"""Workflow step registry for ArchonOS.

Per docs/architecture/CORE_ARCHITECTURE.md §3.2:
    Closed set of step types in v1:
        import, search, remember, recall, shell, ask
    The registry is a dict. Adding a step type = adding a function + registry
    entry + test. No plugins, no entry_points, no dynamic import in v1.

Per §3.4: Each step appends an event to workflow_runs.log.
Per §3.1: step shape is {id, type, args}.
"""

from __future__ import annotations

from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3


# A step function receives a sqlite3.Connection (so it can touch the DB)
# and the resolved args dict (templating already applied). It returns a
# dict of output keys that subsequent steps can reference as
# `{{steps.<id>.<key>}}`. The dict MUST be JSON-serializable.
StepFn = Callable[["sqlite3.Connection", dict[str, Any]], dict[str, Any]]


# --- step implementations ---


def step_import(conn, args: dict[str, Any]) -> dict[str, Any]:
    from pathlib import Path
    from archonos.knowledge import import_ as kb_import

    path = Path(args["path"]).resolve()
    report = kb_import.import_path(conn, path)
    return {
        "docs_added": report.docs_added,
        "chunks_added": report.chunks_added,
        "skipped_dupes": report.skipped_dupes,
        "errors": report.errors,
    }


def step_fetch(conn, args: dict[str, Any]) -> dict[str, Any]:
    """Fetch a paper from a remote source (arXiv, OpenAlex, PubMed,
    Unpaywall, CORE, Crossref, DOAJ) and import it into the knowledge
    base. Per CORE_ARCHITECTURE §3.2 step registry, this is a closed
    step type added in M6+.
    """
    from archonos.knowledge import import_ as kb_import
    from archonos.knowledge.sources import all_sources, parse_identifier, SourceError

    identifier = args["identifier"]
    sources = all_sources()
    scheme, ident = parse_identifier(identifier)
    if scheme not in sources:
        raise ValueError(
            f"fetch: unknown source scheme {scheme!r}. "
            f"Known: {sorted(sources)}"
        )
    try:
        documents = sources[scheme].fetch(ident)
    except SourceError as e:
        raise RuntimeError(f"fetch failed for {identifier!r}: {e}") from e
    report = kb_import.import_documents(conn, documents)
    return {
        "source": scheme,
        "identifier": ident,
        "docs_added": report.docs_added,
        "chunks_added": report.chunks_added,
        "skipped_dupes": report.skipped_dupes,
        "errors": report.errors,
    }


def step_search(conn, args: dict[str, Any]) -> dict[str, Any]:
    from archonos.knowledge import search as kb_search

    k = int(args.get("k", 10))
    hits = kb_search.search(conn, args["query"], k=k)
    return {
        "hits": [
            {
                "chunk_id": h.chunk_id,
                "doc_title": h.doc_title,
                "snippet": h.snippet,
                "rank": h.rank,
            }
            for h in hits
        ],
        "count": len(hits),
        "summary": _summarize(hits),
    }


def _summarize(hits) -> str:  # type: ignore[no-untyped-def]
    if not hits:
        return "no results"
    return "; ".join(f"{h.doc_title}: {h.snippet[:80]}" for h in hits[:3])


def step_remember(conn, args: dict[str, Any]) -> dict[str, Any]:
    from archonos.memory import ops as mem_ops

    kind = args.get("kind", "note")
    body = args["body"]
    project = args.get("project", "default")
    meta = args.get("meta")
    if isinstance(meta, str):
        import json
        meta = json.loads(meta) if meta.strip() else None
    mem_id = mem_ops.remember(conn, kind, body, meta=meta, project=project)
    return {"id": mem_id, "kind": kind}


def step_recall(conn, args: dict[str, Any]) -> dict[str, Any]:
    from archonos.memory import ops as mem_ops

    limit = int(args.get("limit", 10))
    kind = args.get("kind")
    project = args.get("project")
    query = args.get("query", "")
    hits = mem_ops.recall(conn, query=query, kind=kind, project=project, limit=limit)
    return {
        "hits": [
            {
                "id": h.id,
                "kind": h.kind,
                "body": h.body,
                "created_at": h.created_at,
                "rank": h.rank,
            }
            for h in hits
        ],
        "count": len(hits),
    }


def step_shell(conn, args: dict[str, Any]) -> dict[str, Any]:
    """Run a whitelisted shell command. Requires `allow_shell=true` in settings.

    Per §3.2: shell step requires allow_shell=true in settings.
    """
    import shlex
    import subprocess

    if not _shell_allowed(conn):
        raise PermissionError(
            "shell step requires settings.key='allow_shell' value='true'"
        )
    cmd_str = args["command"]
    timeout = int(args.get("timeout", 30))
    parts = shlex.split(cmd_str)
    result = subprocess.run(  # noqa: S603
        parts,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _shell_allowed(conn) -> bool:  # type: ignore[no-untyped-def]
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'allow_shell'"
    ).fetchone()
    return row is not None and row["value"].lower() in ("true", "1", "yes")


def step_ask(conn, args: dict[str, Any]) -> dict[str, Any]:
    """LLM call. M6+ only; M3 ships as a no-op stub that returns a
    'not configured' message and exits 0. Per §3.2 the registry lists ask
    but per §6 implementation is gated on provider availability.
    """
    return {
        "text": "(ask step: M6 stub — provider not configured)",
        "prompt": args.get("prompt", ""),
    }


# --- the registry itself ---


STEP_REGISTRY: dict[str, StepFn] = {
    "import": step_import,
    "fetch": step_fetch,
    "search": step_search,
    "remember": step_remember,
    "recall": step_recall,
    "shell": step_shell,
    "ask": step_ask,
}


def resolve_step(type_name: str) -> StepFn:
    if type_name not in STEP_REGISTRY:
        raise KeyError(
            f"Unknown step type: {type_name!r}. "
            f"Allowed: {sorted(STEP_REGISTRY)}"
        )
    return STEP_REGISTRY[type_name]
