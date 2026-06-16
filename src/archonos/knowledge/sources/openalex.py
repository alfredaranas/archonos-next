"""OpenAlex source — 250M+ scholarly works with cross-publisher metadata.

API: REST JSON, no auth required but a polite pool expects a User-Agent
with contact info. https://docs.openalex.org/

Endpoints used:
    GET https://api.openalex.org/works/<id>
        ID can be:
          - W-prefixed OpenAlex ID (e.g. W2741809807) — full
          - DOI (e.g. 10.1038/nature12373) — auto-resolved
          - PMID (e.g. 23212345) — auto-resolved if prefixed
    GET https://api.openalex.org/works?search=<query>&per-page=<n>
        Free-text search.
"""

from __future__ import annotations

import urllib.parse

from archonos.knowledge.sources.base import Document, SourceError
from archonos.knowledge.sources.http import get, get_json

BASE = "https://api.openalex.org"


class OpenAlexSource:
    scheme = "openalex"
    base_url = BASE
    name = "OpenAlex"

    def fetch(self, identifier: str) -> list[Document]:
        """Fetch one work by OpenAlex ID, DOI, or PMID."""
        ident = _strip_openalex_prefix(identifier)
        # OpenAlex accepts the bare ID; PMIDs/DOIs need a prefix.
        if ident.startswith("10."):
            ident = "doi:" + ident
        elif ident.isdigit() and len(ident) <= 9:
            ident = "pmid:" + ident
        elif ident.startswith("W") and ident[1:].isdigit():
            pass  # already an OpenAlex ID
        # else: try as-is (may be a URL we should resolve)

        if "/" in ident and not ident.startswith(("doi:", "pmid:")):
            # URL form
            ident = ident.rstrip("/").rsplit("/", 1)[-1]
            if ident.startswith("W") and ident[1:].isdigit():
                pass
            else:
                raise SourceError(f"OpenAlex: cannot resolve identifier {ident!r}")

        url = f"{BASE}/works/{ident}"
        try:
            data = get_json(url, headers={"Accept": "application/json"})
        except Exception as e:
            raise SourceError(f"OpenAlex fetch failed for {ident!r}: {e}") from e
        if not data or data.get("id") is None:
            raise SourceError(f"OpenAlex: no work found for {ident!r}")
        return [_parse_work(data)]

    def search(self, query: str, limit: int = 10) -> list[Document]:
        """Free-text search across OpenAlex works."""
        if limit <= 0:
            return []
        per_page = min(limit, 50)
        data = get_json(
            f"{BASE}/works",
            params={"search": query, "per-page": per_page},
        )
        results = data.get("results") or []
        return [_parse_work(w) for w in results if w]


def _strip_openalex_prefix(identifier: str) -> str:
    s = identifier.strip()
    if s.startswith("openalex:"):
        s = s.split(":", 1)[1]
    return s


def _invert_abstract(inv_index: dict | None) -> str:
    """OpenAlex stores abstracts as an inverted index:
        {"word": [positions], ...}
    Reconstruct the abstract text."""
    if not inv_index:
        return ""
    positions: dict[int, str] = {}
    for word, locs in inv_index.items():
        for p in locs:
            positions[p] = word
    if not positions:
        return ""
    max_pos = max(positions)
    words = [positions.get(i, "") for i in range(max_pos + 1)]
    return " ".join(w for w in words if w)


def _parse_work(w: dict) -> Document:
    """Parse an OpenAlex work dict into a Document."""
    # ID
    openalex_id = (w.get("id") or "").rsplit("/", 1)[-1]  # 'W2741809807'

    # Title
    title = (w.get("title") or w.get("display_name") or "").strip() or "Untitled"

    # Abstract (inverted index -> text)
    abstract = _invert_abstract(w.get("abstract_inverted_index"))

    # Authors
    authors = []
    for a in w.get("authorships") or []:
        name = (a.get("author") or {}).get("display_name")
        if name:
            authors.append(name)

    # DOI / PMID (OpenAlex canonical forms)
    doi = (w.get("doi") or "").removeprefix("https://doi.org/")
    pmid = (w.get("ids") or {}).get("pmid", "").rsplit("/", 1)[-1]
    pmcid = (w.get("ids") or {}).get("pmcid", "").rsplit("/", 1)[-1]

    # Concepts / topics
    concepts = []
    for c in (w.get("concepts") or [])[:8]:
        n = c.get("display_name")
        if n:
            concepts.append(n)

    # Journal / venue
    venue = ""
    hv = w.get("primary_location") or {}
    src = hv.get("source") or {}
    if src:
        venue = src.get("display_name") or ""

    # Year / date
    pub_date = w.get("publication_date") or ""
    year = w.get("publication_year")

    # Open-access status
    oa = w.get("open_access") or {}
    oa_status = oa.get("oa_status", "")
    oa_url = oa.get("oa_url") or ""

    # Counts (for relevance/sort if user wants to filter)
    cited = w.get("cited_by_count", 0)

    # Build content
    content = f"# {title}\n\n"
    if authors:
        content += "**Authors:** " + ", ".join(authors) + "\n\n"
    if year:
        content += f"**Year:** {year}\n\n"
    if venue:
        content += f"**Venue:** {venue}\n\n"
    if doi:
        content += f"**DOI:** {doi}\n\n"
    if pmid:
        content += f"**PMID:** {pmid}\n\n"
    if concepts:
        content += "**Concepts:** " + ", ".join(concepts) + "\n\n"
    if oa_status:
        content += f"**Open Access:** {oa_status}\n\n"
    if cited:
        content += f"**Cited by:** {cited}\n\n"
    if abstract:
        content += "## Abstract\n\n" + abstract + "\n"
    else:
        content += "## Abstract\n\n_(no abstract available)_\n"
    content += f"\n---\n*Source: https://openalex.org/{openalex_id}*\n"

    # source_path: prefer OA URL, then DOI URL, then OpenAlex page
    if oa_url:
        source_path = oa_url
    elif doi:
        source_path = f"https://doi.org/{doi}"
    else:
        source_path = f"https://openalex.org/{openalex_id}"

    meta = {
        "openalex_id": openalex_id,
        "doi": doi,
        "pmid": pmid,
        "pmcid": pmcid,
        "authors": authors,
        "venue": venue,
        "year": year,
        "publication_date": pub_date,
        "concepts": concepts,
        "cited_by_count": cited,
        "oa_status": oa_status,
        "oa_url": oa_url,
    }
    return Document(
        source_path=source_path,
        title=title,
        doc_type="openalex",
        content=content,
        byte_size=len(content.encode("utf-8")),
        meta=meta,
    )
