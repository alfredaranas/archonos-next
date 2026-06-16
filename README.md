# ArchonOS Next

Local-first AI operating system: knowledge, memory, workflows, continuity. The model is replaceable; the knowledge is durable.

**Status:** Local Alpha (Milestones 0.5–5 complete). Architecture frozen. M6 (LLM provider layer) is the first post-alpha milestone.

## Quickstart

```bash
git clone https://github.com/alfredaranas/archonos-next.git
cd archonos-next
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
archonos init
archonos import ~/some-corpus/
archonos search "your topic"
archonos remember --kind decision "An important call you made"
archonos recall "the call you made"
```

For the full walkthrough (6 steps from a clean machine), see [`docs/onboarding/FIRST_RUN.md`](docs/onboarding/FIRST_RUN.md). For setting up Windows 11 + WSL2 from scratch, see [`docs/onboarding/WINDOWS_WSL2.md`](docs/onboarding/WINDOWS_WSL2.md).

## What's in Local Alpha

| Milestone | Status | What it is |
|---|---|---|
| M0.5 | ✅ | Repo foundation, package layout, stdlib-only deps |
| M1 | ✅ | CLI kernel: `init`, `status`, `healthcheck` |
| M2 | ✅ | Knowledge base: `import`, `search` (FTS5, BM25, < 1ms) |
| M3 | ✅ | Workflow engine: JSON specs, 6 step types, templating, audit trail |
| M4 | ✅ | Persistent memory: `remember`, `recall` with cross-process persistence |
| M5 | ✅ | Local Alpha walkthrough (this release) |
| M6 | 📋 | LLM provider layer (post-alpha) |

**72 unit + integration tests** in `tests/test_gate_m1.py` … `test_gate_m4.py` + **3 end-to-end tests** in `tests/test_e2e_alpha.py` — all pass on Python 3.11+ with zero runtime dependencies.

## CLI surface

```text
archonos init [--project NAME]              # create or verify a project
archonos status [--project NAME]           # show counts + schema version
archonos healthcheck [--project NAME]      # 5 checks: db, schema, write, fts, disk

archonos import PATH [--project NAME]       # import md/txt into knowledge base
archonos search QUERY [-k N]                # FTS5 + BM25 ranked search

archonos remember TEXT [--kind KIND]        # store a memory (decision/state/lesson/note/workflow_outcome)
archonos recall [QUERY] [--kind KIND] [-k N]  # FTS5 recall or most-recent

archonos workflow register NAME SPEC_FILE   # register a JSON workflow spec
archonos workflow list                      # list registered workflows
archonos workflow run NAME [--param k=v ...]  # run a workflow
archonos workflow log RUN_ID                # show audit trail
```

Exit codes per `docs/architecture/CORE_ARCHITECTURE.md` §5: **0** ok · **1** user error · **2** system error.

## Architecture

- **One SQLite database per project**, at `~/.archonos/<project>/archonos.db` (override with `$ARCHONOS_HOME`).
- **One module owns the connection** (`src/archonos/storage/db.py`); everything else receives a `Connection`. Swapping SQLite for Supabase means swapping this factory, not the callers.
- **Core never prints.** CLI formats; core returns dataclasses. This is what makes CLI → MCP → UI swappable.
- **Migrations are numbered SQL files** in `src/archonos/storage/migrations/`; `schema_version` table gates application. No ORM, ever.
- **Workflows are JSON specs** with typed steps (`import`, `search`, `remember`, `recall`, `shell`, `ask`) and a tiny `{{params.x}}` / `{{steps.<id>.<key>}}` templating language. No YAML, no Python callables, no plugins in v1.
- **FTS5 everywhere.** Both `chunks` and `memories` are indexed by synced FTS5 virtual tables. No vector search until post-alpha.

Read [`docs/architecture/CORE_ARCHITECTURE.md`](docs/architecture/CORE_ARCHITECTURE.md) for the full spec. The schema DDL is in [`src/archonos/storage/migrations/001_init.sql`](src/archonos/storage/migrations/001_init.sql) and matches the spec verbatim.

## Development

```bash
# Run the full test suite (75 tests, ~1s)
pytest tests/ -v

# Run a single milestone's gate
pytest tests/test_gate_m1.py -v
pytest tests/test_gate_m2.py -v
pytest tests/test_gate_m3.py -v
pytest tests/test_gate_m4.py -v

# Run the end-to-end Local Alpha scenario (3 tests, ~1.3s)
pytest tests/test_e2e_alpha.py -v
```

## Project layout

```text
archonos-next/
├── pyproject.toml                # 0 runtime deps, pytest dev-only
├── docs/
│   ├── BASE_PLAN.md              # milestone plan (frozen)
│   ├── architecture/
│   │   ├── CORE_ARCHITECTURE.md  # schema + workflow + module contracts (frozen)
│   │   └── decisions/            # ADRs
│   ├── founding/                 # CODEX_HANDOFF, NORTH_STAR, etc.
│   ├── onboarding/
│   │   ├── FIRST_RUN.md          # M5 walkthrough (the 6-step path)
│   │   └── WINDOWS_WSL2.md       # clean Windows 11 setup
│   └── product/                  # post-alpha planning
├── src/archonos/                 # ~1300 LOC of kernel code
│   ├── cli/main.py               # argparse dispatch
│   ├── core/ops.py               # init / status / healthcheck
│   ├── storage/
│   │   ├── db.py                 # single conn owner + migration runner
│   │   └── migrations/001_init.sql
│   ├── knowledge/                # chunk, import, search (M2)
│   ├── memory/ops.py             # remember, recall (M4)
│   └── workflows/                # registry, steps, engine (M3)
└── tests/
    ├── test_gate_m1.py           # 12 tests
    ├── test_gate_m2.py           # 18 tests
    ├── test_gate_m3.py           # 27 tests
    ├── test_gate_m4.py           # 15 tests
    └── test_e2e_alpha.py         # 3 scenarios
```

## Division of labor

- **Claude** — architecture, planning, decision records (`docs/architecture/decisions/`)
- **Codex** — implementation, tests, PRs per milestone
- **Hermes** — kernel owner; verifies gate tests per milestone; reports to Alfred via Telegram

Gate tests define done. A milestone is not complete until its gate test passes.

## What's next

M6 (LLM provider layer) per `docs/BASE_PLAN.md`:

- `ModelProvider` protocol: `complete(messages, tools=None) -> ChatResponse`
- One implementation: `OpenAICompatProvider(base_url, api_key, model)` — covers MiniMax M3 (via OpenRouter), OpenAI, and any local vLLM endpoint
- `archonos ask "<question>"` — retrieval (M2 search) + synthesis (provider)
- API key via settings table / env var; no key = degraded mode, everything else still works
- Still zero required cloud: provider optional, knowledge/memory/workflows fully functional without it

The `ask` step type already exists in the workflow registry as a M6 stub — when the provider is built, only `src/archonos/workflows/steps.py::step_ask` needs to change.
