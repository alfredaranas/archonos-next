"""CLI helpers for the workflow scheduler.

New commands:
  archonos workflow schedule list
  archonos workflow schedule add NAME WORKFLOW "EXPR" [--param k=v ...]
  archonos workflow schedule remove NAME
  archonos workflow schedule enable NAME
  archonos workflow schedule disable NAME
  archonos scheduler run [--once]            # foreground loop (or one-shot for tests)

Per BASE_PLAN.md, scheduled workflows are post-alpha polish.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from archonos import scheduler
from archonos.workflows import engine as wf_engine
from archonos.storage import db as storage_db


def _project_dir_for(args) -> "Path":  # type: ignore[no-untyped-def]
    """Resolve the project directory for the current CLI invocation."""
    from pathlib import Path
    from archonos.storage import db
    project = getattr(args, "project", "default") or "default"
    return db.project_dir(project)


def _cmd_schedule_list(args: argparse.Namespace) -> int:
    pdir = _project_dir_for(args)
    scheds = scheduler.load_schedules(pdir)
    if not scheds:
        print("No schedules.")
        return 0
    for s in scheds:
        flag = "  on " if s.enabled else "  off"
        print(f"{s.name:24s} {flag}  workflow={s.workflow:20s}  cron={s.schedule!r:18s}  next={s.next_run or '(none)'}")
    return 0


def _cmd_schedule_add(args: argparse.Namespace) -> int:
    pdir = _project_dir_for(args)
    params = {}
    for kv in args.param or []:
        if "=" not in kv:
            print(f"--param must be key=value: {kv!r}", file=sys.stderr)
            return 1
        k, v = kv.split("=", 1)
        params[k] = v
    sched = scheduler.Schedule(
        name=args.name,
        workflow=args.workflow,
        schedule=args.expr,
        params=params,
        enabled=True,
    )
    # Validate cron now so the user gets an immediate error
    try:
        scheduler._parse_cron(args.expr)  # type: ignore[attr-defined]
    except ValueError as e:
        print(f"invalid cron expression: {e}", file=sys.stderr)
        return 1
    scheduler.upsert_schedule(pdir, sched)
    print(f"Schedule '{args.name}' added (workflow={args.workflow}, cron={args.expr!r})")
    # Print computed next_run
    scheds = scheduler.load_schedules(pdir)
    for s in scheds:
        if s.name == args.name:
            print(f"Next run: {s.next_run}")
    return 0


def _cmd_schedule_remove(args: argparse.Namespace) -> int:
    pdir = _project_dir_for(args)
    if scheduler.remove_schedule(pdir, args.name):
        print(f"Schedule '{args.name}' removed.")
        return 0
    print(f"Schedule '{args.name}' not found.", file=sys.stderr)
    return 1


def _cmd_schedule_enable(args: argparse.Namespace, enabled: bool) -> int:
    pdir = _project_dir_for(args)
    scheds = scheduler.load_schedules(pdir)
    for s in scheds:
        if s.name == args.name:
            s.enabled = enabled
            scheduler.upsert_schedule(pdir, s)
            state = "enabled" if enabled else "disabled"
            print(f"Schedule '{args.name}' {state}.")
            return 0
    print(f"Schedule '{args.name}' not found.", file=sys.stderr)
    return 1


def _cmd_scheduler_run(args: argparse.Namespace) -> int:
    """The scheduler loop. --once runs all currently-due schedules and exits.
    Without --once, it loops forever (or until interrupted)."""
    pdir = _project_dir_for(args)
    project = getattr(args, "project", "default") or "default"
    once = getattr(args, "once", False)
    interval = int(getattr(args, "poll_seconds", 30) or 30)

    print(f"Scheduler running for project '{project}' (poll={interval}s, once={once})", file=sys.stderr)
    while True:
        due = scheduler.find_due(pdir)
        for s in due:
            print(f"[{datetime.now().isoformat()}] running '{s.name}' -> workflow '{s.workflow}'", file=sys.stderr)
            try:
                conn = storage_db.get_connection(project)
            except FileNotFoundError:
                print(f"  no database — run `archonos init` first", file=sys.stderr)
                continue
            try:
                try:
                    result = wf_engine.run(conn, s.workflow, s.params)
                except Exception as e:
                    print(f"  workflow raised: {type(e).__name__}: {e}", file=sys.stderr)
                    continue
            finally:
                conn.close()
            status_word = "ok" if result.ok else result.status
            print(f"  run {result.run_id}: {status_word} ({len(result.log)} steps)", file=sys.stderr)
            scheduler.mark_run(pdir, s.name)
        if once:
            break
        time.sleep(interval)
    return 0
