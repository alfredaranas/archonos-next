# ArchonOS Next — Product Specification

> Self-hosted AI Knowledge Operating System for developers & indie hackers.

---

## Product Vision

**"Your private AI brain in a single command."**

A self-hosted, local-first knowledge OS that lets anyone run a personal AI with memory, knowledge search, and workflows — without cloud dependencies.

---

## Target Users

| Persona | Use Case |
|---------|----------|
| Indie hackers | Personal AI assistant, coding memory |
| Developers | Project knowledge base, code docs |
| Researchers | Paper management, notes |
| Traders | Research, setups, analysis |
| Makers | Wiki, documentation, ideas |

---

## Core Features

### 1. Knowledge Base
- Import: markdown, txt, pdf, docx
- Search: Full-text (FTS5) + semantic (embeddings)
- Chunking: Automatic with overlap

### 2. Memory
- Remember: Store decisions, lessons, notes
- Recall: Search across memories
- Types: decision, lesson, note, workflow_outcome

### 3. Workflows
- Register JSON workflows
- Run: sequential steps
- Audit: full run logs

### 4. AI Integration (Optional)
- Local: llama.cpp, ollama
- Cloud: OpenAI, MiniMax, Anthropic
- No API key = degraded mode (FTS5 still works)

---

## Technical Stack

### Core (Required)
- **Python 3.11+** — stdlib only for M1-M5
- **SQLite** — all data, WAL mode
- **FTS5** — full-text search
- **Docker** — one-command deployment

### Optional (Extensions)
- **Ollama** — local embeddings & inference
- **OpenAI API** — cloud embeddings
- **MiniMax API** — reasoning

---

## Docker Deployment

### Quick Start
```bash
# One command
docker run -p 8090:8090 archonos/archonos-next

# With persistent data
docker run -p 8090:8090 \
  -v ./data:/data \
  archonos/archonos-next
```

### First Run
```bash
# Initialize
docker exec archonos init

# Import docs
docker exec archonos import ./docs

# Search
docker exec archonos search "my query"

# Remember
docker exec archonos remember "decision: use SQLite"

# Recall
docker exec archonos recall "what decisions did we make"
```

---

## Architecture

```
┌─────────────────────────────────────┐
│           Docker Container           │
│  ┌─────────────────────────────┐   │
│  │      CLI (argparse)         │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │    ArchonOS Core (Python)   │   │
│  │  • Knowledge                │   │
│  │  • Memory                   │   │
│  │  • Workflows                │   │
│  └─────────────────────────────┘   │
│  ┌─────────────────────────────┐   │
│  │      SQLite (WAL)           │   │
│  │  • documents               │   │
│  │  • chunks                   │   │
│  │  • memories                 │   │
│  │  • workflows                │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
            │
            ▼ (optional)
┌─────────────────────────────────────┐
│         Ollama (local)              │
│  • Embeddings (nomic-embed-text)    │
│  • Inference (llama3, etc.)         │
└─────────────────────────────────────┘
```

---

## CLI Commands

```bash
# Setup
archonos init                    # Initialize project
archonos status                  # Show counts

# Knowledge
archonos import <path>           # Import files
archonos search <query> [-k 10]  # Search

# Memory
archonos remember <text> [--kind decision|lesson|note]
archonos recall <query> [-k 10]

# Workflows
archonos workflow register <file.json>
archonos workflow list
archonos workflow run <name> [--param k=v]
archonos workflow log <run_id>

# AI (optional)
archonos ask <question>          # RAG + LLM
```

---

## Data Storage

```
~/.archonos/
└── default/
    └── archonos.db      # SQLite (all data)
```

**Persisted via Docker volume:**
```bash
-v ./data:/data
```

---

## API Server (Optional)

```bash
# Enable HTTP API
archonos serve --port 8090

# Endpoints
GET  /api/health
GET  /api/status
GET  /api/search?q=<query>
POST /api/memory
GET  /api/memory?q=<query>
POST /api/workflow/run
```

---

## Product Tiers

### 🥉 Community (Free)
- SQLite + FTS5
- CLI only
- No embeddings (keyword search only)
- Docker: `archonos/archonos-next:latest`

### 🥈 Pro ($9/mo)
- Everything in Community
- Ollama embeddings (local)
- HTTP API
- Web UI (basic)
- Docker: `archonos/archonos-next:pro`

### 🥇 Team ($29/mo)
- Everything in Pro
- Multi-user support
- Team memory
- Cloud sync (optional)
- Priority support

---

## Competition

| Product | ArchonOS Advantage |
|---------|-------------------|
| Obsidian | AI-native, CLI-first, programmable |
| Notion | Self-hosted, local-first |
| Qdrant | Simpler, all-in-one |
| Supabase | Pre-built, not "AI OS" |

---

## Roadmap

### MVP (v1.0)
- [x] CLI kernel (M1)
- [x] Knowledge import + search (M2)
- [ ] Memory remember + recall (M4)
- [ ] Workflow engine (M3)
- [ ] Docker build + one-command run

### v1.1
- [ ] Web UI (minimal)
- [ ] HTTP API
- [ ] Basic search UI

### v2.0
- [ ] Ollama integration (embeddings)
- [ ] Semantic search
- [ ] Pro tier launch

### v2.1
- [ ] Multi-user support
- [ ] Team workflows
- [ ] Cloud sync (optional)

---

## Pricing Logic

| Tier | Price | Margin | Target |
|------|-------|--------|--------|
| Community | $0 | N/A | Adoption |
| Pro | $9/mo | ~70% | Power users |
| Team | $29/mo | ~80% | Small teams |

**Cost estimate:**
- VPS (1 CPU, 2GB): $5/mo
- Ollama (optional): runs locally

---

## Success Metrics

- ⭐ GitHub stars
- 📥 Docker pulls
- 💬 Community contributions
- 💰 MRR (monthly recurring revenue)

---

## Open Questions

1. License? (AGPL, commercial, dual?)
2. Brand name? (ArchonOS? Rebrand?)
3. Hosting the registry? (Docker Hub, GHCR)
4. Payment processor? (Stripe, Paddle)
5. Support model? (Discord, email, docs)

---

*Last updated: 2026-06-11*
