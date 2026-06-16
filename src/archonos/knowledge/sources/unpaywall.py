"""Unpaywall source — DOI resolver to free full-text copies.

API: REST JSON, no API key but they require an email in the User-Agent
header for the polite pool. https://unpaywall.org/products/api

Endpoint:
    GET https://api.unpaywall.org/v2/<doi>?email=<email>
        Returns best_oa_location (the best Open Access copy), or
        {'best_oa_location': None, 'oa_status': 'closed'} if closed.

Schemes:
    doi:<doi>          e.g. doi:10.1038/nature12373
    https://doi.org/<doi>   (resolved via the URL dispatcher)
"""

from __future__ import annotations

import urllib.parse

from archonos.knowledge.sources.base import Document, SourceError
from archonos.knowledge.sources.http import get_json

BASE = "https://api.unpaywall.org/v2"
# Polite pool requires email; replace at runtime via env or config.
DEFAULT_EMAIL = "kernel@archonos.local"


class UnpaywallSource:
    scheme = "doi"
    base_url = BASE
    name = "Unpaywall"

    def __init__(self, email: str | None = None):
        self.email = email or DEFAULT_EMAIL

    def fetch(self, identifier: str) -> list[Document]:
        doi = _strip_doi_prefix(identifier)
        if not doi.startswith("10."):
            raise SourceError(f"Unpaywall: invalid DOI {doi!r}")
        try:
            data = get_json(
                f"{BASE}/{urllib.parse.quote(doi, safe='/')}",
                params={"email": self.email},
            )
        except Exception as e:
            raise SourceError(f"Unpaywall fetch failed for {doi!r}: {e}") from e
        if not data or not data.get("doi"):
            raise SourceError(f"Unpaywall: no data for DOI {doi!r}")
        return [_parse_response(doi, data)]

    def search(self, query: str, limit: int = 10) -> list[Document]:
        """Unpaywall has no free-text search. We use the DataCite
        DOI-resolve-and-search as a fallback (queries DataCite's
        public API for DOIs matching the query) — best-effort, may
        return zero results if the query doesn't look like a DOI prefix.
        """
        # Best-effort: try DataCite for works matching the query
        if limit <= 0:
            return []
        try:
            data = get_json(
                "https://api.datacite.org/dois",
                params={"query": query, "page[size]": min(limit, 20)},
                headers={"Accept": "application/json"},
            )
        except Exception:
            return []
        items = (data.get("data") or [])
        docs = []
        for item in items:
            attrs = item.get("attributes") or {}
            doi = attrs.get("doi")
            if not doi:
                continue
            try:
                docs.extend(self.fetch("doi:" + doi))
            except Exception:
                continue
        return docs


def _strip_doi_prefix(identifier: str) -> str:
    s = identifier.strip()
    for prefix in ("doi:", "https://doi.org/", "http://doi.org/", "doi.org/"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return s


def _parse_response(doi: str, data: dict) -> Document:
    """Parse an Unpaywall /v2/<doi> response into a Document."""
    title = (data.get("title") or "").strip() or f"DOI:{doi}"
    authors = []
    for a in data.get("z_authors") or []:
        name = (
            " ".join(p for p in [a.get("given"), a.get("family")] if p)
        ).strip()
        if name:
            authors.append(name)
    journal = (data.get("journal_name") or "").strip()
    year = data.get("year")
    publisher = (data.get("publisher") or "").strip()
    oa_status = data.get("oa_status") or "closed"
    best = data.get("best_oa_location") or {}

    oa_url = best.get("url") or ""
    oa_url_for_pdf = best.get("url_for_pdf") or ""
    license = best.get("license") or ""
    version = best.get("version") or ""

    # Reconstruct an abstract? Unpaywall doesn't return abstracts —
    # only metadata. So content is metadata + a pointer to the OA copy.
    content = f"# {title}\n\n"
    if authors:
        content += "**Authors:** " + ", ".join(authors) + "\n\n"
    if journal:
        content += f"**Journal:** {journal}\n\n"
    if year:
        content += f"**Year:** {year}\n\n"
    if publisher:
        content += f"**Publisher:** {publisher}\n\n"
    content += f"**DOI:** {doi}\n\n"
    content += f"**Open Access Status:** {oa_status}\n\n"
    if oa_url:
        content += f"**Open Access URL:** {oa_url}\n\n"
    if oa_url_for_pdf and oa_url_for_pdf != oa_url:
        content += f"**PDF:** {oa_url_for_pdf}\n\n"
    if license:
        content += f"**License:** {license}\n\n"
    if version:
        content += f"**Version:** {version}\n\n"
    content += (
        "_Note: Unpaywall returns metadata only (no abstract). The "
        "Open Access URL above links to the free full text if available._\n"
    )
    content += f"\n---\n*Source: https://api.unpaywall.org/v2/{doi} (resolved DOI: https://doi.org/{doi})*\n"

    source_path = oa_url or f"https://doi.org/{doi}"

    return Document(
        source_path=source_path,
        title=title,
        doc_type="unpaywall",
        content=content,
        byte_size=len(content.encode("utf-8")),
        meta={
            "doi": doi,
            "authors": authors,
            "journal": journal,
            "year": year,
            "publisher": publisher,
            "oa_status": oa_status,
            "oa_url": oa_url,
            "oa_url_for_pdf": oa_url_for_pdf,
            "license": license,
            "version": version,
        },
    )
