"""arXiv source — 2.4M+ open-access preprints.

API: Atom XML over HTTP, no auth, no rate limit beyond a polite
User-Agent. https://info.arxiv.org/help/api/index.html

Endpoints used:
    https://export.arxiv.org/api/query?search_query=...&max_results=...
        Returns Atom feed with <entry> per paper.
        Search fields: ti (title), au (author), abs (abstract), all (all).
        Operator prefixes: ti:"...", au:"...", AND, OR, ANDNOT.

Identifiers:
    arxiv:<id>          e.g. arxiv:2501.12345 or arxiv:cs/0102034
    https://arxiv.org/abs/<id>   (also arxiv.org/pdf/<id> for PDF)
"""

from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET

from archonos.knowledge.sources.base import Document, SourceError
from archonos.knowledge.sources.http import get_xml, ns_strip

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"


class ArxivSource:
    scheme = "arxiv"
    base_url = "https://export.arxiv.org/api/query"
    name = "arXiv"

    def fetch(self, identifier: str) -> list[Document]:
        """Fetch one paper by arXiv ID. Returns 1-element list."""
        ident = _strip_arxiv_prefix(identifier)
        url = self.base_url + "?id_list=" + urllib.parse.quote(ident) + "&max_results=1"
        root = get_xml(url)
        entries = [el for el in root if ns_strip(el.tag) == "entry"]
        if not entries:
            raise SourceError(f"arXiv: no paper found for id={ident!r}")
        return [_parse_entry(entries[0])]

    def search(self, query: str, limit: int = 10) -> list[Document]:
        """Free-text search across all arXiv fields."""
        if limit <= 0:
            return []
        params = {
            "search_query": f"all:{query}",
            "max_results": str(min(limit, 50)),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        qs = urllib.parse.urlencode(params)
        root = get_xml(self.base_url + "?" + qs)
        docs = []
        for el in root:
            if ns_strip(el.tag) == "entry":
                docs.append(_parse_entry(el))
        return docs


def _strip_arxiv_prefix(identifier: str) -> str:
    s = identifier.strip()
    if s.startswith("arxiv:"):
        s = s.split(":", 1)[1]
    # If it was a URL, take the last path segment
    if "/" in s and " " not in s:
        s = s.rstrip("/").rsplit("/", 1)[-1]
    # Drop any ".pdf" / ".abs" extension
    for ext in (".pdf", ".abs"):
        if s.endswith(ext):
            s = s[: -len(ext)]
    return s


def _parse_entry(entry: ET.Element) -> Document:
    """Parse one <entry> into a Document."""
    arxiv_id = _text(entry, f"{ARXIV}id") or _text(entry, f"{ATOM}id")
    title = _strip_ws(_text(entry, f"{ATOM}title") or "")
    summary = _strip_ws(_text(entry, f"{ATOM}summary") or "")

    # Authors
    authors = []
    for a in entry.iter(f"{ATOM}author"):
        name = _text(a, f"{ATOM}name")
        if name:
            authors.append(name)

    # Categories
    categories = []
    for c in entry.iter(f"{ARXIV}category"):
        term = c.attrib.get("term")
        if term:
            categories.append(term)

    # Published / updated
    published = _text(entry, f"{ATOM}published") or ""

    # Link to abstract page
    abs_link = ""
    pdf_link = ""
    for l in entry.iter(f"{ATOM}link"):
        href = l.attrib.get("href", "")
        rel = l.attrib.get("rel", "")
        title_attr = l.attrib.get("title", "")
        if rel == "alternate" and "arxiv.org" in href:
            abs_link = href
        if title_attr == "pdf" and "arxiv.org/pdf" in href:
            pdf_link = href

    # Use canonical arXiv URL as source_path for stable dedupe
    source_path = abs_link or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "")

    # Content: title + authors + abstract + categories. Markdown-lite.
    content = f"# {title}\n\n"
    if authors:
        content += "**Authors:** " + ", ".join(authors) + "\n\n"
    if arxiv_id:
        content += f"**arXiv:** {arxiv_id}\n\n"
    if categories:
        content += "**Categories:** " + ", ".join(categories) + "\n\n"
    if published:
        content += f"**Published:** {published}\n\n"
    content += "## Abstract\n\n" + summary + "\n"
    if abs_link:
        content += f"\n---\n*Source: {abs_link}*\n"
    if pdf_link:
        content += f"*PDF: {pdf_link}*\n"

    meta = {
        "arxiv_id": arxiv_id,
        "authors": authors,
        "categories": categories,
        "published": published,
        "abs_url": abs_link,
        "pdf_url": pdf_link,
    }
    return Document(
        source_path=source_path,
        title=title or (f"arXiv:{arxiv_id}" if arxiv_id else "arXiv paper"),
        doc_type="arxiv",
        content=content,
        byte_size=len(content.encode("utf-8")),
        meta=meta,
    )


def _text(el: ET.Element, tag: str) -> str | None:
    """Get text of a child element with the given tag, or None."""
    for child in el.iter(tag):
        if child.text is not None:
            return child.text
    return None


def _strip_ws(s: str) -> str:
    """Collapse whitespace and strip — arXiv Atom responses have
    irregular indentation/whitespace in title and summary."""
    return " ".join(s.split())
