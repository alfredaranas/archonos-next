"""ArchonOS CLI — argparse dispatch only.

Per docs/architecture/CORE_ARCHITECTURE.md §1: CLI formats, core returns data.
Per §5: exit codes 0 ok · 1 user error · 2 system error.
CLI surface (M0.5 + M1 + M2):
    init, status, healthcheck, import, search
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from archonos.core import ops
from archonos.knowledge import import_ as kb_import
from archonos.knowledge import search as kb_search
from archonos.storage import db

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


def _cmd_import(args: argparse.Namespace) -> int:
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"Path not found: {path}", file=sys.stderr)
        return 1
    try:
        conn = db.get_connection(args.project)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    try:
        report = kb_import.import_path(conn, path)
    finally:
        conn.close()
    print(f"Documents: {report.docs_added} added, {report.skipped_dupes} skipped (dupes)")
    print(f"Chunks:    {report.chunks_added} added")
    if report.errors:
        print(f"Errors:    {len(report.errors)}", file=sys.stderr)
        for e in report.errors:
            print(f"  {e}", file=sys.stderr)
        return 2
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    try:
        conn = db.get_connection(args.project)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    try:
        hits = kb_search.search(conn, args.query, k=args.limit)
    finally:
        conn.close()
    if not hits:
        print("No results found")
        return 0
    for h in hits:
        print(f"{h.doc_title}  (rank {h.rank:.2f}, chunk {h.chunk_id})")
        print(f"  {h.snippet}")
    return 0


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

    sp_import = sub.add_parser("import", help="import files into the knowledge base")
    sp_import.add_argument("path", help="file or directory to import (md/txt)")
    sp_import.add_argument("--project", default="default")
    sp_import.set_defaults(fn=_cmd_import)

    sp_search = sub.add_parser("search", help="search the knowledge base")
    sp_search.add_argument("query", help="search query")
    sp_search.add_argument("--project", default="default")
    sp_search.add_argument("--limit", "-k", type=int, default=10, dest="limit")
    sp_search.set_defaults(fn=_cmd_search)

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
