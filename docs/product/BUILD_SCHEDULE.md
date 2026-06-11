# ArchonOS Build Schedule

> 8-week execution plan with milestone checkpoints.

---

## Schedule Overview

| Week | Dates | Phase | Milestones | Checkpoint? |
|------|-------|-------|------------|--------------|
| 1 | Jun 12-18 | Foundation | M1 (CLI Kernel) | ✅ |
| 2 | Jun 19-25 | Foundation | M2 (Knowledge) | ✅ |
| 3 | Jun 26-Jul 2 | Foundation | M3 (Workflows) + M4 (Memory) | ⏸️ |
| 4 | Jul 3-9 | Infrastructure | Docker + Local Alpha | ✅ |
| 5 | Jul 10-16 | Intelligence | M6 (LLM Provider) | ⏸️ |
| 6 | Jul 17-23 | Intelligence | RAG Pipeline + Approval UI | |
| 7 | Jul 24-30 | Polish | Web UI Pages | |
| 8 | Jul 31-Aug 6 | Ship | Docs + Landing + Launch | ✅ |

---

## Detailed Breakdown

### Week 1: CLI Kernel (M1)
**Jun 12-18**

- [ ] `archonos init` — creates ~/.archonos/ + SQLite db
- [ ] `archonos status` — shows project, db, counts
- [ ] `archonos healthcheck` — db reachable, write test, disk space
- [ ] Exit codes: 0 ok, 1 user error, 2 system error
- [ ] Idempotent init

**Checkpoint 1:** CLI basic commands work

---

### Week 2: Knowledge Base (M2)
**Jun 19-25**

- [ ] Schema: documents, chunks, settings tables
- [ ] `archonos import <path>` — md/txt/pdf → chunks
- [ ] FTS5 search: `archonos search "<query>"`
- [ ] Import 100 docs, search returns ranked results <200ms

**Checkpoint 2:** Knowledge import + search works

---

### Week 3: Workflows + Memory (M3-M4)
**Jun 26-Jul 2**

- [ ] Schema: workflows, workflow_runs tables
- [ ] `archonos workflow register/list/run <name>`
- [ ] Audit log per run
- [ ] Schema: memories table
- [ ] `archonos remember` / `archonos recall`
- [ ] Memory persists across sessions

**Checkpoint 3:** Workflows and memory work

---

### Week 4: Docker + Local Alpha
**Jul 3-9**

- [ ] Dockerfile builds successfully
- [ ] `docker run archonos/archonos:latest` works
- [ ] Data persists via volume mount
- [ ] Clean-machine walkthrough documented

**Checkpoint 4:** Docker deployment works

---

### Week 5: LLM Provider (M6)
**Jul 10-16**

- [ ] ModelProvider contract defined
- [ ] OpenAI-compatible provider (covers MiniMax, OpenAI, vLLM)
- [ ] `archonos ask` — retrieval + synthesis
- [ ] Graceful fallback when no API key

**Checkpoint 5:** LLM integration works

---

### Week 6: RAG + Approval UI
**Jul 17-23**

- [ ] Full RAG pipeline (search → context → ask)
- [ ] Approval gate system UI
- [ ] Workflow approval/deny buttons
- [ ] Approval settings (ask/yolo/deny)

**Checkpoint 6:** AI capabilities + approval gates work

---

### Week 7: Web UI Polish
**Jul 24-30**

- [ ] Dashboard page
- [ ] Knowledge search page
- [ ] Memory recall page
- [ ] Workflow management page
- [ ] Settings page

**Checkpoint 7:** Full Web UI functional

---

### Week 8: Ship
**Jul 31-Aug 6**

- [ ] Documentation (docs.archonos.app)
- [ ] Landing page design
- [ ] Docker Hub release
- [ ] GitHub release + stars campaign

**Checkpoint 8:** Product launched

---

## Checkpoint Options

I recommend checking in at these milestones:

| Option | Checkpoints | Frequency |
|--------|-------------|-----------|
| **A (Recommended)** | 1, 4, 8 | Every 2 weeks |
| **B** | 1, 3, 5, 8 | Weekly then biweekly |
| **C** | Every milestone | Weekly |

---

## Questions for You

1. **Which checkpoint option do you prefer?** (A/B/C)
2. **Any weeks you know you'll be busy?** (adjust accordingly)
3. **Want me to start with Week 1 now?**

---

*Schedule created: 2026-06-11*
