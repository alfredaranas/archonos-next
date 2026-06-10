# ArchonOS Next — Core Architecture v1.0

> The two decisions the founding doc left open — the workflow primitive and the concrete schema — plus the system design that binds M0.5–M6 together. This document closes "architecture frozen." Changes require a documented decision record in docs/architecture/decisions/.

**Author:** Claude (architect) · **Implementer:** Codex · **Date:** 2026-06-09

---

## 1. System shape

```
                        ┌─────────────────────────┐
                        │       CLI (typer-free,   │
                        │       argparse only)     │
                        └───────────┬─────────────┘
                                    │
                        ┌───────────▼─────────────┐
                        │      ArchonOS Core       │
                        │  (pure python, no I/O    │
                        │   opinions, testable)    │
                        └──┬──────┬──────┬────────┘
                           │      │      │
                ┌──────────▼─┐ ┌──▼───┐ ┌▼─────────┐
                │ Knowledge  │ │Memory│ │Workflows │
                └──────┬─────┘ └──┬───┘ └────┬─────┘
                       │          │          │
                       └──────────▼──────────┘
                                  │
                        ┌─────────▼─────────┐
                        │   storage/db.py    │
                        │  (single SQLite    │
                        │   connection mgr)  │
                        └─────────┬─────────┘
                                  │
                          ~/.archonos/<project>/archonos.db
```

Rules:
- **One database file per project.** No cross-project state. `~/.archonos/<project>/archonos.db`.
- **One module owns the connection** (`storage/db.py`). Everything else receives a connection, never opens one. This is what makes SQLite → Supabase swappable later: swap the connection factory, not the callers.
- **Core never prints.** CLI formats; core returns data. This is what makes CLI → MCP → UI swappable later.
- **stdlib only for M0.5–M5.** `sqlite3`, `argparse`, `json`, `pathlib`, `dataclasses`, `hashlib`, `datetime`. The only permitted third-party dep through M5 is `pytest` (dev). M6 adds `httpx` or stdlib `urllib` — decide at M6, prefer stdlib.

