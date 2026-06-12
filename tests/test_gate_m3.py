"""Gate test for Milestone 3 — Workflow Engine.

Gate: register + run a 3-step workflow, all steps visible in audit log.
"""

from __future__ import annotations

import json
import pytest

from archonos.core import ops
from archonos.workflows import ops as wf_ops
from archonos.storage import db


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    ops.init()
    return tmp_path


@pytest.fixture
def conn(isolated_home):
    c = db.get_connection()
    yield c
    c.close()


SAMPLE_SPEC = {
    "name": "test-workflow",
    "description": "Three step test workflow",
    "steps": [
        {"name": "step_one", "action": "log", "args": {"message": "Starting"}},
        {"name": "step_two", "action": "log", "args": {"message": "Processing"}},
        {"name": "step_three", "action": "log", "args": {"message": "Done"}},
    ]
}


def test_register_workflow(conn):
    wf_id = wf_ops.register(conn, "test-workflow", SAMPLE_SPEC)
    assert wf_id is not None
    assert isinstance(wf_id, int)


def test_register_idempotent(conn):
    id1 = wf_ops.register(conn, "test-workflow", SAMPLE_SPEC)
    id2 = wf_ops.register(conn, "test-workflow", SAMPLE_SPEC)
    assert id1 == id2  # same workflow upserted


def test_register_increments_version(conn):
    wf_ops.register(conn, "test-workflow", SAMPLE_SPEC)
    updated_spec = {**SAMPLE_SPEC, "description": "Updated"}
    wf_ops.register(conn, "test-workflow", updated_spec)
    wf = wf_ops.get_workflow(conn, "test-workflow")
    assert wf.version == 2


def test_list_workflows(conn):
    wf_ops.register(conn, "workflow-a", SAMPLE_SPEC)
    wf_ops.register(conn, "workflow-b", SAMPLE_SPEC)
    workflows = wf_ops.list_workflows(conn)
    names = [w.name for w in workflows]
    assert "workflow-a" in names
    assert "workflow-b" in names


def test_get_workflow(conn):
    wf_ops.register(conn, "test-workflow", SAMPLE_SPEC)
    wf = wf_ops.get_workflow(conn, "test-workflow")
    assert wf is not None
    assert wf.name == "test-workflow"
    spec = json.loads(wf.spec)
    assert len(spec["steps"]) == 3


def test_get_workflow_not_found(conn):
    wf = wf_ops.get_workflow(conn, "nonexistent")
    assert wf is None


def test_run_workflow_returns_id(conn):
    wf_ops.register(conn, "test-workflow", SAMPLE_SPEC)
    run_id = wf_ops.run_workflow(conn, "test-workflow")
    assert isinstance(run_id, int)


def test_run_workflow_status_succeeded(conn):
    wf_ops.register(conn, "test-workflow", SAMPLE_SPEC)
    run_id = wf_ops.run_workflow(conn, "test-workflow")
    runs = wf_ops.list_runs(conn)
    run = next((r for r in runs if r.id == run_id), None)
    assert run is not None
    assert run.status == "succeeded"


def test_run_workflow_audit_log(conn):
    wf_ops.register(conn, "test-workflow", SAMPLE_SPEC)
    run_id = wf_ops.run_workflow(conn, "test-workflow")
    runs = wf_ops.list_runs(conn)
    run = next(r for r in runs if r.id == run_id)
    log = json.loads(run.log)
    assert len(log) > 0
    # All 3 steps should appear in the log
    step_names = [e.get("step") for e in log if "step" in e]
    assert "step_one" in step_names
    assert "step_two" in step_names
    assert "step_three" in step_names


def test_run_workflow_not_found(conn):
    with pytest.raises(ValueError, match="not found"):
        wf_ops.run_workflow(conn, "nonexistent")


def test_list_runs(conn):
    wf_ops.register(conn, "test-workflow", SAMPLE_SPEC)
    wf_ops.run_workflow(conn, "test-workflow")
    wf_ops.run_workflow(conn, "test-workflow")
    runs = wf_ops.list_runs(conn)
    assert len(runs) >= 2


def test_status_reflects_workflows(conn):
    wf_ops.register(conn, "test-workflow", SAMPLE_SPEC)
    wf_ops.run_workflow(conn, "test-workflow")
    conn.close()
    s = ops.status()
    assert s.workflows == 1
    assert s.workflow_runs == 1
