# ArchonOS Next

Local-first AI operating system: knowledge, memory, workflows, continuity. The model is replaceable; the knowledge is durable.

**Status:** All milestones 0.5–6 complete. 129 tests passing. Zero runtime dependencies.

## Quickstart

```bash
git clone https://github.com/alfredaranas/archonos-next.git
cd archonos-next
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
archonos init
archonos import ~/some-corpus/    # .md, .txt, .pdf
archonos search "your topic"
archonos remember --kind decision "An important call you made"
archonos recall "the call you made"
```

For the full walkthrough (6 steps from a clean machine), see [`docs/onboarding/FIRST_RUN.md`](docs/onboarding/FIRST_RUN.md). For setting up Windows 11 + WSL2 from scratch, see [`docs/onboarding/WINDOWS_WSL2.md`](docs/onboarding/WINDOWS_WSL2.md).

## Milestone status

| Milestone | Status | What it is |
|---|---|---|
| M0.5 | ✅ | Repo foundation, package layout, stdlib-only deps |
| M1 | ✅ | CLI kernel: `init`, `status`, `healthcheck` |
| M2 | ✅ | Knowledge base: `import`, `search` (FTS5, BM25, < 1ms) |
| M3 | ✅ | Workflow engine: JSON specs, 7 step types, templating, audit trail |
| M4 | ✅ | Persistent memory: `remember`, `recall` with cross-process persistence |
| M5 | ✅ | Local Alpha walkthrough + clean-machine e2e test |
| M6 | ✅ | LLM provider layer (`archonos ask`) + 8 open-access paper sources |

**129 tests** in `tests/` — all pass in ~8s. Breakdown:
- `test_gate_m1.py` 12 (kernel + schema-shape guards)
- `test_gate_m2.py` 18 (knowledge + the <200ms search gate)
- `test_gate_m3.py` 27 (workflow engine + the 3-step gate)
- `test_gate_m4.py` 15 (memory + cross-process persistence gate)
- `test_gate_m6.py` 14 (LLM provider + RAG + degraded mode)
- `test_e2e_alpha.py` 3 (clean-machine walkthrough as subprocesses)
- `test_sources.py` 20 (8 paper sources, network-aware)
- `test_tier2.py` 20 (PDF import, .archonosignore, cron, scheduler)

## CLI surface

```text
# Project lifecycle
archonos init [--project NAME]              # create or verify a project
archonos status [--project NAME]           # show counts + schema version
archonos healthcheck [--project NAME]      # 5 checks: db, schema, write, fts, disk

# Knowledge
archonos import PATH [--project NAME]       # import md/txt/pdf into knowledge base
archonos search QUERY [-k N]                # FTS5 + BM25 ranked search
archonos fetch <scheme>:<id>                # fetch from a paper source
archonos search-sources QUERY [--source]    # search remote sources (no import)
archonos list-sources                       # show available paper sources

# Memory
archonos remember TEXT [--kind KIND]        # store a memory
archonos recall [QUERY] [--kind KIND] [-k N]  # FTS5 recall or most-recent

# Workflows
archonos workflow register NAME SPEC_FILE
archonos workflow list
archonos workflow run NAME [--param k=v ...]
archonos workflow log RUN_ID
archonos workflow schedule add NAME WORKFLOW "0 9 * * *"
archonos workflow schedule list
archonos workflow schedule enable|disable|remove NAME

# Scheduling
archonos scheduler run [--once] [--poll-seconds N]   # foreground scheduler

# LLM
archonos ask "..."                            # RAG: FTS5 + provider.complete()
archonos llm-providers                        # show active LLM config
archonos config set|get|unset|list KEY [VALUE]  # project settings (LLM keys go here)
```

Exit codes per `docs/architecture/CORE_ARCHITECTURE.md` §5: **0** ok · **1** user error · **2** system error.

## Paper sources (8 schemes, stdlib only)

All fetchers use stdlib `urllib` + `json` + `xml.etree`. **Zero PyPI packages installed.** No Sci-Hub, no shadow libraries.

| Scheme | Source | Coverage | Auth |
|---|---|---|---|
| `arxiv:` | arXiv | 2.4M+ preprints | none |
| `openalex:` | OpenAlex | 250M+ works | none (polite pool) |
| `pmid:` | PubMed | 36M+ abstracts | none (NCBI E-utilities) |
| `pmcid:` | PubMed Central | 11.6M full text | none (JATS XML) |
| `doi:` | Unpaywall | 20M+ free copies via DOI | email UA |
| `core:` | CORE | 200M+ papers | none |
| `crossref:` | Crossref | 150M+ DOI registry | none (polite pool) |
| `doaj:` | DOAJ | ~20K OA journals | none |

```bash
archonos list-sources                                          # see what's available
archonos fetch arxiv:1706.03762                                # Attention Is All You Need
archonos fetch doi:10.1038/nature12373                         # resolves via Unpaywall
archonos fetch pmid:33212345                                   # PubMed abstract
archonos search-sources "graph neural network" --source arxiv  # browse first
```

Skip list (no public API or legally grey): Google Scholar, Anna's Archive, WeLib.

## LLM provider layer

The `archonos ask` command and the `ask` workflow step type use any OpenAI-compatible HTTP endpoint. Default config targets MiniMax M3 via OpenRouter.

```bash
# Option 1: settings (persisted in the project's SQLite db)
archonos config set llm_provider minimax
archonos config set llm_model MiniMax-M3
archonos config set llm_base_url https://openrouter.ai/api/v1
archonos config set llm_api_key <your-key>

# Option 2: env vars (override settings; wins)
export ARCHONOS_LLM_API_KEY=<your-key>
export ARCHONOS_LLM_BASE_URL=https://openrouter.ai/api/v1

# Then:
archonos ask "summarize the 3 most relevant imported papers on attention mechanisms"
archonos llm-providers     # show active config + masked key
```

