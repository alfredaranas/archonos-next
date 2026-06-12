# ArchonOS Next — Onboarding

> Local Alpha (M5). Install ArchonOS Next on Windows 11 + WSL2 in under 10 minutes, no cloud required.

## What you get

A local-first AI operating system with:

- **Knowledge base** — import documents (md/txt/pdf), full-text search with ranking
- **Memory** — durable across sessions, recall decisions/lessons/notes by query
- **Workflows** — JSON-spec automation with audit logs
- **LLM provider** — optional (M3, OpenAI, Anthropic), works without

All data lives in a single SQLite file on your machine. No account, no cloud, no telemetry.

## Requirements

- Windows 11 + WSL2 (Ubuntu or Kali), or any Linux/macOS
- Python 3.10+
- 100MB free disk
- Optional: `git` for cloning, an LLM API key for chat

## Install

```bash
# 1. clone
git clone https://github.com/alfredaranas/archonos-next.git ~/archonos-next
cd ~/archonos-next

# 2. virtualenv + install
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 3. initialize
archonos init
archonos healthcheck
```

Expected output:

```
Created project 'default' at /home/you/.archonos/default/archonos.db
Applied migrations: [1]
[OK  ] db_reachable: /home/you/.archonos/default/archonos.db
[OK  ] schema_version: have v1, latest v1
[OK  ] write_test: settings write ok
[OK  ] fts_tables: 2/2 fts tables
[OK  ] disk_space: 87234MB free
```

If all 5 checks are OK, you're running.

## First use — import + search

```bash
# import a folder of notes
archonos import ~/notes/

# search them
archonos search "what I learned about FTS5"
```

Search returns ranked snippets with highlighted matches.

## Memory — survives across sessions

```bash
archonos remember "Use INTEGER PKs not UUIDs for FTS5 tables" --kind lesson
archonos remember "Adopted SQLite as canonical local store" --kind decision

# later, in any session:
archonos recall --kind decision
archonos recall --query "FTS5"
```

Memories live in the same SQLite database. Survive reboot, process restart, anything.

## Workflows

A workflow is a JSON spec — a sequence of typed steps. Example `daily-brief.json`:

```json
{
  "name": "daily-brief",
  "description": "Import inbox, search a topic, save a memory",
  "steps": [
    {"name": "ingest", "action": "import", "args": {"path": "~/inbox/"}},
    {"name": "find",   "action": "search", "args": {"query": "open questions"}},
    {"name": "log",    "action": "remember", "args": {"kind": "state"}}
  ]
}
```

```bash
archonos workflow-register daily-brief --spec "$(cat daily-brief.json)"
archonos workflow-list
archonos workflow-run daily-brief
```

Each run is logged in `workflow_runs` with start time, end time, status, per-step audit trail.

## Status anywhere

```bash
archonos status
```

```
project:         default
db:              /home/you/.archonos/default/archonos.db
schema:          v1
documents:       42
chunks:          187
memories:        9
workflows:       1
workflow_runs:   3
```

## Multiple projects

```bash
archonos init --project research
archonos init --project trading

archonos import ~/papers/ --project research
archonos search "transformer attention" --project research
```

Each project gets its own SQLite database at `~/.archonos/<name>/archonos.db`. No cross-contamination.

## Optional — LLM chat

If you have an API key:

```bash
export MINIMAX_API_KEY="sk-..."
archonos chat "Explain my notes on FTS5"
```

Providers supported out of the box: `minimax` (default), `openai`, `anthropic`. Set the matching `*_API_KEY` env var.

Without a key set, every other command still works — the LLM layer is strictly optional.

## Verifying the install

The full gate test suite proves everything works:

```bash
pytest tests/ -v
```

40 tests should pass: 8 M1 (CLI), 13 M2 (knowledge), 9 M3 (workflows), 10 M4 (memory).

## Where things live

```
~/.archonos/<project>/archonos.db   # all your data, one file
~/archonos-next/                    # the code
```

To back up everything: copy `~/.archonos/`. To wipe: delete it.

## Troubleshooting

**`pip install` fails** — install python3-venv: `sudo apt install python3-venv` (Ubuntu/Kali) or use Python 3.10+

**`No database at ...` errors** — run `archonos init` first

**`fts_tables` healthcheck fails** — your SQLite is built without FTS5. Reinstall Python or use `apt install sqlite3` to get a modern SQLite

**Search returns no results after import** — check `archonos status` shows chunks > 0. If chunks are present but search is empty, the FTS index may not have synced — re-import will fix it

## What's next

- M6 (LLM provider polish) — ready
- Knowledge packs — bundle domain content with archonos-next as a kernel (see `knowledge-packs/sonography/` for the reference implementation)
- Desktop UI — future, on top of the stable CLI

## Get help

- GitHub: https://github.com/alfredaranas/archonos-next
- Architecture: `docs/architecture/CORE_ARCHITECTURE.md`
- Plan: `docs/BASE_PLAN.md`
