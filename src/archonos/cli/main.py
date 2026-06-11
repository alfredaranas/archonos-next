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


def _cmd_import(args: argparse.Namespace) -> int:
    from pathlib import Path
    from archonos.knowledge import import_ as kb_import
    from archonos.storage import db
    
    conn = db.get_connection(args.project)
    try:
        path = Path(args.path).resolve()
        if not path.exists():
            print(f"Path not found: {path}", file=sys.stderr)
            return 1
        
        report = kb_import.import_path(conn, path)
        print(f"Documents: {report.docs_added} added, {report.skipped_dupes} skipped")
        print(f"Chunks: {report.chunks_added} added")
        return 0
    finally:
        conn.close()


def _cmd_search(args: argparse.Namespace) -> int:
    from archonos.knowledge import search as kb_search
    from archonos.storage import db
    
    conn = db.get_connection(args.project)
    try:
        results = kb_search.search(conn, args.query, k=args.limit)
        if not results:
            print("No results found")
            return 0
        
        for r in results:
            print(f"{r.title}")
            print(f"  {r.snippet}")
            print(f"  rank: {r.rank:.2f}")
        return 0
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="archonos", description="ArchonOS Next")
    p.add_argument("--version", action="version", version=f"archonos {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    # init
    sp_init = sub.add_parser("init", help="create or verify a project")
    sp_init.add_argument("--project", default="default")
    sp_init.set_defaults(fn=_cmd_init)

    # status
    sp_status = sub.add_parser("status", help="show project state")
    sp_status.add_argument("--project", default="default")
    sp_status.set_defaults(fn=_cmd_status)

    # healthcheck
    sp_hc = sub.add_parser("healthcheck", help="run health checks")
    sp_hc.add_argument("--project", default="default")
    sp_hc.set_defaults(fn=_cmd_healthcheck)

    # import
    sp_import = sub.add_parser("import", help="import files into knowledge base")
    sp_import.add_argument("path", help="file or folder to import")
    sp_import.add_argument("--project", default="default")
    sp_import.set_defaults(fn=_cmd_import)

    # search
    sp_search = sub.add_parser("search", help="search knowledge base")
    sp_search.add_argument("query", help="search query")
    sp_search.add_argument("--project", default="default")
    sp_search.add_argument("--limit", type=int, default=10, help="max results (default: 10)")
    sp_search.set_defaults(fn=_cmd_search)

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