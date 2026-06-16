"""Workflow scheduler for ArchonOS (M6+ post-alpha polish).

A schedule is a JSON object stored in the workflows table's
`schedules` JSON column (or — for simplicity in v1 — in a small
JSON file at <project>/schedules.json). Each schedule is:
    {
      "name": "morning-brief",
      "workflow": "brief",          # the registered workflow name
      "schedule": "0 9 * * *",      # 5-field cron expression
      "params": {"topic": "python"},
      "enabled": true,
      "last_run": null,             # ISO datetime
      "next_run": "2026-06-16T09:00:00"
    }

The scheduler (`archonos scheduler run`):
  - Reads schedules from the project
  - Computes next_run for each (using stdlib datetime — no croniter dep)
  - Sleeps until the next pending run
  - Executes the workflow
  - Records the result
  - Loops

This module implements a minimal 5-field cron evaluator (minute
hour day-of-month month day-of-week). It supports:
  *           - any
  N           - exact
  N,M         - list
  N-M         - range
  */N         - step (every N)

It does NOT support:
  - 6-field cron (with seconds)
  - @reboot, @hourly shortcuts
  - year-bound schedules
  - L/W for last-weekday / last-day-of-month
These are documented as future extensions in the module docstring.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


SCHEDULES_FILENAME = "schedules.json"


# --- cron expression evaluation ---


def _parse_field(field_str: str, lo: int, hi: int) -> set[int]:
    """Parse one cron field (e.g. '*/15', '1,3,5', '0-23') into a set of ints."""
    out: set[int] = set()
    for part in field_str.split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if "/" in part:
            base, step_str = part.split("/", 1)
            step = int(step_str)
        else:
            base = part
        if base == "*" or base == "":
            start, end = lo, hi
        elif "-" in base:
            start_s, end_s = base.split("-", 1)
            start, end = int(start_s), int(end_s)
        else:
            val = int(base)
            if val < lo or val > hi:
                raise ValueError(f"cron field value {val} out of range [{lo}, {hi}]")
            out.add(val)
            continue
        # Apply range with step
        if start > end:
            # Wrap-around (e.g. 23-1 means 23,0,1)
            for v in range(start, hi + 1, step):
                out.add(v)
            for v in range(lo, end + 1, step):
                out.add(v)
        else:
            for v in range(start, end + 1, step):
                out.add(v)
    return out


def _parse_cron(expr: str) -> dict[str, set[int]]:
    """Parse a 5-field cron expression into a dict of {field: set_of_values}."""
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(
            f"cron expression must have 5 fields (got {len(parts)}): {expr!r}"
        )
    minute, hour, dom, month, dow = parts
    return {
        "minute": _parse_field(minute, 0, 59),
        "hour": _parse_field(hour, 0, 23),
        "dom": _parse_field(dom, 1, 31),
        "month": _parse_field(month, 1, 12),
        "dow": _parse_field(dow, 0, 6),  # 0 = Sunday
    }


def matches(cron: dict[str, set[int]], dt: datetime) -> bool:
    """True if the given datetime matches the parsed cron expression."""
    return (
        dt.minute in cron["minute"]
        and dt.hour in cron["hour"]
        and dt.day in cron["dom"]
        and dt.month in cron["month"]
        # Python: Monday=0..Sunday=6. Cron: Sunday=0..Saturday=6. Convert.
        and ((dt.weekday() + 1) % 7) in cron["dow"]
    )


def next_run_after(cron: dict[str, set[int]], dt: datetime) -> datetime:
    """Return the next datetime >= dt that matches the cron expression.

    Walks minute by minute; for a 5-field expression with reasonable
    constraints this converges in <1s for any reasonable horizon.
    """
    # Round up to the next minute
    candidate = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    # Bound the search to 366 days for safety (leap years)
    end = candidate + timedelta(days=366)
    while candidate < end:
        if matches(cron, candidate):
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError(f"no matching datetime within 366 days for {dt}")


# --- schedule storage ---


@dataclass
class Schedule:
    name: str
    workflow: str
    schedule: str
    params: dict = field(default_factory=dict)
    enabled: bool = True
    last_run: str | None = None
    next_run: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Schedule":
        return cls(
            name=d["name"],
            workflow=d["workflow"],
            schedule=d["schedule"],
            params=d.get("params") or {},
            enabled=d.get("enabled", True),
            last_run=d.get("last_run"),
            next_run=d.get("next_run"),
        )


def schedules_path(project_dir: Path) -> Path:
    return project_dir / SCHEDULES_FILENAME


def load_schedules(project_dir: Path) -> list[Schedule]:
    p = schedules_path(project_dir)
    if not p.is_file():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return [Schedule.from_dict(s) for s in data]


def save_schedules(project_dir: Path, schedules: list[Schedule]) -> None:
    p = schedules_path(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps([s.to_dict() for s in schedules], indent=2, sort_keys=True),
        encoding="utf-8",
    )


def upsert_schedule(project_dir: Path, sched: Schedule) -> None:
    """Insert or update a schedule by name; recompute next_run."""
    scheds = load_schedules(project_dir)
    for i, s in enumerate(scheds):
        if s.name == sched.name:
            scheds[i] = sched
            break
    else:
        scheds.append(sched)
    # Recompute next_run
    if sched.enabled and sched.schedule:
        try:
            cron = _parse_cron(sched.schedule)
            sched.next_run = next_run_after(cron, datetime.now()).isoformat()
        except ValueError as e:
            sched.next_run = None
            # Leave the schedule in place; surface the error on first run
            sched.params.setdefault("_cron_error", str(e))
    save_schedules(project_dir, scheds)


def remove_schedule(project_dir: Path, name: str) -> bool:
    """Remove a schedule by name. Returns True if removed."""
    scheds = load_schedules(project_dir)
    new = [s for s in scheds if s.name != name]
    if len(new) == len(scheds):
        return False
    save_schedules(project_dir, new)
    return True


def find_due(project_dir: Path, now: datetime | None = None) -> list[Schedule]:
    """Return all enabled schedules whose next_run is <= now."""
    now = now or datetime.now()
    scheds = load_schedules(project_dir)
    due = []
    for s in scheds:
        if not s.enabled or not s.next_run:
            continue
        try:
            next_dt = datetime.fromisoformat(s.next_run)
        except ValueError:
            continue
        if next_dt <= now:
            due.append(s)
    return due


def mark_run(project_dir: Path, name: str) -> None:
    """Update last_run and recompute next_run for a schedule after a successful run."""
    scheds = load_schedules(project_dir)
    for s in scheds:
        if s.name == name:
            s.last_run = datetime.now().isoformat()
            if s.schedule:
                try:
                    cron = _parse_cron(s.schedule)
                    s.next_run = next_run_after(cron, datetime.now()).isoformat()
                except ValueError:
                    s.next_run = None
            break
    save_schedules(project_dir, scheds)
