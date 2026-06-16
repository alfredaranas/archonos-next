"""Tests for Tier 2 polish features.

Covers:
  - PDF import (best-effort, both pdfminer path and stdlib fallback)
  - .archonosignore support
  - Cron expression parser + scheduler (workflow schedule add/list/remove)
  - Scheduler run loop
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from archonos import scheduler
from archonos.cli.main import main
from archonos.core import ops
from archonos.knowledge import import_ as kb_import
from archonos.knowledge.import_ import (
    _extract_pdf_text,
    _is_ignored,
    _load_ignore_patterns,
)
from archonos.storage import db
from archonos.workflows import engine as wf_engine
from archonos.workflows import registry as wf_registry


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    ops.init()
    return tmp_path


# --- .archonosignore ---


def test_archonosignore_missing_returns_empty(tmp_path):
    assert _load_ignore_patterns(tmp_path) == []


def test_archonosignore_loads_patterns(tmp_path):
    (tmp_path / ".archonosignore").write_text(
        "# a comment\n\n"
        "*.tmp\n"
        "build/\n"
        "secret-*.md\n"
    )
    patterns = _load_ignore_patterns(tmp_path)
    assert patterns == ["*.tmp", "build/", "secret-*.md"]


def test_archonosignore_matches_filename(tmp_path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "notes" / "a.tmp").write_text("tmp", encoding="utf-8")
    patterns = ["*.tmp"]
    assert _is_ignored(tmp_path / "notes" / "a.tmp", tmp_path, patterns)
    assert not _is_ignored(tmp_path / "notes" / "a.md", tmp_path, patterns)


def test_archonosignore_matches_directory_name(tmp_path):
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "out.md").write_text("out", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.md").write_text("a", encoding="utf-8")
    assert _is_ignored(tmp_path / "build" / "out.md", tmp_path, ["build"])
    assert not _is_ignored(tmp_path / "src" / "a.md", tmp_path, ["build"])


def test_import_path_honors_archonosignore(isolated_home):
    docs = isolated_home / "docs"
    docs.mkdir()
    (docs / "keep.md").write_text("# keep\n\nkeep me", encoding="utf-8")
    # An .md file that WOULD be imported but is excluded by the ignore
    (docs / "skip-this.md").write_text("# skip\n\nskip me", encoding="utf-8")
    (docs / "draft.md").write_text("# draft\n\ndraft", encoding="utf-8")
    (docs / ".archonosignore").write_text("skip-this.md\n")

    conn = db.get_connection()
    try:
        report = kb_import.import_path(conn, docs)
    finally:
        conn.close()
    assert report.docs_added == 2  # keep.md, draft.md
    assert report.skipped_ignored == 1
    assert report.skipped_dupes == 0


def test_import_path_can_disable_archonosignore(isolated_home):
    docs = isolated_home / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("a", encoding="utf-8")
    (docs / "b.md").write_text("b", encoding="utf-8")
    (docs / ".archonosignore").write_text("b.md\n")

    conn = db.get_connection()
    try:
        # honor_ignore=False: the ignore file is bypassed
        report = kb_import.import_path(conn, docs, honor_ignore=False)
    finally:
        conn.close()
    assert report.docs_added == 2
    assert report.skipped_ignored == 0


# --- PDF import ---


def _make_minimal_pdf(path: Path) -> None:
    """Write a minimal hand-crafted PDF with a single Tj text operation.

    This PDF is intentionally tiny so we don't need a real PDF library
    for the test. It has a parenthesized text string that the stdlib
    fallback should extract.
    """
    content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 70 >>
stream
BT /F1 12 Tf 100 700 Td (Hello ArchonOS PDF test content) Tj ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000056 00000 n
0000000103 00000 n
0000000202 00000 n
trailer
<< /Size 5 /Root 1 0 R >>
startxref
320
%%EOF
"""
    path.write_bytes(content)


