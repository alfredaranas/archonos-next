"""Knowledge sources — fetch papers from open-access hubs.

Per docs/architecture/CORE_ARCHITECTURE.md §1: stdlib only.
This package is post-alpha (M6+). It uses only stdlib urllib + json +
xml.etree to hit public APIs of open-access paper hubs.

The Source protocol is the contract every hub implements. A Source:
- has a scheme prefix (e.g. "arxiv", "doi", "pmid", "openalex")
- can resolve an identifier OR a URL to a list[Document]
- can be queried by free-text (search) returning a list[Document]
- is read-only (no writes, no state)

Documents returned by Source.fetch() / Source.search() are in-memory
shapes that knowledge.import_ can persist into the documents + chunks
tables. They include a stable source_path that the kernel can re-fetch
from, plus the content (abstract or full text) ready for chunking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Document:
    """An in-memory document ready to be imported into the knowledge base.

    Maps 1:1 to the documents table in CORE_ARCHITECTURE.md §2:
        source_path, title, doc_type, sha256, byte_size, meta
    Plus the actual content for chunking.
    """
    source_path: str       # stable URL or scheme-prefixed ID, used for dedupe
    title: str
    doc_type: str          # 'arxiv' | 'pubmed' | 'openalex' | 'core' | 'doaj' | 'oamg' | 'unpaywall' | ...
    content: str           # abstract or full text — what gets chunked
    byte_size: int = 0
    sha256: str = ""       # computed by import_ on persist
    meta: dict = field(default_factory=dict)

    def to_meta(self) -> dict:
        """Return a JSON-safe dict for the documents.meta column."""
        return {
            "source_path": self.source_path,
            "title": self.title,
            "doc_type": self.doc_type,
            **({"sha256": self.sha256} if self.sha256 else {}),
            **({"byte_size": self.byte_size} if self.byte_size else {}),
            **self.meta,
        }


class SourceError(Exception):
    """Raised when a source fails to resolve or fetch."""


@runtime_checkable
class Source(Protocol):
    """The contract every paper-source implements.

    A source has:
        scheme:    the prefix the CLI dispatcher uses (e.g. "arxiv")
        base_url:  the API root (for diagnostics)
        name:      human-readable name (for archonos fetch --list)

    And two methods:
        fetch(identifier) -> list[Document]
            Resolve an identifier (scheme-prefixed or URL) into one or
            more Documents. Most sources return 1 document per call.
        search(query, limit) -> list[Document]
            Free-text search; returns up to `limit` results.
    """
    scheme: str
    base_url: str
    name: str

    def fetch(self, identifier: str) -> list[Document]: ...
    def search(self, query: str, limit: int = 10) -> list[Document]: ...


# --- identifier parsing (CLI dispatch) ---


def parse_identifier(s: str) -> tuple[str, str]:
    """Parse "<scheme>:<id>" or a bare URL into (scheme, id).

    Examples:
        "arxiv:2501.12345"        -> ("arxiv",  "2501.12345")
        "doi:10.1038/nature12373" -> ("doi",    "10.1038/nature12373")
        "https://arxiv.org/abs/2501.12345" -> ("arxiv", "2501.12345")
        "pmid:33212345"           -> ("pmid",   "33212345")
    """
    s = s.strip()
    # HF sub-type prefixes (model:/dataset:/space:) — these all route to
    # the `hf` scheme. The HuggingFaceSource then re-parses the kind from
    # the prefix on its own. Without this alias, `model:foo` would be
    # treated as a separate scheme that doesn't exist.
    if ":" in s and not s.startswith("http"):
        prefix = s.split(":", 1)[0].lower()
        if prefix in ("model", "dataset", "space"):
            return "hf", s
    if "://" in s:
        # Bare URL — map host to scheme
        host_to_scheme = {
            "arxiv.org": "arxiv",
            "pubmed.ncbi.nlm.nih.gov": "pmid",
            "ncbi.nlm.nih.gov": "pmid",
            "doi.org": "doi",
            "openalex.org": "openalex",
            "core.ac.uk": "core",
            "doaj.org": "doaj",
            "oa.mg": "oamg",
            "huggingface.co": "hf",
        }
        for host, scheme in host_to_scheme.items():
            if host in s:
                return scheme, s
        raise SourceError(f"Unknown URL host: {s}")
    if ":" in s:
        scheme, _, ident = s.partition(":")
        return scheme.strip().lower(), ident.strip()
    raise SourceError(f"Cannot parse identifier (need 'scheme:id' or URL): {s!r}")


def all_sources() -> dict[str, "Source"]:
    """Lazy registry of all known sources. Importing a source module
    registers it. Returned by scheme name."""
    # Local imports to avoid circular dependencies and to keep import
    # time low (urllib is heavy if imported eagerly).
    from archonos.knowledge.sources import arxiv, openalex, pubmed, unpaywall, core, crossref, doaj, huggingface

    return {
        "arxiv": arxiv.ArxivSource(),
        "openalex": openalex.OpenAlexSource(),
        "pmid": pubmed.PubmedSource(),
        "pmcid": pubmed.PMCSource(),
        "doi": unpaywall.UnpaywallSource(),
        "core": core.CORESource(),
        "crossref": crossref.CrossrefSource(),
        "doaj": doaj.DOAJSource(),
        "hf": huggingface.HuggingFaceSource(),
    }
