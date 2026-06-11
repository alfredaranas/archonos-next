"""Memory operations — remember + recall."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Memory:
    id: int
    kind: str
    body: str
    project: str
    created_at: str
    meta: str


def remember(
    conn: sqlite3.Connection,
    kind: str,
    body: str,
    project: str = "default",
    meta: str = "{}"
) -> int:
    """Store a memory. Returns memory id."""
    cursor = conn.execute(
        """INSERT INTO memories (kind, body, project, meta)
           VALUES (?, ?, ?, ?)""",
        (kind, body, project, meta)
    )
    conn.commit()
    return cursor.lastrowid


def recall(
    conn: sqlite3.Connection,
    query: str | None = None,
    kind: str | None = None,
    project: str = "default",
    limit: int = 10
) -> list[Memory]:
    """Recall memories by query or kind."""
    if query:
        # FTS5 search
        sql = """
            SELECT m.id, m.kind, m.body, m.project, m.created_at, m.meta
            FROM memories_fts f
            JOIN memories m ON m.id = f.rowid
            WHERE memories_fts MATCH ?
            ORDER BY bm25(memories_fts)
            LIMIT ?
        """
        cursor = conn.execute(sql, (f'"{query}"', limit))
    elif kind:
        sql = """
            SELECT id, kind, body, project, created_at, meta
            FROM memories
            WHERE project = ? AND kind = ?
            ORDER BY created_at DESC
            LIMIT ?
        """
        cursor = conn.execute(sql, (project, kind, limit))
    else:
        sql = """
            SELECT id, kind, body, project, created_at, meta
            FROM memories
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
        """
        cursor = conn.execute(sql, (project, limit))
    
    return [
        Memory(id=r["id"], kind=r["kind"], body=r["body"],
               project=r["project"], created_at=r["created_at"], meta=r["meta"])
        for r in cursor.fetchall()
    ]


def decisions(conn: sqlite3.Connection, project: str = "default") -> list[Memory]:
    """Get all decisions for a project."""
    return recall(conn, kind="decision", project=project)


def lessons(conn: sqlite3.Connection, project: str = "default") -> list[Memory]:
    """Get all lessons for a project."""
    return recall(conn, kind="lesson", project=project)