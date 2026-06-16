# Local Alpha — First Run

> A 6-step walkthrough that takes you from a clean machine to a working
> ArchonOS Next kernel. The M5 gate (per `docs/BASE_PLAN.md`).
>
> **Target environment:** Windows 11 + WSL2 (Ubuntu), 16 GB RAM, no cloud,
> no homelab. Python 3.11+ in the WSL distro.
>
> **Time required:** ~10 minutes for the install + 2 minutes for the walkthrough.
>
> **Result:** A local `archonos` CLI that can init a project, import
> documents, search them with FTS5, run declarative JSON workflows, and
> persist memories across processes. All data lives in
> `~/.archonos/default/archonos.db` (or `$ARCHONOS_HOME`).

---

## Prerequisites

You need:

- **Windows 11** with **WSL2** enabled (Ubuntu 22.04 or 24.04 recommended)
  - See `docs/onboarding/WINDOWS_WSL2.md` for setting up WSL2 from scratch
- **Python 3.11 or newer** inside WSL
  - WSL Ubuntu 24.04 ships with Python 3.12 by default — perfect
- **git** inside WSL
- **~500 MB** of free disk space
- **No network access required** for the walkthrough itself (the kernel
  is local-first; the M6 LLM provider layer is optional and not part of
  Local Alpha)

Verify before starting:

```bash
# Inside WSL
python3 --version        # must be >= 3.11
git --version
which pip3
```

---

## Step 1 — Install

```bash
git clone https://github.com/alfredaranas/archonos-next.git
cd archonos-next
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

**What this does:**
- Creates a project-local virtualenv at `./.venv/`
- Installs `archonos` in editable mode (the `archonos` console script is on PATH inside the venv)
- Installs `pytest` as a dev dependency for the test suite

**Verify the install:**

```bash
archonos --version
# Expected output: archonos 0.1.0
```

If `archonos` is not found, you forgot to activate the venv (`source .venv/bin/activate`).

**Verify the test suite passes on this machine:**

```bash
pytest tests/ -v
# Expected: 75 passed
```

If any test fails, the install is broken — re-create the venv (`rm -rf .venv` and start Step 1 over). Do not proceed with a broken install.

---

## Step 2 — init

```bash
mkdir ~/alpha-walkthrough && cd ~/alpha-walkthrough
archonos init
```

**Expected output:**

```
Created project 'default' at /home/<you>/.archonos/default/archonos.db
Applied migrations: [1]
```

**What this does:**
- Creates `~/.archonos/default/archonos.db` (the SQLite database — your data)
- Applies migration 001, which creates the full schema: `documents`, `chunks`, `memories`, `workflows`, `workflow_runs`, `settings`, `schema_version` + the FTS5 virtual tables (`chunks_fts`, `memories_fts`) and their sync triggers

**Override the location with `ARCHONOS_HOME`:**

```bash
ARCHONOS_HOME=/tmp/my-alpha archonos init
# Database lives at /tmp/my-alpha/default/archonos.db
```

This is the only environment variable the kernel reads. Useful for testing, multiple projects, or keeping everything on a USB stick.

**Idempotency check:**

```bash
archonos init
# Expected output: Verified project 'default' at .../archonos.db
```

Running `init` twice is safe — it re-applies only the migrations that haven't been applied yet.

---

## Step 3 — import

Build a small corpus and import it.

```bash
mkdir ./corpus
cat > ./corpus/alpha.md << 'EOF'
# Alpha: Python performance

Python is a dynamic, interpreted language. The CPython implementation
compiles source to bytecode, which is then executed by a virtual machine.
Memory management uses reference counting plus a cycle detector.

Key topics: python interpreter bytecode memory
EOF

cat > ./corpus/beta.md << 'EOF'
# Beta: Rust safety

Rust is a systems programming language focused on memory safety without
garbage collection. The borrow checker enforces aliasing rules at compile time.

Key topics: rust memory safety compiler
EOF

