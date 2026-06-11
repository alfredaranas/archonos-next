"""ArchonOS CLI — argparse dispatch only."""

from __future__ import annotations
import argparse
import json
import sys
from archonos import __version__
from archonos.core import ops

def _cmd_init(args):
    r = ops.init(args.project)
    verb = "Created" if r.created else "Verified"
    print(f"{verb} project '{r.project}' at {r.db_path}")
    if r.migrations_applied:
        print(f"Applied migrations: {r.migrations_applied}")
    return 0

def _cmd_status(args):
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

def _cmd_healthcheck(args):
    h = ops.healthcheck(args.project)
    for c in h.checks:
        mark = "OK  " if c.ok else "FAIL"
        print(f"[{mark}] {c.name}: {c.detail}")
    return 0 if h.ok else 2

def _cmd_import(args):
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

def _cmd_search(args):
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

def _cmd_remember(args):
    from archonos.memory import ops as mem_ops
    from archonos.storage import db
    conn = db.get_connection(args.project)
    try:
        mem_id = mem_ops.remember(conn, args.kind, args.body, args.project)
        print(f"Memory stored: id={mem_id}")
        return 0
    finally:
        conn.close()

def _cmd_recall(args):
    from archonos.memory import ops as mem_ops
    from archonos.storage import db
    conn = db.get_connection(args.project)
    try:
        results = mem_ops.recall(conn, query=args.query, kind=args.kind, limit=args.limit)
        if not results:
            print("No memories found")
            return 0
        for r in results:
            print(f"[{r.kind}] {r.created_at}")
            print(f"  {r.body}")
        return 0
    finally:
        conn.close()

def _cmd_workflow_register(args):
    from archonos.workflows import ops as wf_ops
    from archonos.storage import db
    conn = db.get_connection(args.project)
    try:
        spec = json.loads(args.spec) if args.spec else {"steps": []}
        wf_id = wf_ops.register(conn, args.name, spec)
        print(f"Workflow registered: {args.name} (id={wf_id})")
        return 0
    finally:
        conn.close()

def _cmd_workflow_list(args):
    from archonos.workflows import ops as wf_ops
    from archonos.storage import db
    conn = db.get_connection(args.project)
    try:
        workflows = wf_ops.list_workflows(conn)
        if not workflows:
            print("No workflows registered")
            return 0
        for wf in workflows:
            spec = json.loads(wf.spec)
            steps = len(spec.get("steps", []))
            print(f"{wf.name}: v{wf.version}, {steps} steps")
        return 0
    finally:
        conn.close()

def _cmd_workflow_run(args):
    from archonos.workflows import ops as wf_ops
    from archonos.storage import db
    conn = db.get_connection(args.project)
    try:
        run_id = wf_ops.run_workflow(conn, args.name)
        print(f"Workflow run: id={run_id}")
        return 0
    finally:
        conn.close()

def _cmd_chat(args):
    from archonos.llm import cli as llm_cli
    result = llm_cli.chat(args.prompt, system=args.system or "", provider=args.provider, model=args.model)
    print(result)
    return 0

def _cmd_llm_providers(args):
    from archonos.llm import cli as llm_cli
    for p in llm_cli.providers_list():
        print(p)
    return 0

def build_parser():
    p = argparse.ArgumentParser(prog="archonos", description="ArchonOS Next")
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

    sp_import = sub.add_parser("import", help="import files into knowledge base")
    sp_import.add_argument("path", help="file or folder to import")
    sp_import.add_argument("--project", default="default")
    sp_import.set_defaults(fn=_cmd_import)

    sp_search = sub.add_parser("search", help="search knowledge base")
    sp_search.add_argument("query", help="search query")
    sp_search.add_argument("--project", default="default")
    sp_search.add_argument("--limit", type=int, default=10)
    sp_search.set_defaults(fn=_cmd_search)

    sp_mem = sub.add_parser("remember", help="store a memory")
    sp_mem.add_argument("body", help="memory content")
    sp_mem.add_argument("--kind", default="note", help="decision, state, lesson, note, workflow_outcome")
    sp_mem.add_argument("--project", default="default")
    sp_mem.set_defaults(fn=_cmd_remember)

    sp_recall = sub.add_parser("recall", help="recall memories")
    sp_recall.add_argument("--query", help="search query")
    sp_recall.add_argument("--kind", help="filter by kind")
    sp_recall.add_argument("--limit", type=int, default=10)
    sp_recall.add_argument("--project", default="default")
    sp_recall.set_defaults(fn=_cmd_recall)

    sp_wf_reg = sub.add_parser("workflow-register", help="register a workflow")
    sp_wf_reg.add_argument("name", help="workflow name")
    sp_wf_reg.add_argument("--spec", default="{}", help="workflow spec JSON")
    sp_wf_reg.add_argument("--project", default="default")
    sp_wf_reg.set_defaults(fn=_cmd_workflow_register)

    sp_wf_list = sub.add_parser("workflow-list", help="list workflows")
    sp_wf_list.add_argument("--project", default="default")
    sp_wf_list.set_defaults(fn=_cmd_workflow_list)

    sp_wf_run = sub.add_parser("workflow-run", help="run a workflow")
    sp_wf_run.add_argument("name", help="workflow name")
    sp_wf_run.add_argument("--project", default="default")
    sp_wf_run.set_defaults(fn=_cmd_workflow_run)

    sp_chat = sub.add_parser("chat", help="chat with LLM")
    sp_chat.add_argument("prompt", help="prompt")
    sp_chat.add_argument("--system", default="", help="system prompt")
    sp_chat.add_argument("--provider", default="minimax", help="provider name")
    sp_chat.add_argument("--model", default="", help="model name")
    sp_chat.set_defaults(fn=_cmd_chat)

    sp_llm = sub.add_parser("llm-providers", help="list available LLM providers")
    sp_llm.set_defaults(fn=_cmd_llm_providers)

    return p

def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())