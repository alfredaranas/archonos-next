"""ArchonOS CLI — argparse dispatch only.

Per docs/architecture/CORE_ARCHITECTURE.md §1: CLI formats, core returns data.
Per §5: exit codes 0 ok · 1 user error · 2 system error.
"""

from __future__ import annotations

import argparse
import sys

from archonos.core import ops

__version__ = "0.1.0"


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
    p = argparse.ArgumentParser(prog="archonos", description="ArchonOS Next — local-first AI operating system")
    p.add_argument("--version", action="version", version=f"archonos {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp_init = sub.add_parser("init", help="create or verify a project")
    sp_init.add_argument("--project", default="default")
    sp_init.set_defaults(fn=_cmd_init)

    sp_status = sub.add_parser("status", help="show project state")
    sp_status.add_argument("--project", default="default")
    sp_status.set_defaults(fn=_cmd_status)

    sp_hc = sub.add_parser("healthcheck", help="run health checks")
    sp_hc.add_argument("--project", default="default")
    sp_hc.set_defaults(fn=_cmd_healthcheck)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(args))
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