cat > ./corpus/gamma.md << 'EOF'
# Gamma: SQLite internals

SQLite is an embedded relational database. FTS5 is the full-text search
extension, providing ranked queries via BM25.

Key topics: sqlite fts5 search bm25
EOF

archonos import ./corpus
```

**Expected output:**

```
Documents: 3 added, 0 skipped (dupes)
Chunks:    3 added
```

**What this does:**
- Walks `./corpus` recursively
- For each `.md` or `.txt` file: computes SHA256, inserts a row in `documents`, splits the text into chunks, inserts each chunk
- Skips files whose SHA256 already exists (dedupe)
- FTS5 sync triggers auto-populate `chunks_fts`

**Re-import is safe:**

```bash
archonos import ./corpus
# Expected: 3 added, 0 skipped → now 0 added, 3 skipped
```

**Check the result:**

```bash
archonos status
# Expected: documents: 3, chunks: 3
```

---

## Step 4 — search

```bash
archonos search "python interpreter"
archonos search "memory safety"
archonos search "fts5 bm25"
archonos search "no_such_term_xyzzy"   # returns "No results found"
```

**Expected output (for `python interpreter`):**

```
alpha  (rank 0.50, chunk 1)
  # Alpha: Python performance Python is a dynamic, interpreted language. The CPython implementation compiles source to bytecode, which is then executed by a virtual machine. Memory management uses reference counting plus a cycle detector. Key topics: python interpreter bytecode memory
```

**What this does:**
- Builds an FTS5 MATCH expression from the query
- Queries `chunks_fts`, joins back to `chunks` and `documents`
- Ranks by BM25 (lower is better from FTS5's side; `rank` is the 0..1 normalized score)
- Returns the top `--limit` results (default 10)

---

## Step 5 — run a workflow

Build a workflow spec — a JSON file describing typed steps with templated arguments:

```bash
cat > ./brief.json << 'EOF'
{
  "name": "import-and-brief",
  "description": "Import a folder, search a topic, save a memory",
  "params": {"folder": "string", "topic": "string"},
  "steps": [
    {"id": "s1", "type": "import",  "args": {"path": "{{params.folder}}"}},
    {"id": "s2", "type": "search",  "args": {"query": "{{params.topic}}", "k": 5}},
    {
      "id": "s3",
      "type": "remember",
      "args": {
        "kind": "workflow_outcome",
        "body": "Brief on {{params.topic}}: {{steps.s2.summary}}"
      }
    }
  ]
}
EOF

archonos workflow register import-and-brief ./brief.json
archonos workflow list
archonos workflow run import-and-brief \
  --param folder=./corpus \
  --param topic=python
```

**Expected output:**

```
Run 1: succeeded (3 steps)
  [OK  ] s1 (import)
  [OK  ] s2 (search)
  [OK  ] s3 (remember)
```

**Inspect the audit trail:**

```bash
archonos workflow log 1
```

**Expected output:**

```
Run 1 (import-and-brief): succeeded
  started:  2026-...
  finished: 2026-...
  steps:    3
  [OK  ] s1 (import)  outputs=[chunks_added, docs_added, errors, skipped_dupes]
  [OK  ] s2 (search)  outputs=[count, hits, summary]
  [OK  ] s3 (remember) outputs=[id, kind]
```

Every run — successful or failed — leaves a row in `workflow_runs` with the full step-by-step log. This is the audit trail.

**Step types (v1, closed set):** `import`, `search`, `remember`, `recall`, `shell` (gated by `allow_shell=true` in settings), `ask` (M6 stub).

---

## Step 6 — persist memory

```bash
archonos remember --kind decision \
  "Local Alpha walkthrough complete: import, search, workflow, remember all work"
archonos remember --kind lesson \
  "FTS5 sync triggers mean a write is immediately queryable"
archonos remember --kind note "Walrus operator can be overused"