def test_pdf_import_with_minimal_pdf(isolated_home):
    f = isolated_home / "test.pdf"
    _make_minimal_pdf(f)
    conn = db.get_connection()
    try:
        report = kb_import.import_path(conn, f)
    finally:
        conn.close()
    # Either pdfminer is installed and we get a real extraction, or
    # the stdlib fallback finds the Tj text. In either case the file
    # should import.
    assert report.docs_added == 1
    assert report.errors == []


def test_pdf_import_handles_image_only_pdf_with_helpful_error(isolated_home, tmp_path):
    """A PDF with no extractable text surfaces the helpful install hint."""
    # Write a malformed PDF (no text streams at all)
    f = isolated_home / "scanned.pdf"
    f.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
                  b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
                  b"xref\n0 3\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n"
                  b"\ntrailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n95\n%%EOF\n")
    conn = db.get_connection()
    try:
        report = kb_import.import_path(conn, f)
    finally:
        conn.close()
    # Either pdfminer handles it (unlikely) or stdlib fallback surfaces
    # a clear error mentioning pdfminer.six.
    if report.docs_added == 0:
        assert len(report.errors) == 1
        assert "pdfminer.six" in report.errors[0]


# --- cron expression parser ---


def test_cron_parse_minute_field():
    assert scheduler._parse_field("*/15", 0, 59) == {0, 15, 30, 45}
    assert scheduler._parse_field("0", 0, 59) == {0}
    assert scheduler._parse_field("1,3,5", 0, 59) == {1, 3, 5}
    assert scheduler._parse_field("0-23", 0, 59) == set(range(0, 24))


def test_cron_parse_field_out_of_range_raises():
    with pytest.raises(ValueError):
        scheduler._parse_field("99", 0, 59)


def test_cron_parse_wrong_field_count_raises():
    with pytest.raises(ValueError):
        scheduler._parse_cron("0 9 * *")  # only 4 fields
    with pytest.raises(ValueError):
        scheduler._parse_cron("0 9 * * * *")  # 6 fields


def test_cron_matches_specific_time():
    cron = scheduler._parse_cron("30 9 * * *")
    dt = datetime(2026, 6, 16, 9, 30)  # June 16 2026, 9:30am
    assert scheduler.matches(cron, dt)
    assert not scheduler.matches(cron, dt.replace(minute=31))
    assert not scheduler.matches(cron, dt.replace(hour=10))


def test_cron_matches_weekdays():
    # 0 9 * * 1-5 = 9am Mon-Fri
    cron = scheduler._parse_cron("0 9 * * 1-5")
    # 2026-06-15 is a Monday
    assert scheduler.matches(cron, datetime(2026, 6, 15, 9, 0))
    # 2026-06-16 is a Tuesday
    assert scheduler.matches(cron, datetime(2026, 6, 16, 9, 0))
    # 2026-06-14 is a Sunday
    assert not scheduler.matches(cron, datetime(2026, 6, 14, 9, 0))


def test_cron_next_run_after():
    cron = scheduler._parse_cron("0 9 * * *")
    # Before 9am, next run is today at 9am
    next1 = scheduler.next_run_after(cron, datetime(2026, 6, 16, 8, 0))
    assert next1 == datetime(2026, 6, 16, 9, 0)
    # After 9am, next run is tomorrow
    next2 = scheduler.next_run_after(cron, datetime(2026, 6, 16, 9, 30))
    assert next2 == datetime(2026, 6, 17, 9, 0)


# --- schedule CRUD + scheduler ---


def test_schedule_upsert_and_load(tmp_path):
    pdir = tmp_path
    s = scheduler.Schedule(
        name="morning", workflow="brief", schedule="0 9 * * *", enabled=True
    )
    scheduler.upsert_schedule(pdir, s)
    loaded = scheduler.load_schedules(pdir)
    assert len(loaded) == 1
    assert loaded[0].name == "morning"
    assert loaded[0].next_run is not None


