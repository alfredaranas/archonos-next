"""Workflow registry for ArchonOS.

Per docs/architecture/CORE_ARCHITECTURE.md §4:
    workflows/registry.py   register(conn, name, spec_json); get(conn, name); list_(conn)

Per §3: A workflow is a JSON document: ordered list of typed steps with
explicit inputs/outputs. Not YAML (no dep), not Python callables.

Public functions take/return dataclasses where appropriate. The raw spec
JSON is always stored as TEXT in the `workflows.spec` column.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass
class Workflow:
    id: int
    name: str
    spec: dict[str, Any]
    version: int
    created_at: str
    updated_at: str


def _parse_spec(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Workflow spec is not valid JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise ValueError("Workflow spec must be a JSON object")
    return parsed


def _validate_spec(spec: dict[str, Any]) -> None:
    """Validate a spec at registration time. Fail fast on malformed input."""
    if "steps" not in spec:
        raise ValueError("Workflow spec must contain a 'steps' list")
    steps = spec["steps"]
    if not isinstance(steps, list):
        raise ValueError("'steps' must be a list")
    if len(steps) == 0:
        raise ValueError("'steps' must not be empty")
    seen_ids: set[str] = set()
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"step[{i}] must be an object")
        if "id" not in step:
            raise ValueError(f"step[{i}] missing 'id'")
        if "type" not in step:
            raise ValueError(f"step[{i}] missing 'type'")
        sid = step["id"]
        if not isinstance(sid, str) or not sid:
            raise ValueError(f"step[{i}].id must be a non-empty string")
        if sid in seen_ids:
            raise ValueError(f"duplicate step id: {sid!r}")
        seen_ids.add(sid)
        stype = step["type"]
        if not isinstance(stype, str) or not stype:
            raise ValueError(f"step[{i}].type must be a non-empty string")
        if "args" in step and not isinstance(step["args"], dict):
            raise ValueError(f"step[{i}].args must be an object if present")


def register(conn, name: str, spec: dict[str, Any] | str) -> int:
    """Register a workflow. If a workflow with the same name exists, the
    version is bumped and `spec` is replaced.

    Returns the workflow id.
    """
    if isinstance(spec, str):
        spec = _parse_spec(spec)
    _validate_spec(spec)

    spec_json = json.dumps(spec, sort_keys=True)
    existing = conn.execute("SELECT id, version FROM workflows WHERE name = ?", (name,)).fetchone()

    if existing is None:
        cur = conn.execute(
            "INSERT INTO workflows(name, spec) VALUES (?, ?)",
            (name, spec_json),
        )
        conn.commit()
        return int(cur.lastrowid)

    new_version = int(existing["version"]) + 1
    conn.execute(
        "UPDATE workflows SET spec = ?, version = ?, updated_at = datetime('now') "
        "WHERE id = ?",
        (spec_json, new_version, existing["id"]),
    )
    conn.commit()
    return int(existing["id"])


def get(conn, name: str) -> Workflow | None:
    row = conn.execute(
        "SELECT id, name, spec, version, created_at, updated_at "
        "FROM workflows WHERE name = ?",
        (name,),
    ).fetchone()
    if row is None:
        return None
    return Workflow(
        id=int(row["id"]),
        name=row["name"],
        spec=_parse_spec(row["spec"]),
        version=int(row["version"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_(conn) -> list[Workflow]:
    rows = conn.execute(
        "SELECT id, name, spec, version, created_at, updated_at "
        "FROM workflows ORDER BY name"
    ).fetchall()
    return [
        Workflow(
            id=int(r["id"]),
            name=r["name"],
            spec=_parse_spec(r["spec"]),
            version=int(r["version"]),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


def get_or_404(conn, name: str) -> Workflow:
    wf = get(conn, name)
    if wf is None:
        raise LookupError(f"Workflow not found: {name!r}")
    return wf