**No provider?** All M0.5–M5 features still work. `archonos ask` exits 1 with a clear message about how to configure. The `ask` workflow step fails the run cleanly (per §3.4 fail-fast).

Works for: MiniMax M3 via OpenRouter, OpenAI, vLLM, llama.cpp server, LM Studio, any local OpenAI-API-shaped endpoint.

## Architecture

- **One SQLite database per project**, at `~/.archonos/<project>/archonos.db` (override with `$ARCHONOS_HOME`).
- **One module owns the connection** (`src/archonos/storage/db.py`); everything else receives a `Connection`. Swapping SQLite for Supabase means swapping this factory, not the callers.
- **Core never prints.** CLI formats; core returns dataclasses. This is what makes CLI → MCP → UI swappable.
- **Migrations are numbered SQL files** in `src/archonos/storage/migrations/`; `schema_version` table gates application. No ORM, ever.
- **Workflows are JSON specs** with typed steps (`import`, `fetch`, `search`, `remember`, `recall`, `shell`, `ask`) and a tiny `{{params.x}}` / `{{steps.<id>.<key>}}` templating language. No YAML, no Python callables, no plugins in v1.
- **FTS5 everywhere.** Both `chunks` and `memories` are indexed by synced FTS5 virtual tables. No vector search until post-alpha.
- **Paper sources** (M6+): each source implements the `Source` protocol; `import_documents()` is the integration point that makes them first-class kernel citizens.
- **LLM providers** (M6): `ModelProvider` Protocol + `OpenAICompatProvider` (one implementation, covers OpenAI, MiniMax M3 via OpenRouter, vLLM, etc.).

Read [`docs/architecture/CORE_ARCHITECTURE.md`](docs/architecture/CORE_ARCHITECTURE.md) for the full spec. The schema DDL is in [`src/archonos/storage/migrations/001_init.sql`](src/archonos/storage/migrations/001_init.sql) and matches the spec verbatim.

## Development

```bash
# Run the full test suite (129 tests, ~8s)
pytest tests/ -v

# Run a single milestone's gate
pytest tests/test_gate_m1.py -v
pytest tests/test_gate_m2.py -v
pytest tests/test_gate_m3.py -v
pytest tests/test_gate_m4.py -v
pytest tests/test_gate_m6.py -v

# Run the end-to-end scenarios
pytest tests/test_e2e_alpha.py -v
pytest tests/test_sources.py -v       # 14 tests, 8 network-aware
pytest tests/test_tier2.py -v        # PDF, ignore, cron, scheduler

# Offline-only (skips the 8 network-dependent source tests)
pytest tests/ -v -k "not network"
```

## Project layout

```text
archonos-next/
├── pyproject.toml                # 0 runtime deps, pytest dev-only
├── .github/workflows/test.yml    # CI: pytest on Python 3.11 + 3.12
├── docs/
│   ├── BASE_PLAN.md              # milestone plan (frozen)
│   ├── architecture/
│   │   ├── CORE_ARCHITECTURE.md  # schema + workflow + module contracts
│   │   └── decisions/            # ADRs
│   ├── founding/                 # CODEX_HANDOFF, NORTH_STAR, etc.
│   ├── onboarding/
│   │   ├── FIRST_RUN.md          # M5 walkthrough (the 6-step path)
│   │   └── WINDOWS_WSL2.md       # clean Windows 11 setup
│   └── product/                  # post-alpha planning
├── src/archonos/                 # ~1500 LOC of kernel code
│   ├── cli/main.py               # argparse dispatch
│   ├── core/ops.py               # init / status / healthcheck
│   ├── storage/
│   │   ├── db.py                 # single conn owner + migration runner
│   │   └── migrations/001_init.sql
│   ├── knowledge/                # chunk, import (md/txt/pdf + .archonosignore), search
│   ├── knowledge/sources/        # 8 paper-source modules
│   ├── memory/ops.py             # remember, recall
│   ├── workflows/                # registry, steps, engine (7 step types)
│   ├── llm/                      # ModelProvider + OpenAICompatProvider
│   └── scheduler.py              # 5-field cron + schedule CRUD
└── tests/
    ├── test_gate_m1.py           # 12
    ├── test_gate_m2.py           # 18
    ├── test_gate_m3.py           # 27
    ├── test_gate_m4.py           # 15
    ├── test_gate_m6.py           # 14
    ├── test_e2e_alpha.py         # 3
    ├── test_sources.py           # 20
    └── test_tier2.py             # 20
```

## Division of labor

- **Claude** — architecture, planning, decision records (`docs/architecture/decisions/`)
- **Codex** — implementation, tests, PRs per milestone
- **Hermes** — kernel owner; verifies gate tests per milestone; reports to Alfred via Telegram

Gate tests define done. A milestone is not complete until its gate test passes.

## Dependency footprint

| | Runtime | Dev |
|---|---|---|
| `pyproject.toml` | (none) | `pytest>=7.4` |
| `archonos` (the package) | stdlib only: `sqlite3`, `argparse`, `json`, `pathlib`, `dataclasses`, `hashlib`, `datetime`, `urllib.request`, `xml.etree.ElementTree`, `fnmatch`, `re`, `shlex`, `subprocess` | — |

`pdfminer.six` is **optional** — import still works on text-based PDFs without it; the stdlib fallback handles most academic papers. Install for better fidelity on complex layouts.

**Zero PyPI packages required to install.** `pip install -e ".[dev]"` brings in pytest and that's it.
