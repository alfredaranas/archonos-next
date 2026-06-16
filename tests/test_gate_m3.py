"""Gate test for Milestone 3 — Workflow Engine.

The gate (per docs/BASE_PLAN.md M3):
    register + run a 3-step workflow; run visible in audit trail.

Per docs/architecture/CORE_ARCHITECTURE.md §3 (workflow primitive):
    - JSON spec with typed steps
    - Closed step-type registry (import, search, remember, recall, shell, ask)
    - Templating: {{params.x}} and {{steps.<id>.<key>}} only
    - Sequential, fail-fast, audited
Per §4: workflows/registry.py, workflows/engine.py, workflows/steps.py
Per §7: gate test IS the definition of done.
"""

from __future__ import annotations

import json

import pytest

from archonos.cli.main import main
from archonos.core import ops
from archonos.storage import db
from archonos.workflows import engine as wf_engine
from archonos.workflows import registry as wf_registry
from archonos.workflows import steps as wf_steps


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    ops.init()
    return tmp_path


# --- registry: §4 contract ---


def test_register_workflow_returns_id(isolated_home):
    spec = {
        "name": "test",
        "description": "trivial workflow",
        "steps": [{"id": "s1", "type": "ask", "args": {"prompt": "hi"}}],
    }
    conn = db.get_connection()
    try:
        wf_id = wf_registry.register(conn, "test", spec)
    finally:
        conn.close()
    assert wf_id > 0


def test_register_replaces_existing_workflow_bumps_version(isolated_home):
    spec1 = {"steps": [{"id": "s1", "type": "ask", "args": {}}]}
    spec2 = {"steps": [{"id": "s1", "type": "ask", "args": {}}, {"id": "s2", "type": "ask", "args": {}}]}
    conn = db.get_connection()
    try:
        wf_registry.register(conn, "wf", spec1)
        wf_registry.register(conn, "wf", spec2)
        wf = wf_registry.get(conn, "wf")
    finally:
        conn.close()
    assert wf.version == 2
    assert len(wf.spec["steps"]) == 2


def test_register_validates_spec_rejects_empty_steps(isolated_home):
    conn = db.get_connection()
    try:
        with pytest.raises(ValueError):
            wf_registry.register(conn, "bad", {"steps": []})
    finally:
        conn.close()


def test_register_validates_spec_rejects_duplicate_step_ids(isolated_home):
    spec = {
        "steps": [
            {"id": "s1", "type": "ask", "args": {}},
            {"id": "s1", "type": "ask", "args": {}},
        ]
    }
    conn = db.get_connection()
    try:
        with pytest.raises(ValueError):
            wf_registry.register(conn, "bad", spec)
    finally:
        conn.close()


def test_register_validates_spec_rejects_missing_step_fields(isolated_home):
    conn = db.get_connection()
    try:
        with pytest.raises(ValueError):
            wf_registry.register(conn, "bad", {"steps": [{"type": "ask"}]})  # no id
        with pytest.raises(ValueError):
            wf_registry.register(conn, "bad", {"steps": [{"id": "s1"}]})  # no type
    finally:
        conn.close()


def test_get_returns_none_for_missing_workflow(isolated_home):
    conn = db.get_connection()
    try:
        assert wf_registry.get(conn, "nope") is None
        with pytest.raises(LookupError):
            wf_registry.get_or_404(conn, "nope")
    finally:
        conn.close()


def test_list_workflows_returns_all(isolated_home):
    conn = db.get_connection()
    try:
        wf_registry.register(conn, "a", {"steps": [{"id": "s1", "type": "ask", "args": {}}]})
        wf_registry.register(conn, "b", {"steps": [{"id": "s1", "type": "ask", "args": {}}]})
        wfs = wf_registry.list_(conn)
    finally:
        conn.close()
    names = [w.name for w in wfs]
    assert set(names) == {"a", "b"}


# --- step registry: §3.2 ---


def test_step_registry_has_closed_v1_set(isolated_home):
    # M3 shipped 6 step types. M6 added 'fetch' for paper sources.
    # The set is closed in v1: adding a step type is a code + test change.
    expected = {"import", "search", "remember", "recall", "shell", "ask", "fetch"}
    assert set(wf_steps.STEP_REGISTRY) == expected


def test_resolve_step_rejects_unknown_type(isolated_home):
    with pytest.raises(KeyError):
        wf_steps.resolve_step("not_a_real_type")


# --- templating: §3.3 ---


def test_templating_substitutes_params(isolated_home):
    from archonos.workflows.engine import resolve_template
    out = resolve_template(
        "hello {{params.name}}",
        params={"name": "world"},
        step_outputs={},
    )
    assert out == "hello world"


