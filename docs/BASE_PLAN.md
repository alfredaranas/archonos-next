# ArchonOS Next — Base Plan v1.0

> Canonical milestone plan. Derived from docs/founding/CODEX_HANDOFF.md with one amendment: Milestone 6 (LLM Provider Layer) added — the founding doc built a knowledge CLI with no inference path. An AI OS must call a model.

**Status:** Architecture frozen · Local Alpha first · 2026-06-09

---

## Milestone 0.5 — Repository Foundation

- [ ] `pyproject.toml` — package `archonos`, Python 3.11+, stdlib-first
- [ ] `src/archonos/{cli,core,config,storage,knowledge,memory,workflows}/` package layout
- [ ] `tests/` with pytest scaffold + first smoke test
- [ ] `docs/{founding,architecture,onboarding,product}/`
- [ ] README — install + quickstart

**Gate:** `pip install -e . && pytest` passes clean on WSL2.

## Milestone 1 — CLI Kernel

- [ ] `archonos init` — creates `~/.archonos/` + project SQLite db + settings
- [ ] `archonos status` — project, db path, counts (documents/chunks/memories/workflows)
- [ ] `archonos healthcheck` — db reachable, schema version, write test, disk space

**Gate:** all 3 commands exit 0 on fresh WSL2; `init` is idempotent.

## Milestone 2 — Local Knowledge Base

- [ ] Schema: `documents`, `chunks`, `settings` (per founding doc — no redesign without approval)
- [ ] `archonos import <path>` — md/txt/pdf → documents + chunks
- [ ] FTS5 search foundation: `archonos search "<query>"`
- [ ] NOTE: FTS5 `content_rowid` requires INTEGER rowid — do not use UUID text PKs (lesson from legacy kb_local_sync)

**Gate:** import 100 mixed docs, search returns ranked results < 200ms.

## Milestone 3 — Workflow Engine

- [ ] Schema: `workflows`, `workflow_runs`
- [ ] `archonos workflow register/list/run <name>`
- [ ] Audit log per run: start/end, steps, outcome, errors

**Gate:** register + run a 3-step workflow; run visible in audit trail.

## Milestone 4 — Persistent Memory

- [ ] Schema: `memories` — project memory, workflow memory, decisions
- [ ] `archonos remember "<text>"` / `archonos recall "<query>"`
- [ ] Recall uses FTS5 over memories

**Gate:** memory written in session A is recalled in session B after process restart.

## Milestone 5 — Local Alpha

End-to-end on Windows 11 + WSL2 + 16GB RAM, no cloud, no homelab:

1. Install → 2. init → 3. import → 4. search → 5. run workflow → 6. persist memory

**Gate:** clean-machine walkthrough documented in docs/onboarding/, completed by someone who is not the author.

## Milestone 6 — LLM Provider Layer (amendment)

The founding doc has no inference path. Added as the first post-alpha milestone — minimal, provider-agnostic:

- [ ] `ModelProvider` contract: `complete(messages, tools=None) -> response` — one interface, no framework
- [ ] First provider: OpenAI-compatible HTTP (targets MiniMax M3 via OpenRouter; also covers OpenAI/local vLLM endpoints for free)
- [ ] `archonos ask "<question>"` — retrieval (M2 search) + synthesis (provider)
- [ ] API key via settings table / env var; no key = degraded mode, everything else still works
- [ ] Still zero required cloud: provider optional, knowledge/memory/workflows fully functional without it

**Gate:** `archonos ask` answers a question grounded in imported documents via M3 API; with no key set, command fails gracefully and all M1–M5 gates still pass.

## Deferred (unchanged from founding doc)

MCP runtime · Desktop UI · agents · vector DB · Supabase · multi-device · legacy adapters. Future layers on top of stable alpha. MCP note: when it comes, MCP is transport over ArchonOS Core — never business logic in the MCP layer.

---

## Sequencing

```
0.5 → 1 → 2 → 3 → 4 → 5 (Local Alpha) → 6 (first AI capability)
```

Codex owns implementation per milestone. Claude owns this plan. Schema and architecture changes require documented approval. Validation gates are falsifiable — a milestone is not DONE until its gate passes.
