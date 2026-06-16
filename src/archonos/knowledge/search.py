"""FTS5 search for ArchonOS knowledge base.

Per docs/architecture/CORE_ARCHITECTURE.md §4:
    search(conn, query, k=10) -> list[Hit(chunk_id, doc_title, snippet, rank)]

Per §2: chunks_fts is a contentless FTS5 table synced via triggers; we
query against it for ranking and join back to chunks + documents.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass


@dataclass
class Hit:
    chunk_id: int
    doc_title: str
    snippet: str
    rank: float


_SNIPPET_RE = re.compile(r"\s+")


def _bm25_to_rank(bm25: float) -> float:
    """Convert SQLite's BM25 (more-negative = better) to a 0..1 score (higher = better).

    SQLite's bm25() returns 0 for perfect match, and more-negative numbers for
    weaker matches. We want a score where higher = better, strictly monotonic
    with the source BM25.
    """
    # bm25 == 0 means a term appeared in every document (idf ~ 0). Treat as the
    # "weakest positive" score.
    if bm25 >= 0:
        return 0.0
    # Saturating transform: rank = |bm25| / (|bm25| + K), K = 5.
    #   bm25 = -1  -> rank = 1/6  = 0.167   (best real matches)
    #   bm25 = -5  -> rank = 5/10 = 0.500
    #   bm25 = -20 -> rank = 20/25 = 0.800  (very weak matches)
    #   bm25 = -100-> rank ~ 0.95
    return abs(bm25) / (abs(bm25) + 5.0)


def _make_snippet(body: str, query: str, max_len: int = 220) -> str:
    """Return a window of `body` centered on the first match of any query term."""
    if not body:
        return ""
    text = _SNIPPET_RE.sub(" ", body).strip()
    if len(text) <= max_len:
        return text

    # Find first occurrence of any query term
    terms = [t for t in re.split(r"\W+", query.lower()) if t]
    pos = -1
    lower = text.lower()
    for t in terms:
        p = lower.find(t)
        if p != -1 and (pos == -1 or p < pos):
            pos = p

    if pos == -1:
        return text[: max_len - 1] + "…"

    half = max_len // 2
    start = max(0, pos - half)
    end = min(len(text), start + max_len)
    start = max(0, end - max_len)  # adjust if we ran off the end
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end] + suffix


def search(conn, query: str, k: int = 10):  # type: ignore[no-untyped-def]
    """Search the knowledge base. Returns list[Hit] ranked by relevance (best first)."""
    if not query or not query.strip():
        return []
    if k <= 0:
        return []

    # FTS5 MATCH expression — quote each term to avoid syntax errors
    # from user-supplied punctuation. FTS5 supports "..." for phrase
    # and term1 term2 for AND. We do simple quoted-term-per-word.
    terms = [t for t in re.split(r"\W+", query) if t]
    if not terms:
        return []
    fts_query = " ".join(f'"{t}"' for t in terms)

    rows = conn.execute(
        "SELECT c.id AS chunk_id, "
        "       d.title AS doc_title, "
        "       c.body AS body, "
        "       bm25(chunks_fts) AS bm "
        "FROM chunks_fts "
        "JOIN chunks c ON c.id = chunks_fts.rowid "
        "JOIN documents d ON d.id = c.document_id "
        "WHERE chunks_fts MATCH ? "
        "ORDER BY bm25(chunks_fts) "
        "LIMIT ?",
        (fts_query, k),
    ).fetchall()

    return [
        Hit(
            chunk_id=int(r["chunk_id"]),
            doc_title=r["doc_title"],
            snippet=_make_snippet(r["body"], query),
            rank=_bm25_to_rank(float(r["bm"])),
        )
        for r in rows
    ]


# Helper: validate FTS5 is queryable. Used by tests.
def fts_is_searchable(conn) -> bool:  # type: ignore[no-untyped-def]
    try:
        conn.execute("SELECT 1 FROM chunks_fts LIMIT 0").fetchone()
        return True
    except sqlite3.Error:
        return False