def test_templating_substitutes_step_outputs(isolated_home):
    from archonos.workflows.engine import resolve_template
    out = resolve_template(
        "found {{steps.s1.count}} results",
        params={},
        step_outputs={"s1": {"count": 5, "summary": "ok"}},
    )
    assert out == "found 5 results"


def test_templating_recurses_into_dicts_and_lists(isolated_home):
    from archonos.workflows.engine import resolve_template
    out = resolve_template(
        {"greeting": "hi {{params.name}}", "tags": ["{{params.a}}", "{{params.b}}"]},
        params={"name": "x", "a": "1", "b": "2"},
        step_outputs={},
    )
    assert out == {"greeting": "hi x", "tags": ["1", "2"]}


def test_templating_rejects_unknown_root(isolated_home):
    from archonos.workflows.engine import resolve_template
    with pytest.raises(ValueError):
        resolve_template("{{globals.x}}", params={}, step_outputs={})


def test_templating_rejects_missing_step_output(isolated_home):
    from archonos.workflows.engine import resolve_template
    with pytest.raises(KeyError):
        resolve_template(
            "{{steps.s1.value}}",
            params={},
            step_outputs={},  # s1 not yet executed
        )


# --- engine: §3.4, §4 ---


def test_run_three_step_workflow_succeeds(isolated_home):
    """THE M3 GATE: register + run a 3-step workflow; run visible in audit trail."""
    # Pre-create a doc so import is a no-op (testing the workflow mechanics, not import)
    docs = isolated_home / "corpus"
    docs.mkdir()
    (docs / "x.md").write_text(
        "# X\n\nPython is a language. Rust is a language. " * 20, encoding="utf-8"
    )

    spec = {
        "name": "import-and-brief",
        "description": "Import a folder, search a topic, save a memory",
        "params": {"folder": "string", "topic": "string"},
        "steps": [
            {"id": "s1", "type": "import",  "args": {"path": "{{params.folder}}"}},
            {"id": "s2", "type": "search",  "args": {"query": "{{params.topic}}", "k": 5}},
            {
                "id": "s3",
                "type": "remember",
                "args": {
                    "kind": "workflow_outcome",
                    "body": "Brief on {{params.topic}}: {{steps.s2.summary}}",
                },
            },
        ],
    }

    conn = db.get_connection()
    try:
        wf_registry.register(conn, "import-and-brief", spec)
        result = wf_engine.run(
            conn, "import-and-brief",
            {"folder": str(docs), "topic": "python"},
        )
    finally:
        conn.close()

    # Status
    assert result.ok, f"workflow failed: {result.log}"
    assert result.status == "succeeded"
    assert result.workflow_name == "import-and-brief"

    # Audit trail
    assert len(result.log) == 3
    assert [e["step"] for e in result.log] == ["s1", "s2", "s3"]
    assert all(e["status"] == "ok" for e in result.log)

    # Output keys are recorded
    assert "docs_added" in result.log[0]["output_keys"]
    assert "hits" in result.log[1]["output_keys"]
    assert "id" in result.log[2]["output_keys"]


def test_run_persists_run_to_workflow_runs_table(isolated_home):
    """Per §3.4: each run is auditable in the database."""
    # Use the search step (no provider required) instead of ask (which needs
    # a configured LLM provider since M6).
    spec = {"steps": [{"id": "s1", "type": "search", "args": {"query": "anything", "k": 3}}]}
    conn = db.get_connection()
    try:
        wf_registry.register(conn, "persist", spec)
        result = wf_engine.run(conn, "persist", {})
        # Read back from DB (not from in-memory result)
        from_db = wf_engine.get_run(conn, result.run_id)
    finally:
        conn.close()
    assert from_db is not None
    assert from_db.status == "succeeded"
    assert from_db.run_id == result.run_id
    assert len(from_db.log) == 1


def test_run_stops_on_first_failure(isolated_home):
    """Per §3.4: First failure stops the run, status=failed, partial log preserved."""
    spec = {
        "steps": [
            {"id": "s1", "type": "search", "args": {"query": "first", "k": 3}},
            # s2 references a non-existent path on purpose
            {
                "id": "s2",
                "type": "import",
                "args": {"path": "/this/path/does/not/exist/anywhere"},
            },
            {"id": "s3", "type": "search", "args": {"query": "never runs", "k": 3}},
        ]
    }
    conn = db.get_connection()
    try:
        wf_registry.register(conn, "fail-test", spec)
        result = wf_engine.run(conn, "fail-test", {})
    finally:
        conn.close()
    assert result.status == "failed"
    # s1 succeeded, s2 failed, s3 never ran
    assert [e["step"] for e in result.log] == ["s1", "s2"]
    assert result.log[0]["status"] == "ok"
    assert result.log[1]["status"] == "failed"
    assert result.log[1]["error"] is not None


def test_run_unknown_workflow_raises(isolated_home):
    conn = db.get_connection()
    try:
        with pytest.raises(LookupError):
            wf_engine.run(conn, "no-such-workflow", {})
    finally:
        conn.close()


