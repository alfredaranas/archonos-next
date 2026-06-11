"""Workflow operations — register, list, run."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime


@dataclass
class WorkflowSpec:
    id: int
    name: str
    spec: str
    version: int
    created_at: str
    updated_at: str


def register(
    conn: sqlite3.Connection,
    name: str,
    spec: dict
) -> int:
    """Register a workflow. Returns workflow id."""
    spec_json = json.dumps(spec)
    
    # Upsert
    existing = conn.execute(
        "SELECT id FROM workflows WHERE name = ?", (name,)
    ).fetchone()
    
    if existing:
        conn.execute(
            """UPDATE workflows SET spec = ?, version = version + 1, updated_at = datetime('now')
               WHERE name = ?""",
            (spec_json, name)
        )
        conn.commit()
        return existing["id"]
    
    cursor = conn.execute(
        """INSERT INTO workflows (name, spec) VALUES (?, ?)""",
        (name, spec_json)
    )
    conn.commit()
    return cursor.lastrowid


def list_workflows(conn: sqlite3.Connection) -> list[WorkflowSpec]:
    """List all registered workflows."""
    cursor = conn.execute(
        "SELECT id, name, spec, version, created_at, updated_at FROM workflows ORDER BY name"
    )
    return [
        WorkflowSpec(
            id=r["id"], name=r["name"], spec=r["spec"],
            version=r["version"], created_at=r["created_at"], updated_at=r["updated_at"]
        )
        for r in cursor.fetchall()
    ]


def get_workflow(conn: sqlite3.Connection, name: str) -> WorkflowSpec | None:
    """Get a workflow by name."""
    row = conn.execute(
        "SELECT id, name, spec, version, created_at, updated_at FROM workflows WHERE name = ?",
        (name,)
    ).fetchone()
    
    if not row:
        return None
    
    return WorkflowSpec(
        id=row["id"], name=row["name"], spec=row["spec"],
        version=row["version"], created_at=row["created_at"], updated_at=row["updated_at"]
    )


@dataclass
class WorkflowRun:
    id: int
    workflow_id: int
    status: str
    started_at: str
    finished_at: str | None
    log: str


def run_workflow(
    conn: sqlite3.Connection,
    name: str,
    params: dict | None = None
) -> int:
    """Execute a workflow. Returns run id."""
    wf = get_workflow(conn, name)
    if not wf:
        raise ValueError(f"Workflow not found: {name}")
    
    spec = json.loads(wf.spec)
    params = params or {}
    
    # Create run record
    cursor = conn.execute(
        """INSERT INTO workflow_runs (workflow_id, status) VALUES (?, 'running')""",
        (wf.id,)
    )
    run_id = cursor.lastrowid
    
    log = []
    
    try:
        # Execute steps
        for idx, step in enumerate(spec.get("steps", [])):
            step_name = step.get("name", f"step_{idx}")
            action = step.get("action")
            
            log.append({
                "step": step_name,
                "status": "started",
                "time": datetime.now().isoformat()
            })
            
            # For now, just log — actual execution would call external handlers
            log.append({
                "step": step_name,
                "status": "completed",
                "time": datetime.now().isoformat()
            })
        
        # Mark succeeded
        conn.execute(
            "UPDATE workflow_runs SET status = 'succeeded', finished_at = datetime('now') WHERE id = ?",
            (run_id,)
        )
    except Exception as e:
        log.append({"error": str(e), "time": datetime.now().isoformat()})
        conn.execute(
            "UPDATE workflow_runs SET status = 'failed', finished_at = datetime('now') WHERE id = ?",
            (run_id,)
        )
    
    # Update log
    conn.execute(
        "UPDATE workflow_runs SET log = ? WHERE id = ?",
        (json.dumps(log), run_id)
    )
    conn.commit()
    
    return run_id


def list_runs(conn: sqlite3.Connection, workflow_id: int | None = None) -> list[WorkflowRun]:
    """List workflow runs."""
    if workflow_id:
        cursor = conn.execute(
            """SELECT id, workflow_id, status, started_at, finished_at, log
               FROM workflow_runs WHERE workflow_id = ? ORDER BY started_at DESC""",
            (workflow_id,)
        )
    else:
        cursor = conn.execute(
            """SELECT id, workflow_id, status, started_at, finished_at, log
               FROM workflow_runs ORDER BY started_at DESC LIMIT 20"""
        )
    
    return [
        WorkflowRun(
            id=r["id"], workflow_id=r["workflow_id"], status=r["status"],
            started_at=r["started_at"], finished_at=r["finished_at"], log=r["log"]
        )
        for r in cursor.fetchall()
    ]