archonos recall "Local Alpha walkthrough"
archonos recall --kind lesson "FTS5"
archonos recall                       # most recent
```

**Expected output (for `archonos recall "Local Alpha walkthrough"`):**

```
[decision] 2026-... (rank 0.20, id=1)
  Local Alpha walkthrough complete: import, search, workflow, remember all work
```

**Cross-process persistence — quit and come back:**

```bash
exit     # or close the terminal
# later, in a fresh shell
source /path/to/archonos-next/.venv/bin/activate
archonos recall "Local Alpha walkthrough"
# Same memory is still there.
```

The FTS5 sync triggers keep `memories` and `memories_fts` in lockstep, so a memory written in one process is searchable in any future process. The persistence is the database, not the process.

---

## Sanity check

```bash
archonos status
archonos healthcheck
```

**Expected `status`:**

```
project:         default
db:              /home/<you>/.archonos/default/archonos.db
schema:          v1
documents:       3
chunks:          3
memories:        3
workflows:       1
workflow_runs:   1
```

**Expected `healthcheck` (all 5 checks OK):**

```
[OK  ] db_reachable: /home/<you>/.archonos/default/archonos.db
[OK  ] schema_version: have v1, latest v1
[OK  ] write_test: settings write ok
[OK  ] fts_tables: 2/2 fts tables
[OK  ] disk_space: <free MB>MB free
```

If any check fails, see the troubleshooting section below.

---

## What you can do now

You have a working local ArchonOS kernel. From here:

- **Import your own documents:** `archonos import ~/Documents/notes/` (only `.md` and `.txt` for now — PDF support is post-alpha per spec §8)
- **Build a personal workflow library:** write JSON specs in `~/.archonos/default/workflows/` and `archonos workflow register <name> <spec.json>`
- **Track decisions and lessons:** use `archonos remember --kind decision ...` and `archonos recall "topic"` to query them later
- **Compose workflows that compose memories:** the `recall` step type returns memories; the `remember` step type writes them; chain them

**What you cannot do yet (post-alpha per spec):**

- Embeddings / vector search — banned until M6+ per CORE_ARCHITECTURE §8; FTS5 is the search story
- LLM-backed `ask` step — M6+; the registry entry exists but is a no-op stub
- MCP server — explicitly deferred until after Local Alpha
- Desktop UI / agents / Supabase — all deferred per BASE_PLAN.md

---

## Troubleshooting

**`archonos: command not found`** — you forgot to activate the venv:
```bash
cd /path/to/archonos-next
source .venv/bin/activate
which archonos
```

**`FileNotFoundError: No database at ...archonos.db`** — you skipped Step 2 or you're pointing at a different `ARCHONOS_HOME`:
```bash
echo $ARCHONOS_HOME   # should be unset, or point at the same dir
archonos init
```

**Search returns no results for terms you know are in the corpus** — the file might have been skipped (only `.md` and `.txt` are supported). Check:
```bash
archonos status    # did documents/chunks go up?
```

**A workflow run fails** — read the audit trail:
```bash
archonos workflow log <run_id>
# Look for [FAIL] steps and the error message
```

**Want a fresh start** — nuke the home dir:
```bash
rm -rf ~/.archonos
archonos init
```

---

## Verifying M5 is done

The M5 gate per `docs/BASE_PLAN.md`:
> *"clean-machine walkthrough documented in docs/onboarding/, completed by someone who is not the author."*

The documentation half is this file. The "completed by someone who is not the author" half requires a fresh user (not the person who wrote the spec) running Steps 1–6 on a clean Windows 11 + WSL2 machine. The kernel half of the gate is automated in `tests/test_e2e_alpha.py` and runs as part of `pytest tests/`.

**Single-command verification (kernel half):**

```bash
cd /path/to/archonos-next
source .venv/bin/activate
pytest tests/ -v
# Expected: 75 passed
```

If 75 tests pass, the kernel is verified. M5 is documented. Local Alpha is shipped.
