"""PubMed + PubMed Central source — 36M+ biomedical abstracts, 11.6M
full-text papers in the PMC Open Access subset.

API: NCBI E-utilities, no auth but a polite User-Agent with a tool
name and contact email is required for >3 req/sec. We stay well
under that. https://www.ncbi.nlm.nih.gov/books/NBK25500/

Endpoints used:
    esearch.fcgi?db=pubmed&term=<query>&retmode=json
        -> {'esearchresult': {'idlist': [pmids]}}
    esummary.fcgi?db=pubmed&id=<pmid>&retmode=json
        -> per-uid summary
    efetch.fcgi?db=pubmed&id=<pmid>&rettype=abstract&retmode=text
        -> raw MEDLINE abstract text
    For PMC (full text):
    esearch.fcgi?db=pmc&term=<pmid>&retmode=json
        -> pmcid mapping
    efetch.fcgi?db=pmc&id=<pmcid>&rettype=full&retmode=xml
        -> JATS XML, <body> has the full text

Schemes:
    pmid:<n>      -> PubMed abstract (always available)
    pmcid:<PMC..> -> PMC full text (if available; otherwise returns abstract)
"""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET

from archonos.knowledge.sources.base import Document, SourceError
from archonos.knowledge.sources.http import get, get_json, get_xml, ns_strip

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
TOOL = "archonos-next"
EMAIL = "kernel@archonos.local"  # polite pool — replace in production via config


def _common_params() -> dict:
    return {"tool": TOOL, "email": EMAIL}


class PubmedSource:
    scheme = "pmid"
    base_url = ESEARCH
    name = "PubMed"

    def fetch(self, identifier: str) -> list[Document]:
        ident = identifier.strip()
        if ident.startswith("pmid:"):
            ident = ident.split(":", 1)[1]
        if not ident.isdigit():
            raise SourceError(f"PubMed: invalid PMID {ident!r}")
        return [_fetch_pmid(ident)]

    def search(self, query: str, limit: int = 10) -> list[Document]:
        if limit <= 0:
            return []
        n = min(limit, 20)
        data = get_json(
            ESEARCH,
            params={**_common_params(), "db": "pubmed", "term": query, "retmax": n, "retmode": "json"},
        )
        ids = (data.get("esearchresult") or {}).get("idlist") or []
        return [_fetch_pmid(pmid) for pmid in ids]


class PMCSource:
    scheme = "pmcid"
    base_url = EFETCH
    name = "PubMed Central"

    def fetch(self, identifier: str) -> list[Document]:
        ident = identifier.strip()
        if ident.startswith("pmcid:"):
            ident = ident.split(":", 1)[1]
        ident = ident.upper()
        if not ident.startswith("PMC"):
            ident = "PMC" + ident
        return [_fetch_pmcid(ident)]

    def search(self, query: str, limit: int = 10) -> list[Document]:
        # PMC has its own search but for simplicity reuse pubmed search
        # and try to map to PMC.
        if limit <= 0:
            return []
        n = min(limit, 20)
        data = get_json(
            ESEARCH,
            params={**_common_params(), "db": "pmc", "term": query, "retmax": n, "retmode": "json"},
        )
        ids = (data.get("esearchresult") or {}).get("idlist") or []
        return [_fetch_pmcid(pmcid) for pmcid in ids]


# --- internal ---


