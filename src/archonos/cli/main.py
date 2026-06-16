"""ArchonOS CLI — argparse dispatch only.

Per docs/architecture/CORE_ARCHITECTURE.md §1: CLI formats, core returns data.
Per §5: exit codes 0 ok · 1 user error · 2 system error.
CLI surface (M0.5 + M1 + M2 + M3 + M4 + M6-sources):
    init, status, healthcheck, import, search, remember, recall,
    fetch, search-sources,
    workflow register/list/run/log
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from archonos.core import ops
from archonos.knowledge import import_ as kb_import
from archonos.knowledge import search as kb_search
from archonos.knowledge.sources import all_sources, parse_identifier, SourceError
from archonos.memory import ops as mem_ops
from archonos.storage import db
from archonos.workflows import engine as wf_engine
from archonos.workflows import registry as wf_registry

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


def _cmd_fetch(args: argparse.Namespace) -> int:
    """Fetch a paper from a remote source and import it."""
    try:
        scheme, ident = parse_identifier(args.identifier)
    except SourceError as e:
        print(f"fetch: {e}", file=sys.stderr)
        return 1
    sources = all_sources()
    if scheme not in sources:
        print(
            f"fetch: unknown source {scheme!r}. Known: {sorted(sources)}",
            file=sys.stderr,
        )
        return 1
    try:
        documents = sources[scheme].fetch(ident)
    except SourceError as e:
        print(f"fetch failed: {e}", file=sys.stderr)
        return 2
    try:
        conn = db.get_connection(args.project)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    try:
        report = kb_import.import_documents(conn, documents)
    finally:
        conn.close()
    if not documents:
        print(f"fetch: no documents returned for {args.identifier!r}")
        return 1
    print(f"Source:   {sources[scheme].name} ({scheme})")
    print(f"Title:    {documents[0].title}")
    print(f"Path:     {documents[0].source_path}")
    print(f"Result:   {report.docs_added} added, {report.skipped_dupes} skipped (dupes)")
    print(f"Chunks:   {report.chunks_added} added")
    if report.errors:
        print(f"Errors:   {len(report.errors)}", file=sys.stderr)
        for e in report.errors:
            print(f"  {e}", file=sys.stderr)
        return 2
    return 0


def _cmd_search_sources(args: argparse.Namespace) -> int:
    """Free-text search across one or all sources."""
    sources = all_sources()
    if args.source:
        if args.source not in sources:
            print(f"Unknown source: {args.source!r}. Known: {sorted(sources)}",
                  file=sys.stderr)
            return 1
        target = {args.source: sources[args.source]}
    else:
        target = sources
    total = 0
    for name, src in target.items():
        try:
            docs = src.search(args.query, limit=args.limit)
        except SourceError as e:
            print(f"[{name}] {type(e).__name__}: {e}", file=sys.stderr)
            continue
        if not docs:
            print(f"[{name}] no results")
            continue
        print(f"[{name}] {len(docs)} result(s):")
        for d in docs:
            print(f"  - {d.title[:80]}")
            print(f"      {d.source_path}")
            total += 1
    print(f"\nTotal: {total} candidate(s). Use `archonos fetch <scheme>:<id>` to import.")
    return 0


def _cmd_list_sources(args: argparse.Namespace) -> int:
    """List available paper sources."""
    sources = all_sources()
    for name, src in sources.items():
        print(f"{name:12s}  {src.name:20s}  {src.base_url}")
    return 0


def _cmd_workflow_register(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec_file).resolve()
    if not spec_path.exists():
        print(f"Spec file not found: {spec_path}", file=sys.stderr)
        return 1
    try:
        spec_text = spec_path.read_text(encoding="utf-8")
        spec = json.loads(spec_text)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Failed to load spec: {e}", file=sys.stderr)
        return 1
    try:
        conn = db.get_connection(args.project)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    try:
        wf_id = wf_registry.register(conn, args.name, spec)
    except ValueError as e:
        print(f"Invalid workflow spec: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(f"Workflow registered: {args.name} (id={wf_id})")
    return 0


def _cmd_workflow_list(args: argparse.Namespace) -> int:
    try:
        conn = db.get_connection(args.project)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    try:
        wfs = wf_registry.list_(conn)
    finally:
        conn.close()
    if not wfs:
        print("No workflows registered")
        return 0
    for wf in wfs:
        n_steps = len(wf.spec.get("steps", []))
        print(f"{wf.name}: v{wf.version}, {n_steps} steps (id={wf.id})")
    return 0


def _cmd_workflow_run(args: argparse.Namespace) -> int:
    try:
        conn = db.get_connection(args.project)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    try:
        # Parse --param key=value pairs into a dict
        params: dict = {}
        for p in args.param or []:
            if "=" not in p:
                print(f"Invalid --param: {p!r} (expected key=value)", file=sys.stderr)
                return 1
            k, v = p.split("=", 1)
            params[k] = v
        result = wf_engine.run(conn, args.name, params)
    finally:
        conn.close()
    status_word = "succeeded" if result.ok else result.status
    print(f"Run {result.run_id}: {status_word} ({len(result.log)} steps)")
    for event in result.log:
        marker = "OK  " if event["status"] == "ok" else "FAIL"
        print(f"  [{marker}] {event['step']} ({event['type']})")
        if event.get("error"):
            print(f"         error: {event['error']}")
    return 0 if result.ok else 2


def _cmd_recall(args: argparse.Namespace) -> int:
    try:
        conn = db.get_connection(args.project)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    try:
        hits = mem_ops.recall(
            conn,
            query=args.query or "",
            kind=args.kind,
            project=args.project if args.project else None,
            limit=args.limit,
        )
    finally:
        conn.close()
    if not hits:
        print("No memories found")
        return 0
    for h in hits:
        print(f"[{h.kind}] {h.created_at}  (rank {h.rank:.2f}, id={h.id})")
        body = h.body
        if len(body) > 220:
            body = body[:217] + "…"
        print(f"  {body}")
    return 0


def _cmd_remember(args: argparse.Namespace) -> int:
    try:
        conn = db.get_connection(args.project)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    try:
        try:
            mem_id = mem_ops.remember(
                conn, args.kind, args.body, meta=None, project=args.project,
            )
        except ValueError as e:
            print(f"Invalid memory: {e}", file=sys.stderr)
            return 1
    finally:
        conn.close()
    print(f"Memory stored: id={mem_id} kind={args.kind}")
    return 0


def _cmd_workflow_log(args: argparse.Namespace) -> int:
    try:
        conn = db.get_connection(args.project)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    try:
        result = wf_engine.get_run(conn, args.run_id)
    finally:
        conn.close()
    if result is None:
        print(f"Run not found: {args.run_id}", file=sys.stderr)
        return 1
    print(f"Run {result.run_id} ({result.workflow_name}): {result.status}")
    print(f"  started:  {result.started_at}")
    print(f"  finished: {result.finished_at}")
    print(f"  steps:    {len(result.log)}")
    for event in result.log:
        marker = "OK  " if event["status"] == "ok" else "FAIL"
        keys = ", ".join(event.get("output_keys") or []) or "-"
        print(f"  [{marker}] {event['step']} ({event['type']}) outputs=[{keys}]")
        if event.get("error"):
            print(f"           error: {event['error']}")
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

    sp_fetch = sub.add_parser("fetch", help="fetch a paper from a remote source and import it")
    sp_fetch.add_argument("identifier", help="scheme:identifier (e.g. arxiv:2501.12345, doi:10.xxx/yyy, pmid:33212345)")
    sp_fetch.add_argument("--project", default="default")
    sp_fetch.set_defaults(fn=_cmd_fetch)

    sp_src_search = sub.add_parser("search-sources", help="search remote paper sources (does not import)")
    sp_src_search.add_argument("query", help="search query")
    sp_src_search.add_argument("--source", help="restrict to one source (arxiv, openalex, pmid, ...)")
    sp_src_search.add_argument("--limit", "-k", type=int, default=5, dest="limit")
    sp_src_search.set_defaults(fn=_cmd_search_sources)

    sp_src_list = sub.add_parser("list-sources", help="list available paper sources")
    sp_src_list.set_defaults(fn=_cmd_list_sources)

    sp_remember = sub.add_parser("remember", help="store a memory")
    sp_remember.add_argument("body", help="memory content")
    sp_remember.add_argument("--kind", default="note", help="decision, state, lesson, note, workflow_outcome")
    sp_remember.add_argument("--project", default="default")
    sp_remember.set_defaults(fn=_cmd_remember)

    sp_recall = sub.add_parser("recall", help="recall memories (most recent, or by FTS5 query)")
    sp_recall.add_argument("query", nargs="?", default="", help="optional FTS5 query")
    sp_recall.add_argument("--kind", help="filter by kind")
    sp_recall.add_argument("--project", default="default")
    sp_recall.add_argument("--limit", "-k", type=int, default=10, dest="limit")
    sp_recall.set_defaults(fn=_cmd_recall)

    # workflow subcommand group
    sp_wf = sub.add_parser("workflow", help="workflow operations")
    wf_sub = sp_wf.add_subparsers(dest="wf_command", required=True)

    sp_wf_reg = wf_sub.add_parser("register", help="register a workflow from a JSON spec file")
    sp_wf_reg.add_argument("name", help="workflow name")
    sp_wf_reg.add_argument("spec_file", help="path to JSON spec file")
    sp_wf_reg.add_argument("--project", default="default")
    sp_wf_reg.set_defaults(fn=_cmd_workflow_register)

    sp_wf_list = wf_sub.add_parser("list", help="list registered workflows")
    sp_wf_list.add_argument("--project", default="default")
    sp_wf_list.set_defaults(fn=_cmd_workflow_list)

    sp_wf_run = wf_sub.add_parser("run", help="run a workflow")
    sp_wf_run.add_argument("name", help="workflow name")
    sp_wf_run.add_argument("--param", action="append", help="key=value (repeatable)")
    sp_wf_run.add_argument("--project", default="default")
    sp_wf_run.set_defaults(fn=_cmd_workflow_run)

    sp_wf_log = wf_sub.add_parser("log", help="show workflow run log")
    sp_wf_log.add_argument("run_id", type=int, help="run id")
    sp_wf_log.add_argument("--project", default="default")
    sp_wf_log.set_defaults(fn=_cmd_workflow_log)

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
