"""Knowledge search — FTS5 full-text search."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class SearchHit:
    chunk_id: int
    document_id: int
    title: str
    snippet: str
    rank: float


def search(conn: sqlite3.Connection, query: str, k: int = 10) -> list[SearchHit]:
    """Search knowledge base using FTS5.
    
    Returns top-k ranked results.
    """
    if not query.strip():
        return []
    
    # Escape FTS5 special characters and prepare query
    # Use simple prefix matching for safety
    terms = query.strip().split()
    fts_query = " OR ".join(f'"{term}"' for term in terms if term)
    
    if not fts_query:
        return []
    
    # Query FTS5 and join with documents
    sql = """
        SELECT 
            c.id AS chunk_id,
            c.document_id,
            d.title,
            snippet(chunks_fts, 0, '<mark>', '</mark>', '...', 32) AS snippet,
            bm25(chunks_fts) AS rank
        FROM chunks_fts f
        JOIN chunks c ON c.id = f.rowid
        JOIN documents d ON d.id = c.document_id
        WHERE chunks_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """
    
    try:
        cursor = conn.execute(sql, (fts_query, k))
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        # Fallback if FTS table doesn't exist yet
        return []
    
    results = []
    for row in rows:
        results.append(SearchHit(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            title=row["title"],
            snippet=row["snippet"],
            rank=abs(row["rank"]),  # BM25 returns negative values
        ))
    
    return results