def test_run_unknown_step_type_fails(isolated_home):
    spec = {"steps": [{"id": "s1", "type": "no_such_type", "args": {}}]}
    conn = db.get_connection()
    try:
        wf_registry.register(conn, "bad", spec)  # registration accepts (registry closed at runtime)
        result = wf_engine.run(conn, "bad", {})
    finally:
        conn.close()
    assert result.status == "failed"
    assert "Unknown step type" in result.log[0]["error"]


# --- shell step: §3.2 requires allow_shell=true in settings ---


def test_shell_step_blocked_by_default(isolated_home):
    spec = {"steps": [{"id": "s1", "type": "shell", "args": {"command": "echo hi"}}]}
    conn = db.get_connection()
    try:
        wf_registry.register(conn, "shell-blocked", spec)
        result = wf_engine.run(conn, "shell-blocked", {})
    finally:
        conn.close()
    assert result.status == "failed"
    assert "allow_shell" in result.log[0]["error"]


def test_shell_step_allowed_when_setting_present(isolated_home):
    conn = db.get_connection()
    try:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES ('allow_shell', 'true')"
        )
        conn.commit()
    finally:
        conn.close()

    spec = {
        "steps": [
            {"id": "s1", "type": "shell", "args": {"command": "echo hello-from-shell"}}
        ]
    }
    conn = db.get_connection()
    try:
        wf_registry.register(conn, "shell-ok", spec)
        result = wf_engine.run(conn, "shell-ok", {})
    finally:
        conn.close()
    assert result.ok
    # output keys contain stdout
    assert "stdout" in result.log[0]["output_keys"]
    assert "hello-from-shell" in result.log[0]["output"]["stdout"]


# --- remember/recall step types: M4 ops used in M3 step dispatch ---


def test_workflow_can_remember_and_recall(isolated_home):
    spec = {
        "steps": [
            {
                "id": "s1",
                "type": "remember",
                "args": {
                    "kind": "decision",
                    "body": "Chose SQLite for local-first storage",
                },
            },
            {
                "id": "s2",
                "type": "recall",
                "args": {"query": "SQLite", "limit": 5},
            },
        ]
    }
    conn = db.get_connection()
    try:
        wf_registry.register(conn, "mem-test", spec)
        result = wf_engine.run(conn, "mem-test", {})
    finally:
        conn.close()
    assert result.ok
    # s1 produced an id, s2 produced hits
    assert "id" in result.log[0]["output_keys"]
    assert "hits" in result.log[1]["output_keys"]
    assert result.log[1]["output"]["count"] >= 1


# --- CLI: §5 ---


def test_cli_workflow_register(isolated_home):
    spec_path = isolated_home / "spec.json"
    spec_path.write_text(
        json.dumps(
            {"steps": [{"id": "s1", "type": "ask", "args": {"prompt": "x"}}]}
        ),
        encoding="utf-8",
    )
    assert main(["workflow", "register", "cli-test", str(spec_path)]) == 0


def test_cli_workflow_list(isolated_home):
    spec_path = isolated_home / "spec.json"
    spec_path.write_text(
        json.dumps({"steps": [{"id": "s1", "type": "ask", "args": {}}]}),
        encoding="utf-8",
    )
    main(["workflow", "register", "listme", str(spec_path)])
    assert main(["workflow", "list"]) == 0


def test_cli_workflow_run(isolated_home):
    spec_path = isolated_home / "spec.json"
    spec_path.write_text(
        json.dumps({"steps": [{"id": "s1", "type": "search", "args": {"query": "hi", "k": 3}}]}),
        encoding="utf-8",
    )
    main(["workflow", "register", "runme", str(spec_path)])
    assert main(["workflow", "run", "runme"]) == 0


def test_cli_workflow_log(isolated_home):
    spec_path = isolated_home / "spec.json"
    spec_path.write_text(
        json.dumps({"steps": [{"id": "s1", "type": "ask", "args": {"prompt": "x"}}]}),
        encoding="utf-8",
    )
    main(["workflow", "register", "logged", str(spec_path)])
    rc = main(["workflow", "run", "logged"])
    # Parse run id from output? Instead, list workflow_runs to find latest id
    conn = db.get_connection()
    try:
        rid = int(
            conn.execute("SELECT MAX(id) AS m FROM workflow_runs").fetchone()["m"]
        )
    finally:
        conn.close()
    assert main(["workflow", "log", str(rid)]) == 0


def test_cli_workflow_run_failed_workflow_exits_2(isolated_home):
    spec_path = isolated_home / "spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "id": "s1",
                        "type": "import",
                        "args": {"path": "/no/such/path/anywhere"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    main(["workflow", "register", "broken", str(spec_path)])
    assert main(["workflow", "run", "broken"]) == 2
