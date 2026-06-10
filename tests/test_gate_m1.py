"""Gate test for Milestone 1 — CLI kernel.

The gate: init/status/healthcheck all exit 0 on a fresh home; init is idempotent.
"""

from __future__ import annotations

import pytest

from archonos.cli.main import main
from archonos.core import ops


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    return tmp_path


def test_init_creates_db(isolated_home):
    r = ops.init()
    assert r.created
    assert (isolated_home / "default" / "archonos.db").exists()
    assert r.migrations_applied == [1]


def test_init_idempotent():
    ops.init()
    r2 = ops.init()
    assert not r2.created
    assert r2.migrations_applied == []


def test_status_counts_zero_on_fresh_project():
    ops.init()
    s = ops.status()
    assert s.schema_version == 1
    assert (s.documents, s.chunks, s.memories, s.workflows, s.workflow_runs) == (0, 0, 0, 0, 0)


def test_status_fails_before_init():
    with pytest.raises(FileNotFoundError):
        ops.status()


def test_healthcheck_all_green_after_init():
    ops.init()
    h = ops.healthcheck()
    assert h.ok, [f"{c.name}: {c.detail}" for c in h.checks if not c.ok]
    assert {c.name for c in h.checks} == {
        "db_reachable", "schema_version", "write_test", "fts_tables", "disk_space",
    }


def test_cli_exit_codes():
    assert main(["init"]) == 0
    assert main(["status"]) == 0
    assert main(["healthcheck"]) == 0


def test_cli_status_before_init_is_user_error(isolated_home, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(isolated_home / "fresh"))
    assert main(["status"]) == 1
