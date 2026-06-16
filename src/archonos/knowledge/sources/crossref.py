"""Crossref source — canonical DOI registry, 150M+ records.

API: REST JSON, no auth but a polite-pool User-Agent with a contact
email is recommended (their `mailto` query parameter puts you in the
polite pool automatically). https://api.crossref.org/

Endpoints:
    GET https://api.crossref.org/works/<doi>
        Fetch a single work by DOI.
    GET https://api.crossref.org/works?query=<query>&rows=<n>
        Free-text search across all works.

Schemes:
    crossref:<doi>            e.g. crossref:10.1038/nature12373
    crossref-search:<query>   (search form; same source handles it)
    https://doi.org/<doi>     (resolved via the URL dispatcher)
"""

from __future__ import annotations

import urllib.parse

from archonos.knowledge.sources.base import Document, SourceError
from archonos.knowledge.sources.http import get_json

BASE = "https://api.crossref.org"
# Polite pool contact — replace at runtime via env or config in production.
POLITE_EMAIL = "kernel@archonos.local"


class CrossrefSource:
    scheme = "crossref"
    base_url = BASE
    name = "Crossref"

    def fetch(self, identifier: str) -> list[Document]:
        doi = _strip_crossref_prefix(identifier)
        if not doi.startswith("10."):
            raise SourceError(f"Crossref: invalid DOI {doi!r}")
        try:
            data = get_json(
                f"{BASE}/works/{urllib.parse.quote(doi, safe='/')}",
                params={"mailto": POLITE_EMAIL},
            )
        except Exception as e:
            raise SourceError(f"Crossref fetch failed for {doi!r}: {e}") from e
        msg = data.get("message") or {}
        if not msg:
            raise SourceError(f"Crossref: no work found for {doi!r}")
        return [_parse_work(doi, msg)]

    def search(self, query: str, limit: int = 10) -> list[Document]:
        if limit <= 0:
            return []
        try:
            data = get_json(
                f"{BASE}/works",
                params={
                    "query": query,
                    "rows": min(limit, 20),
                    "mailto": POLITE_EMAIL,
                },
            )
        except Exception as e:
            raise SourceError(f"Crossref search failed: {e}") from e
        items = (data.get("message") or {}).get("items") or []
        docs = []
        for item in items:
            doi = item.get("DOI")
            if not doi:
                continue
            try:
                docs.append(_parse_work(doi, item))
            except Exception:
                continue
        return docs


def _strip_crossref_prefix(identifier: str) -> str:
    s = identifier.strip()
    for prefix in ("crossref:", "crossref-search:", "https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return s


def _parse_work(doi: str, w: dict) -> Document:
    """Parse a Crossref work message into a Document."""
    title_list = w.get("title") or []
    title = (title_list[0] if title_list else "").strip() or f"DOI:{doi}"
    subtitle_list = w.get("subtitle") or []
    if subtitle_list and title and not title.endswith("."):
        title = f"{title}: {subtitle_list[0]}".strip()

    # Authors
    authors = []
    for a in w.get("author") or []:
        given = a.get("given") or ""
        family = a.get("family") or ""
        if given or family:
            authors.append(f"{given} {family}".strip())

    # Abstract (Crossref sometimes returns JATS in <jats:p> tags; strip them)
    abstract = (w.get("abstract") or "").strip()
    if abstract:
        # Crude JATS strip
        import re
        abstract = re.sub(r"<[^>]+>", "", abstract)
        abstract = " ".join(abstract.split())

    # Container (journal/book)
    container_list = w.get("container-title") or []
    journal = container_list[0] if container_list else ""
    publisher = (w.get("publisher") or "").strip()

    # Year / date
    issued = w.get("issued") or {}
    date_parts = (issued.get("date-parts") or [[]])[0]
    year = date_parts[0] if date_parts else None
    issued_date = w.get("issued", {}).get("date-time") or ""
    if not issued_date and year:
        issued_date = str(year)

    # Type
    work_type = w.get("type") or ""

    # Volume / issue / page
    volume = w.get("volume") or ""
    issue = w.get("issue") or ""
    page = w.get("page") or ""

    # Subjects
    subjects = []
    for s in w.get("subject") or []:
        if isinstance(s, str):
            subjects.append(s)

    # Link (URL)
    link = (w.get("URL") or "").strip()

    # License
    licenses = w.get("license") or []
    license_urls = [l.get("URL") for l in licenses if l.get("URL")]

    content = f"# {title}\n\n"
    if authors:
        content += "**Authors:** " + ", ".join(authors) + "\n\n"
    if journal:
        content += f"**Journal:** {journal}\n\n"
    if publisher:
        content += f"**Publisher:** {publisher}\n\n"
    if year:
        content += f"**Year:** {year}\n\n"
    if work_type:
        content += f"**Type:** {work_type}\n\n"
    if volume or issue or page:
        bits = []
        if volume:
            bits.append(f"vol {volume}")
        if issue:
            bits.append(f"no {issue}")
        if page:
            bits.append(f"pp {page}")
        content += "**Citation:** " + ", ".join(bits) + "\n\n"
    content += f"**DOI:** {doi}\n\n"
    if subjects:
        content += "**Subjects:** " + ", ".join(subjects[:8]) + "\n\n"
    if link:
        content += f"**URL:** {link}\n\n"
    if license_urls:
        content += f"**License:** {license_urls[0]}\n\n"
    content += "## Abstract\n\n" + (abstract or "_(no abstract available)_\n")
    content += f"\n---\n*Source: https://doi.org/{doi}*\n"

    return Document(
        source_path=link or f"https://doi.org/{doi}",
        title=title,
        doc_type="crossref",
        content=content,
        byte_size=len(content.encode("utf-8")),
        meta={
            "doi": doi,
            "authors": authors,
            "journal": journal,
            "publisher": publisher,
            "year": year,
            "issued_date": issued_date,
            "type": work_type,
            "volume": volume,
            "issue": issue,
            "page": page,
            "subjects": subjects,
            "url": link,
            "license": license_urls[0] if license_urls else "",
        },
    )