def test_schedule_remove(tmp_path):
    pdir = tmp_path
    scheduler.upsert_schedule(pdir, scheduler.Schedule(
        name="a", workflow="wf", schedule="0 9 * * *", enabled=True
    ))
    scheduler.upsert_schedule(pdir, scheduler.Schedule(
        name="b", workflow="wf", schedule="0 10 * * *", enabled=True
    ))
    assert scheduler.remove_schedule(pdir, "a") is True
    assert scheduler.remove_schedule(pdir, "a") is False
    assert len(scheduler.load_schedules(pdir)) == 1


def test_find_due_picks_up_overdue(isolated_home):
    # Add a schedule with a past next_run manually
    scheds = [
        scheduler.Schedule(
            name="overdue", workflow="any",
            schedule="0 9 * * *", enabled=True,
            next_run=(datetime.now() - timedelta(hours=1)).isoformat(),
        ),
        scheduler.Schedule(
            name="future", workflow="any",
            schedule="0 9 * * *", enabled=True,
            next_run=(datetime.now() + timedelta(hours=1)).isoformat(),
        ),
        scheduler.Schedule(
            name="disabled-overdue", workflow="any",
            schedule="0 9 * * *", enabled=False,
            next_run=(datetime.now() - timedelta(hours=1)).isoformat(),
        ),
    ]
    scheduler.save_schedules(scheduler.project_dir(isolated_home, "default") if False else __import__("archonos.storage.db", fromlist=["project_dir"]).project_dir("default"), scheds)
    pdir = db.project_dir("default")
    scheduler.save_schedules(pdir, scheds)
    due = scheduler.find_due(pdir)
    names = {s.name for s in due}
    assert "overdue" in names
    assert "future" not in names
    assert "disabled-overdue" not in names


# --- CLI: workflow schedule add / list / remove ---


def test_cli_workflow_schedule_add_list_remove(isolated_home):
    # Register a workflow first (so the schedule references a real one)
    spec = {"steps": [{"id": "s1", "type": "search", "args": {"query": "x", "k": 1}}]}
    spec_path = isolated_home / "wf.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    main(["workflow", "register", "my-wf", str(spec_path)])

    assert main(["workflow", "schedule", "add", "test-sched", "my-wf", "0 9 * * *"]) == 0
    assert main(["workflow", "schedule", "list"]) == 0
    assert main(["workflow", "schedule", "remove", "test-sched"]) == 0
    assert main(["workflow", "schedule", "remove", "nonexistent"]) == 1


def test_cli_workflow_schedule_rejects_bad_cron(isolated_home):
    spec = {"steps": [{"id": "s1", "type": "search", "args": {"query": "x", "k": 1}}]}
    spec_path = isolated_home / "wf.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    main(["workflow", "register", "my-wf", str(spec_path)])
    # 4 fields is not a valid cron
    assert main(["workflow", "schedule", "add", "bad", "my-wf", "0 9 * *"]) == 1


# --- CLI: scheduler run --once ---


def test_cli_scheduler_run_once_runs_due_workflow(isolated_home):
    # Register a workflow
    spec = {"steps": [{"id": "s1", "type": "search", "args": {"query": "test", "k": 1}}]}
    spec_path = isolated_home / "wf.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    main(["workflow", "register", "sched-wf", str(spec_path)])

    # Insert a schedule whose next_run is in the past
    pdir = db.project_dir("default")
    s = scheduler.Schedule(
        name="overdue-wf", workflow="sched-wf",
        schedule="0 9 * * *", enabled=True,
        next_run=(datetime.now() - timedelta(minutes=1)).isoformat(),
    )
    scheduler.save_schedules(pdir, [s])

    # Run --once: should execute the workflow
    rc = main(["scheduler", "run", "--once"])
    assert rc == 0

    # The workflow should have been run; check the audit log
    conn = db.get_connection()
    try:
        n_runs = int(
            conn.execute("SELECT COUNT(*) AS n FROM workflow_runs").fetchone()["n"]
        )
    finally:
        conn.close()
    assert n_runs == 1

    # Schedule's next_run should be advanced
    updated = scheduler.load_schedules(pdir)[0]
    assert updated.last_run is not None
    assert updated.next_run > datetime.now().isoformat()[:16]  # later than now
