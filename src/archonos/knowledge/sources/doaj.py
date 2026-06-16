"""DOAJ source — Directory of Open Access Journals metadata.

API: REST JSON, no auth, no rate limit. https://doaj.org/api/v3/docs

Endpoints:
    GET https://doaj.org/api/articles/<doi>
        Fetch a single article by DOI.
    GET https://api.doaj.org/search/articles/<query>
        Search by free text or fielded query (e.g. 'title:open access').
        NOTE: the search endpoint is search.doaj.org; the API search is
        https://doaj.org/api/search/articles/<query>?ref=homepage-box

Schemes:
    doaj:<doi>          e.g. doaj:10.1234/example
    https://doaj.org/... (resolved via URL dispatcher)
"""

from __future__ import annotations

import urllib.parse

from archonos.knowledge.sources.base import Document, SourceError
from archonos.knowledge.sources.http import get_json

API = "https://doaj.org/api"


class DOAJSource:
    scheme = "doaj"
    base_url = API
    name = "DOAJ"

    def fetch(self, identifier: str) -> list[Document]:
        doi = _strip_doaj_prefix(identifier)
        if not doi.startswith("10."):
            raise SourceError(f"DOAJ: invalid DOI {doi!r}")
        try:
            data = get_json(
                f"{API}/articles/{urllib.parse.quote(doi, safe='/')}",
                headers={"Accept": "application/json"},
            )
        except Exception as e:
            raise SourceError(f"DOAJ fetch failed for {doi!r}: {e}") from e
        bibjson = (data.get("bibjson") or {})
        if not bibjson:
            raise SourceError(f"DOAJ: no record for {doi!r}")
        return [_parse_bibjson(doi, bibjson)]

    def search(self, query: str, limit: int = 10) -> list[Document]:
        if limit <= 0:
            return []
        try:
            data = get_json(
                f"{API}/search/articles/{urllib.parse.quote(query, safe=':')}",
                params={"pageSize": min(limit, 20)},
                headers={"Accept": "application/json"},
            )
        except Exception as e:
            raise SourceError(f"DOAJ search failed: {e}") from e
        results = data.get("results") or []
        docs = []
        for item in results:
            bibjson = item.get("bibjson") or {}
            doi = ""
            for ident in bibjson.get("identifier") or []:
                if ident.get("type") == "doi":
                    doi = ident.get("id", "")
                    break
            if not doi:
                continue
            try:
                docs.append(_parse_bibjson(doi, bibjson))
            except Exception:
                continue
        return docs


def _strip_doaj_prefix(identifier: str) -> str:
    s = identifier.strip()
    for prefix in ("doaj:", "https://doaj.org/", "http://doaj.org/", "doaj.org/"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return s


def _parse_bibjson(doi: str, b: dict) -> Document:
    """Parse a DOAJ bibjson record into a Document."""
    title = (b.get("title") or "").strip() or f"DOI:{doi}"
    abstract = (b.get("abstract") or "").strip()

    authors = []
    for a in b.get("author") or []:
        name = a.get("name") if isinstance(a, dict) else str(a)
        if name:
            authors.append(name)

    journal = (b.get("journal") or {}).get("title") or ""
    publisher = (b.get("journal") or {}).get("publisher") or ""
    year = (b.get("year") or "").strip()
    issn = ((b.get("journal") or {}).get("issns") or [])
    if isinstance(issn, list) and issn:
        issn = issn[0]
    else:
        issn = ""

    # Keywords / subjects
    keywords = b.get("keywords") or []
    if not keywords:
        subjects = b.get("subject") or []
        keywords = [
            s.get("term") for s in subjects
            if isinstance(s, dict) and s.get("term")
        ]

    # Links — DOAJ returns fulltext URLs in links
    fulltext_urls = []
    for link in b.get("link") or []:
        url = link.get("url") if isinstance(link, dict) else None
        if url:
            fulltext_urls.append(url)

    content = f"# {title}\n\n"
    if authors:
        content += "**Authors:** " + ", ".join(authors) + "\n\n"
    if journal:
        content += f"**Journal:** {journal}\n\n"
    if publisher:
        content += f"**Publisher:** {publisher}\n\n"
    if year:
        content += f"**Year:** {year}\n\n"
    if issn:
        content += f"**ISSN:** {issn}\n\n"
    content += f"**DOI:** {doi}\n\n"
    if keywords:
        content += "**Keywords:** " + ", ".join(str(k) for k in keywords[:8]) + "\n\n"
    content += "## Abstract\n\n" + (abstract or "_(no abstract available)_\n")
    if fulltext_urls:
        content += "\n**Full text:**\n"
        for u in fulltext_urls[:3]:
            content += f"- {u}\n"
    content += f"\n---\n*Source: https://doaj.org/article/{doi}*\n"

    return Document(
        source_path=fulltext_urls[0] if fulltext_urls else f"https://doi.org/{doi}",
        title=title,
        doc_type="doaj",
        content=content,
        byte_size=len(content.encode("utf-8")),
        meta={
            "doi": doi,
            "authors": authors,
            "journal": journal,
            "publisher": publisher,
            "year": year,
            "issn": issn,
            "keywords": keywords,
            "fulltext_urls": fulltext_urls,
        },
    )
