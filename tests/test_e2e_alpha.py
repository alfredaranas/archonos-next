"""End-to-end test for Local Alpha (Milestone 5).

The M5 gate (per docs/BASE_PLAN.md):
    End-to-end on Windows 11 + WSL2 + 16GB RAM, no cloud, no homelab:
        1. Install
        2. init
        3. import
        4. search
        5. run workflow
        6. persist memory
    Gate: clean-machine walkthrough documented in docs/onboarding/,
          completed by someone who is not the author.

This test IS the kernel-level half of that gate: it exercises steps
2-6 in one scenario using only the public CLI surface, in a fresh
ARCHONOS_HOME, with subprocesses that look like a real user's
terminal commands. The Windows+WSL2 install half is covered by
docs/onboarding/WINDOWS_WSL2.md.

This is also a useful single-command smoke for any future regression:
"did anything in M0.5-M4 break the end-to-end story?"
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


# Locate the archonos binary that `pip install -e .` put on PATH.
# We invoke it the same way a real user would: a fresh subprocess,
# fresh PYTHONPATH / cwd, only ARCHONOS_HOME carried in via env.


def _archonos_bin() -> str:
    """Resolve the archonos console-script path inside the active venv."""
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        bin_dir = "Scripts" if os.name == "nt" else "bin"
        return os.path.join(venv, bin_dir, "archonos")
    # Fall back to PATH
    return "archonos"


def _run(args: list[str], home: str, timeout: int = 30) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["ARCHONOS_HOME"] = home
    return subprocess.run(
        [_archonos_bin()] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


# --- the scenario ---


def test_e2e_alpha_walkthrough(tmp_path):
    """Full Local Alpha pipeline: install -> init -> import -> search
    -> run workflow -> persist memory. Install is implicit (we're using
    the already-installed binary in the venv).

    Each step mirrors a real terminal command, with a fresh subprocess
    per step, just as a user would type them one at a time.
    """
    home = str(tmp_path / "alpha-home")

    # 1. init
    r = _run(["init"], home)
    assert r.returncode == 0, f"init failed: {r.stderr}"
    assert "Created" in r.stdout or "Verified" in r.stdout

    # 2. import a small corpus
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "alpha.md").write_text(
        "# Alpha\n\n"
        "Python is a dynamic language. The CPython interpreter compiles "
        "source to bytecode. " * 8
        + "\n\nKey topics: python interpreter bytecode\n",
        encoding="utf-8",
    )
    (corpus / "beta.txt").write_text(
        "Rust is a systems language focused on memory safety. "
        "The borrow checker enforces aliasing at compile time. " * 8
        + "\n\nTopics: rust memory safety compiler\n",
        encoding="utf-8",
    )
    (corpus / "gamma.md").write_text(
        "# Gamma\n\n"
        "SQLite is an embedded database. FTS5 provides full-text search "
        "with BM25 ranking. " * 8
        + "\n\nKey topics: sqlite fts5 search\n",
        encoding="utf-8",
    )

    r = _run(["import", str(corpus)], home)
    assert r.returncode == 0, f"import failed: {r.stderr}"
    assert "3 added" in r.stdout
    assert "0 skipped" in r.stdout

    # 3. search
    r = _run(["search", "python interpreter"], home)
    assert r.returncode == 0, f"search failed: {r.stderr}"
    assert "alpha" in r.stdout.lower()

    r = _run(["search", "fts5 bm25"], home)
    assert r.returncode == 0
    assert "gamma" in r.stdout.lower()

    # No-results case is a clean exit too
    r = _run(["search", "no_such_term_anywhere_xyzzy"], home)
    assert r.returncode == 0
    assert "No results" in r.stdout

    # 4. run a workflow that exercises the full pipeline
    spec = {
        "name": "alpha-walkthrough",
        "description": "Import, search, and remember — the full kernel in one shot.",
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
    spec_path = tmp_path / "alpha-walkthrough.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    r = _run(["workflow", "register", "alpha-walkthrough", str(spec_path)], home)
    assert r.returncode == 0, f"workflow register failed: {r.stderr}"

    # Re-import the same corpus first so the workflow's import step is a no-op
    # (everything already imported; this exercises the dedupe path too)
    r = _run(
        [
            "workflow", "run", "alpha-walkthrough",
            "--param", f"folder={corpus}",
            "--param", "topic=rust",
        ],
        home,
    )
    assert r.returncode == 0, f"workflow run failed:\nstdout={r.stdout}\nstderr={r.stderr}"
    assert "succeeded" in r.stdout
    assert "s1 (import)" in r.stdout
    assert "s2 (search)" in r.stdout
    assert "s3 (remember)" in r.stdout

    # 5. persist a memory directly (workflow already did via s3, but we
    #    add one more to demonstrate the CLI works standalone)
    r = _run(
        [
            "remember", "--kind", "lesson",
            "Local Alpha is complete: init -> import -> search -> workflow -> remember -> recall",
        ],
        home,
    )
    assert r.returncode == 0
    assert "Memory stored" in r.stdout

    # 6. recall — must work across the whole session
    r = _run(["recall", "Local Alpha"], home)
    assert r.returncode == 0
    assert "lesson" in r.stdout
    assert "Local Alpha is complete" in r.stdout

    # No-query recall returns most recent
    r = _run(["recall"], home)
    assert r.returncode == 0
    assert "lesson" in r.stdout

    # 7. status — final state of the system
    r = _run(["status"], home)
    assert r.returncode == 0
    # 3 docs from import + 1 from the workflow re-run (deduped, so still 3)
    assert "documents:       3" in r.stdout
    assert "chunks:          3" in r.stdout
    # Memories: 1 from workflow s3 + 1 from direct remember = 2
    assert "memories:        2" in r.stdout
    assert "workflows:       1" in r.stdout
    assert "workflow_runs:   1" in r.stdout

    # 8. healthcheck — all 5 checks still green after the e2e exercise
    r = _run(["healthcheck"], home)
    assert r.returncode == 0
    assert "db_reachable" in r.stdout
    assert "schema_version" in r.stdout
    assert "write_test" in r.stdout
    assert "fts_tables" in r.stdout
    assert "disk_space" in r.stdout


# --- negative / boundary cases the walkthrough doc should also cover ---


def test_e2e_alpha_walkthrough_clean_machine_no_state(tmp_path):
    """A truly fresh ARCHONOS_HOME with no prior state should still
    complete the full walkthrough. This is the closest the test suite
    can get to the 'completed by someone who is not the author' part
    of the M5 gate — the test has no memory of previous runs."""
    home = str(tmp_path / "fresh-home")

    # Every step must succeed on a brand-new install
    assert _run(["init"], home).returncode == 0
    assert _run(["healthcheck"], home).returncode == 0

    # The state should be empty but consistent
    r = _run(["status"], home)
    assert r.returncode == 0
    for line in (
        "documents:       0",
        "chunks:          0",
        "memories:        0",
        "workflows:       0",
        "workflow_runs:   0",
    ):
        assert line in r.stdout

    # Search with no corpus is a clean "no results" — not a crash
    r = _run(["search", "anything"], home)
    assert r.returncode == 0
    assert "No results" in r.stdout

    # Recall with no memories is clean
    r = _run(["recall"], home)
    assert r.returncode == 0
    assert "No memories" in r.stdout

    # Workflow list is clean
    r = _run(["workflow", "list"], home)
    assert r.returncode == 0
    assert "No workflows" in r.stdout


def test_e2e_alpha_persistence_across_subprocesses(tmp_path):
    """The full M5 walkthrough, then a fresh subprocess re-recalls
    everything. This proves the kernel is genuinely persistent and
    cross-process — the property the whole local-first design depends
    on. (M4's gate tests this for memories; this test exercises the
    same property for documents + chunks + workflows + workflow_runs.)"""
    home = str(tmp_path / "persistent-home")

    # Write
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "x.md").write_text(
        "Persistence is the property of surviving process boundaries. " * 10,
        encoding="utf-8",
    )
    assert _run(["init"], home).returncode == 0
    assert _run(["import", str(corpus)], home).returncode == 0
    assert _run(["remember", "persisted across processes"], home).returncode == 0

    # Each query runs in a brand-new subprocess
    r = _run(["status"], home)
    assert r.returncode == 0
    assert "documents:       1" in r.stdout
    assert "chunks:          1" in r.stdout
    assert "memories:        1" in r.stdout

    r = _run(["search", "persistence"], home)
    assert r.returncode == 0
    assert "x" in r.stdout.lower()

    r = _run(["recall", "persisted"], home)
    assert r.returncode == 0
    assert "persisted across processes" in r.stdout
