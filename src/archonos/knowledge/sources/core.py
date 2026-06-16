"""CORE source — 200M+ open-access papers aggregator.

API: REST JSON, no auth but a key is recommended for higher rate
limits (we don't use a key in v1; the no-key pool is sufficient for
single-document imports). https://core.ac.uk/docs/

Endpoints:
    GET https://api.core.ac.uk/v3/works/<id>
    GET https://api.core.ac.uk/v3/works?search=<query>&limit=<n>

Schemes:
    core:<id>            e.g. core:12345
    https://core.ac.uk/works/<id>   (resolved via URL dispatcher)
"""

from __future__ import annotations

import urllib.parse

from archonos.knowledge.sources.base import Document, SourceError
from archonos.knowledge.sources.http import get_json

BASE = "https://api.core.ac.uk/v3"


class CORESource:
    scheme = "core"
    base_url = BASE
    name = "CORE"

    def fetch(self, identifier: str) -> list[Document]:
        ident = _strip_core_prefix(identifier)
        # CORE IDs are numeric (e.g. 12345); URLs end in /works/<id>
        if "/" in ident:
            ident = ident.rstrip("/").rsplit("/", 1)[-1]
        if not ident:
            raise SourceError(f"CORE: invalid identifier {identifier!r}")
        try:
            data = get_json(f"{BASE}/works/{urllib.parse.quote(ident, safe='')}")
        except Exception as e:
            raise SourceError(f"CORE fetch failed for {ident!r}: {e}") from e
        if not data or not data.get("id"):
            raise SourceError(f"CORE: no work found for id={ident!r}")
        return [_parse_work(data)]

    def search(self, query: str, limit: int = 10) -> list[Document]:
        if limit <= 0:
            return []
        try:
            data = get_json(
                f"{BASE}/search/works",
                params={"q": query, "limit": min(limit, 20)},
            )
        except Exception as e:
            raise SourceError(f"CORE search failed: {e}") from e
        results = data.get("results") or []
        return [_parse_work(w) for w in results if w]


def _strip_core_prefix(identifier: str) -> str:
    s = identifier.strip()
    if s.startswith("core:"):
        s = s.split(":", 1)[1]
    return s


def _parse_work(w: dict) -> Document:
    """Parse a CORE work dict into a Document."""
    title = (w.get("title") or "").strip() or "Untitled"
    abstract = (w.get("abstract") or "").strip()
    if not abstract and w.get("description"):
        abstract = w["description"].strip()

    authors = []
    for a in w.get("authors") or []:
        name = a.get("name") if isinstance(a, dict) else str(a)
        if name:
            authors.append(name)

    doi = w.get("doi") or ""
    year = w.get("yearPublished") or w.get("year") or ""
    publisher = w.get("publisher") or ""
    journal = ""
    # CORE returns 'journals' as a list of names
    journals = w.get("journals") or []
    if isinstance(journals, list) and journals:
        if isinstance(journals[0], dict):
            journal = journals[0].get("title") or ""
        else:
            journal = str(journals[0])

    download_url = w.get("downloadUrl") or ""
    source_url = w.get("sourceFulltextUrls") or []
    if isinstance(source_url, list) and source_url:
        source_url = source_url[0] if source_url else ""
    else:
        source_url = ""

    core_id = w.get("id") or ""
    # CORE may return a full URL or a bare id
    if isinstance(core_id, str) and core_id.startswith("http"):
        core_id_short = core_id.rstrip("/").rsplit("/", 1)[-1]
    else:
        core_id_short = str(core_id)

    # Topics / keywords
    topics = []
    for k in w.get("topics") or []:
        if isinstance(k, dict):
            n = k.get("label") or k.get("name")
            if n:
                topics.append(n)
        else:
            topics.append(str(k))

    content = f"# {title}\n\n"
    if authors:
        content += "**Authors:** " + ", ".join(authors) + "\n\n"
    if year:
        content += f"**Year:** {year}\n\n"
    if journal:
        content += f"**Journal:** {journal}\n\n"
    if publisher:
        content += f"**Publisher:** {publisher}\n\n"
    if doi:
        content += f"**DOI:** {doi}\n\n"
    if topics:
        content += "**Topics:** " + ", ".join(topics[:8]) + "\n\n"
    content += "## Abstract\n\n" + (abstract or "_(no abstract available)_\n")
    if download_url:
        content += f"\n**Download URL:** {download_url}\n"
    if source_url and source_url != download_url:
        content += f"**Source:** {source_url}\n"
    content += f"\n---\n*Source: https://core.ac.uk/works/{core_id_short}*\n"

    return Document(
        source_path=download_url or source_url or f"https://core.ac.uk/works/{core_id_short}",
        title=title,
        doc_type="core",
        content=content,
        byte_size=len(content.encode("utf-8")),
        meta={
            "core_id": core_id_short,
            "doi": doi,
            "authors": authors,
            "year": year,
            "journal": journal,
            "publisher": publisher,
            "topics": topics,
            "download_url": download_url,
            "source_url": source_url,
        },
    )
