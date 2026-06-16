"""Persistent memory for ArchonOS.

Per docs/architecture/CORE_ARCHITECTURE.md §2: memories table with
    (id, kind CHECK, body, project, created_at, meta) and a synced FTS5
    virtual table (memories_fts).

Per §4 contracts:
    memory/store.py  remember(conn, kind, body, meta=None) -> int
    memory/recall.py recall(conn, query, k=10) -> list[MemoryHit]

(These are exposed as the `memory.ops` module so workflow steps can
import a single namespace. The names of the public functions match the
spec exactly.)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime


_VALID_KINDS = ("decision", "state", "lesson", "note", "workflow_outcome")


@dataclass
class MemoryHit:
    id: int
    kind: str
    body: str
    created_at: str
    rank: float


# --- remember ---


def remember(
    conn,
    kind: str,
    body: str,
    meta: dict | None = None,
    project: str = "default",
) -> int:
    """Store a memory. Returns the new memory id.

    Raises ValueError if kind is not in the allowed set.
    """
    if kind not in _VALID_KINDS:
        raise ValueError(
            f"Invalid kind: {kind!r}. Must be one of {_VALID_KINDS}"
        )
    meta_json = json.dumps(meta or {})
    cur = conn.execute(
        "INSERT INTO memories(kind, body, project, meta) VALUES (?, ?, ?, ?)",
        (kind, body, project, meta_json),
    )
    conn.commit()
    return int(cur.lastrowid)


# --- recall ---


def _bm25_to_rank(bm25: float) -> float:
    """Same transform as knowledge.search — see comments there."""
    if bm25 >= 0:
        return 0.0
    return abs(bm25) / (abs(bm25) + 5.0)


def recall(
    conn,
    query: str = "",
    kind: str | None = None,
    project: str | None = None,
    limit: int = 10,
) -> list[MemoryHit]:
    """Recall memories by FTS5 query, with optional kind/project filters.

    If query is empty, returns the most recent memories (no ranking).
    """
    if limit <= 0:
        return []

    if query.strip():
        terms = [t for t in re.split(r"\W+", query) if t]
        if not terms:
            return _recent(conn, kind, project, limit)
        fts_query = " ".join(f'"{t}"' for t in terms)

        sql = (
            "SELECT m.id AS id, m.kind AS kind, m.body AS body, "
            "       m.created_at AS created_at, "
            "       bm25(memories_fts) AS bm "
            "FROM memories_fts "
            "JOIN memories m ON m.id = memories_fts.rowid "
            "WHERE memories_fts MATCH ? "
        )
        args: list = [fts_query]
        if kind is not None:
            sql += "AND m.kind = ? "
            args.append(kind)
        if project is not None:
            sql += "AND m.project = ? "
            args.append(project)
        sql += "ORDER BY bm25(memories_fts) LIMIT ?"
        args.append(limit)

        rows = conn.execute(sql, args).fetchall()
        return [
            MemoryHit(
                id=int(r["id"]),
                kind=r["kind"],
                body=r["body"],
                created_at=r["created_at"],
                rank=_bm25_to_rank(float(r["bm"])),
            )
            for r in rows
        ]

    return _recent(conn, kind, project, limit)


def _recent(conn, kind, project, limit) -> list[MemoryHit]:
    sql = "SELECT id, kind, body, created_at FROM memories WHERE 1=1"
    args: list = []
    if kind is not None:
        sql += " AND kind = ?"
        args.append(kind)
    if project is not None:
        sql += " AND project = ?"
        args.append(project)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    rows = conn.execute(sql, args).fetchall()
    return [
        MemoryHit(
            id=int(r["id"]),
            kind=r["kind"],
            body=r["body"],
            created_at=r["created_at"],
            rank=0.0,
        )
        for r in rows
    ]


# --- list helpers used by tests ---


def count(conn, project: str | None = None) -> int:
    if project is None:
        return int(conn.execute("SELECT COUNT(*) AS n FROM memories").fetchone()["n"])
    return int(
        conn.execute("SELECT COUNT(*) AS n FROM memories WHERE project = ?", (project,))
        .fetchone()["n"]
    )


def valid_kinds() -> tuple[str, ...]:
    return _VALID_KINDS