def _fetch_pmid(pmid: str) -> Document:
    summary = get_json(
        ESUMMARY,
        params={**_common_params(), "db": "pubmed", "id": pmid, "retmode": "json"},
    )
    rec = (summary.get("result") or {}).get(pmid) or {}
    if not rec:
        raise SourceError(f"PubMed: no record for PMID {pmid}")

    title = (rec.get("title") or "").strip()
    authors = rec.get("authors") or []
    author_names = [a.get("name") for a in authors if a.get("name")]
    journal = rec.get("fulljournalname") or rec.get("source") or ""
    pubdate = rec.get("pubdate") or ""
    volume = rec.get("volume") or ""
    issue = rec.get("issue") or ""
    pages = rec.get("pages") or ""
    doi = next((a for a in rec.get("articleids", []) if a.get("idtype") == "doi"), None)
    doi_str = (doi or {}).get("value", "")

    # Try to get the abstract text. esummary doesn't always include it.
    abstract = _fetch_abstract_text(pmid)

    content = f"# {title}\n\n"
    if author_names:
        content += "**Authors:** " + ", ".join(author_names) + "\n\n"
    content += f"**Journal:** {journal}\n\n"
    if pubdate:
        content += f"**Published:** {pubdate}\n\n"
    if volume or issue or pages:
        bits = []
        if volume:
            bits.append(f"vol {volume}")
        if issue:
            bits.append(f"no {issue}")
        if pages:
            bits.append(f"pp {pages}")
        content += "**Citation:** " + ", ".join(bits) + "\n\n"
    content += f"**PMID:** {pmid}\n\n"
    if doi_str:
        content += f"**DOI:** {doi_str}\n\n"
    content += "## Abstract\n\n" + (abstract or "_(no abstract available)_\n")
    content += f"\n---\n*Source: https://pubmed.ncbi.nlm.nih.gov/{pmid}/*\n"

    return Document(
        source_path=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        title=title or f"PMID:{pmid}",
        doc_type="pubmed",
        content=content,
        byte_size=len(content.encode("utf-8")),
        meta={
            "pmid": pmid,
            "authors": author_names,
            "journal": journal,
            "pubdate": pubdate,
            "volume": volume,
            "issue": issue,
            "pages": pages,
            "doi": doi_str,
        },
    )


def _fetch_abstract_text(pmid: str) -> str:
    """Fetch the MEDLINE abstract as plain text."""
    try:
        body = get(
            EFETCH + "?" + urllib.parse.urlencode({**_common_params(), "db": "pubmed", "id": pmid,
                    "rettype": "abstract", "retmode": "text"}),
        )
    except Exception:
        return ""
    return body.decode("utf-8", errors="replace").strip()


def _fetch_pmcid(pmcid: str) -> Document:
    # Try PMC full text (JATS XML)
    try:
        xml_root = get_xml(
            EFETCH,
            params={**_common_params(), "db": "pmc", "id": pmcid, "rettype": "full"},
        )
        full_text, title, authors, journal = _parse_jats(xml_root)
        body_bytes = len(full_text.encode("utf-8"))
        content = f"# {title}\n\n"
        if authors:
            content += "**Authors:** " + ", ".join(authors) + "\n\n"
        if journal:
            content += f"**Journal:** {journal}\n\n"
        content += f"**PMCID:** {pmcid}\n\n"
        content += full_text
        content += f"\n---\n*Source: https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/*\n"
        return Document(
            source_path=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/",
            title=title or pmcid,
            doc_type="pmc",
            content=content,
            byte_size=body_bytes + len(content[:1000].encode("utf-8")),
            meta={"pmcid": pmcid, "authors": authors, "journal": journal},
        )
    except Exception:
        # Fallback: try to resolve the PMCID to a PMID and get the abstract
        try:
            data = get_json(
                ESEARCH,
                params={**_common_params(), "db": "pubmed", "term": pmcid,
                        "retmax": 1, "retmode": "json"},
            )
            ids = (data.get("esearchresult") or {}).get("idlist") or []
            if ids:
                doc = _fetch_pmid(ids[0])
                doc.doc_type = "pmc"
                doc.source_path = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"
                doc.meta["pmcid"] = pmcid
                doc.meta["pmid_fallback"] = ids[0]
                return doc
        except Exception:
            pass
        raise SourceError(f"PMC: no full text or abstract for {pmcid}")


def _parse_jats(root: ET.Element) -> tuple[str, str, list[str], str]:
    """Parse a JATS <article> into (full_text, title, authors, journal)."""
    title = ""
    for t in root.iter():
        if ns_strip(t.tag) == "article-title" and t.text and not title:
            title = " ".join(t.text.split())
            break
    authors = []
    for contrib in root.iter():
        if ns_strip(contrib.tag) == "contrib" and contrib.attrib.get("contrib-type") == "author":
            surname = ""
            given = ""
            for child in contrib:
                tag = ns_strip(child.tag)
                if tag == "surname" and child.text:
                    surname = child.text
                elif tag == "given-names" and child.text:
                    given = child.text
            if surname:
                authors.append(f"{given} {surname}".strip())
    journal = ""
    for j in root.iter():
        if ns_strip(j.tag) == "journal-title" and j.text and not journal:
            journal = " ".join(j.text.split())
            break

    # Full text: walk <p> elements in <body>
    paras = []
    for p in root.iter():
        if ns_strip(p.tag) == "p" and p.text:
            paras.append(" ".join(p.text.split()))
    full_text = "\n\n".join(paras)
    return full_text, title, authors, journal