## 2. Schema DDL v1 (canonical — Codex implements verbatim)

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE settings (
  key         TEXT PRIMARY KEY,
  value       TEXT NOT NULL,
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE documents (
  id          INTEGER PRIMARY KEY,            -- rowid alias. INTEGER, never UUID (FTS5 lesson)
  source_path TEXT NOT NULL,                  -- original file path at import time
  title       TEXT NOT NULL,
  doc_type    TEXT NOT NULL DEFAULT 'md',     -- md | txt | pdf
  sha256      TEXT NOT NULL UNIQUE,           -- dedupe + change detection on re-import
  byte_size   INTEGER NOT NULL,
  imported_at TEXT NOT NULL DEFAULT (datetime('now')),
  meta        TEXT NOT NULL DEFAULT '{}'      -- JSON, schemaless extras
);

CREATE TABLE chunks (
  id          INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_idx   INTEGER NOT NULL,               -- 0-based order within document
  body        TEXT NOT NULL,
  body_chars  INTEGER NOT NULL,
  UNIQUE(document_id, chunk_idx)
);

CREATE VIRTUAL TABLE chunks_fts USING fts5(
  body,
  content='chunks', content_rowid='id'        -- INTEGER id makes this valid
);

-- FTS sync triggers (insert/delete/update) — Codex: implement all three.

CREATE TABLE memories (
  id          INTEGER PRIMARY KEY,
  kind        TEXT NOT NULL CHECK(kind IN ('decision','state','lesson','note','workflow_outcome')),
  body        TEXT NOT NULL,
  project     TEXT NOT NULL DEFAULT 'default',
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  meta        TEXT NOT NULL DEFAULT '{}'
);

CREATE VIRTUAL TABLE memories_fts USING fts5(
  body,
  content='memories', content_rowid='id'
);

CREATE TABLE workflows (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  spec        TEXT NOT NULL,                  -- JSON workflow spec (see §3)
  version     INTEGER NOT NULL DEFAULT 1,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE workflow_runs (
  id          INTEGER PRIMARY KEY,
  workflow_id INTEGER NOT NULL REFERENCES workflows(id),
  status      TEXT NOT NULL CHECK(status IN ('running','succeeded','failed','aborted')),
  started_at  TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at TEXT,
  log         TEXT NOT NULL DEFAULT '[]'      -- JSON array of step events (see §3.4)
);

CREATE TABLE schema_version (
  version     INTEGER NOT NULL,
  applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT INTO schema_version(version) VALUES (1);
```

Schema rules:
- INTEGER primary keys everywhere. UUIDs banned (FTS5 `content_rowid` requires integer; legacy kb_local_sync failure is the precedent).
- Migrations are numbered SQL files in `src/archonos/storage/migrations/`; `schema_version` gates application. No ORM, ever.
- JSON columns (`meta`, `spec`, `log`) are stored as TEXT, validated in core, never queried with json_extract in v1.

## 3. Workflow primitive (the open decision — resolved)

**A workflow is a JSON document: an ordered list of typed steps with explicit inputs/outputs. Not YAML (no dep), not Python callables (not portable/auditable), not shell-first (not safe by default).**

### 3.1 Spec format

```json
{
  "name": "import-and-brief",
  "description": "Import a folder, search a topic, save a memory",
  "params": {"folder": "string", "topic": "string"},
  "steps": [
    {"id": "s1", "type": "import",  "args": {"path": "{{params.folder}}"}},
    {"id": "s2", "type": "search",  "args": {"query": "{{params.topic}}", "k": 5}},
    {"id": "s3", "type": "remember","args": {"kind": "workflow_outcome",
                                              "body": "Brief on {{params.topic}}: {{steps.s2.summary}}"}}
  ]
}
```

### 3.2 Step types (v1 registry — closed set)

| type | does | maps to |
|---|---|---|
| `import` | import file/folder into knowledge | knowledge.import_path() |
| `search` | FTS query, returns top-k | knowledge.search() |
| `remember` | write a memory | memory.remember() |
| `recall` | search memories | memory.recall() |
| `shell` | run a whitelisted local command | subprocess, **requires `allow_shell=true` in settings** |
| `ask` | LLM call (M6+ only, no-op stub before) | provider.complete() |

The registry is a dict in `workflows/steps.py`. Adding a step type = adding a function + registry entry + test. No plugins, no entry_points, no dynamic import in v1.

### 3.3 Templating

`{{params.x}}` and `{{steps.<id>.<key>}}` only. Implemented with a 30-line resolver, not jinja. Unknown reference = hard fail before execution starts (validate the whole DAG first, then run).

### 3.4 Execution + audit

- Sequential only in v1. No branches, no loops, no parallelism. (A workflow that needs control flow is a Python script; document it as such.)
- Each step appends an event to `workflow_runs.log`: `{"step": "s2", "status": "ok", "started": "...", "finished": "...", "output_keys": ["summary"], "error": null}`.
- First failure stops the run, status=`failed`, partial log preserved. No retries in v1.
- `archonos workflow run <name> --param folder=./docs --param topic=czmil`

## 4. Module contracts (what Codex implements)

```
storage/db.py        get_connection(project) -> sqlite3.Connection; migrate(conn)
knowledge/import_.py import_path(conn, path) -> ImportReport(docs_added, chunks_added, skipped_dupes)
knowledge/search.py  search(conn, query, k=10) -> list[Hit(chunk_id, doc_title, snippet, rank)]
knowledge/chunk.py   chunk_text(text, target_chars=1500, overlap=200) -> list[str]
memory/store.py      remember(conn, kind, body, meta=None) -> int
memory/recall.py     recall(conn, query, k=10) -> list[MemoryHit]
workflows/registry.py register(conn, name, spec_json); get(conn, name); list_(conn)
workflows/engine.py  run(conn, name, params) -> RunResult(run_id, status, log)
workflows/steps.py   STEP_REGISTRY: dict[str, StepFn]
config/settings.py   get/set over settings table; ARCHONOS_HOME env override
cli/main.py          argparse dispatch only — zero business logic
```

All return values are dataclasses. All functions take `conn` as first arg. No module-level state.

## 5. CLI surface (complete for M1–M5)

```
archonos init [--project NAME]
archonos status
archonos healthcheck
archonos import PATH
archonos search QUERY [-k N]
archonos remember TEXT [--kind KIND]
archonos recall QUERY [-k N]
archonos workflow register FILE.json
archonos workflow list
archonos workflow run NAME [--param k=v ...]
archonos workflow log RUN_ID
```

Exit codes: 0 ok · 1 user error (bad args, not found) · 2 system error (db, io). Healthcheck prints one line per check, exits nonzero on any failure.

## 6. M6 provider contract (designed now, built later)

```python
@dataclass
class ChatResponse:
    text: str
    usage: dict          # tokens in/out
    raw: dict            # provider response, untouched

class ModelProvider(Protocol):
    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResponse: ...
```

One implementation at M6: `OpenAICompatProvider(base_url, api_key, model)` — covers MiniMax M3 (OpenRouter), OpenAI, and any local vLLM endpoint with zero extra code. The interface is deliberately MCP-tool-shaped (`tools` param) so the future MCP layer is a transport bolt-on, not a redesign. No key configured → `archonos ask` exits 1 with a clear message; nothing else degrades.

## 7. Test strategy

- Every module contract in §4 gets a unit test against a tmp-path SQLite db (pytest `tmp_path` fixture). No mocks of sqlite — test the real thing, it's free.
- One end-to-end test per milestone gate, named `test_gate_m1.py` … `test_gate_m5.py`, runnable individually. The gate test IS the milestone definition of done.
- CI is `pytest` — nothing else until it hurts.

## 8. What this document deliberately does not decide

- Chunking quality tuning (M2 ships naive char-window chunking; improving it is post-alpha)
- PDF extraction fidelity (M2 ships stdlib-possible text extraction or marks pdf as best-effort)
- Embeddings/vector search (banned until post-alpha per founding doc; FTS5 is the search story)
- Any legacy adapter (Continuum, SupaBrain, Hermes) — capability pool only

---

**Codex: implement M0.5 + M1 from this document and BASE_PLAN.md. The schema in §2 and the workflow spec in §3 are frozen. Open a PR per milestone. Gate tests define done.**
