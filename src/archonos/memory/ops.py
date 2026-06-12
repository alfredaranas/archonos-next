"""Memory operations — persistent storage for decisions, lessons, state, notes."""

from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass


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
        # FTS5 search - use internal FTS table (no rowid column)
        sql = """
            SELECT m.id, m.kind, m.body, m.project, m.created_at, m.meta
            FROM memories m
            WHERE m.id IN (
                SELECT rowid FROM memories_fts WHERE memories_fts MATCH ?
            )
            ORDER BY m.created_at DESC
            LIMIT ?
        """
        cursor = conn.execute(sql, (query, limit))
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
        Memory(
            id=r[0],
            kind=r[1],
            body=r[2],
            project=r[3],
            created_at=r[4],
            meta=r[5]
        )
        for r in cursor.fetchall()
    ]


def decisions(conn: sqlite3.Connection, project: str = "default", limit: int = 10) -> list[Memory]:
    """Recall all decisions."""
    return recall(conn, kind="decision", project=project, limit=limit)


def lessons(conn: sqlite3.Connection, project: str = "default", limit: int = 10) -> list[Memory]:
    """Recall all lessons."""
    return recall(conn, kind="lesson", project=project, limit=limit)
