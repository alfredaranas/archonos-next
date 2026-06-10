"""ArchonOS CLI — argparse dispatch only. Zero business logic.

Exit codes: 0 ok · 1 user error · 2 system error.
"""

from __future__ import annotations

import argparse
import sys

from archonos import __version__
from archonos.core import ops


def _cmd_init(args: argparse.Namespace) -> int:
    r = ops.init(args.project)
    verb = "Created" if r.created else "Verified"
    print(f"{verb} project '{r.project}' at {r.db_path}")
    if r.migrations_applied:
        print(f"Applied migrations: {r.migrations_applied}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    try:
        s = ops.status(args.project)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"project:         {s.project}")
    print(f"db:              {s.db_path}")
    print(f"schema:          v{s.schema_version}")
    print(f"documents:       {s.documents}")
    print(f"chunks:          {s.chunks}")
    print(f"memories:        {s.memories}")
    print(f"workflows:       {s.workflows}")
    print(f"workflow_runs:   {s.workflow_runs}")
    return 0


def _cmd_healthcheck(args: argparse.Namespace) -> int:
    h = ops.healthcheck(args.project)
    for c in h.checks:
        mark = "OK  " if c.ok else "FAIL"
        print(f"[{mark}] {c.name}: {c.detail}")
    return 0 if h.ok else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="archonos", description="ArchonOS Next")
    p.add_argument("--version", action="version", version=f"archonos {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    for name, fn, help_ in [
        ("init", _cmd_init, "create or verify a project"),
        ("status", _cmd_status, "show project state"),
        ("healthcheck", _cmd_healthcheck, "run health checks"),
    ]:
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--project", default="default")
        sp.set_defaults(fn=fn)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except Exception as e:  # noqa: BLE001 — final guard, system error
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
