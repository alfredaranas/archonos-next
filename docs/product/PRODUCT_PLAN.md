# ArchonOS Product Plan — From Prototype to Product

> A comprehensive technical and product strategy for turning the ArchonOS prototype into a sellable, self-hosted AI OS.
> 
> **Status:** Planning · **Version:** 1.0 · **Date:** 2026-06-11

---

## Executive Summary

ArchonOS is not a "knowledge base" or a "chatbot" — it is a **Knowledge Operating System** with built-in approval gates. This is a fundamentally different category:

| Traditional Tools | ArchonOS |
|-----------------|----------|
| Files you browse | Knowledge you query |
| Apps you run | Workflows you approve |
| Data you store | Memory that persists |
| Manual processes | Gated automation |

The product vision: **"Your private AI brain with guardrails."**

This plan outlines the technical execution, UI design, and go-to-market strategy to ship a sellable product within 8 weeks.

---

## Part I: Product Architecture

### 1.1 The Three Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                      ARCHONOS STACK                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                    PRESENTATION                           │   │
│   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │   │
│   │   │    CLI       │  │  Web UI     │  │   API       │   │   │
│   │   │  (typer)    │  │  (minimal)  │  │  (FastAPI)  │   │   │
│   │   └─────────────┘  └─────────────┘  └─────────────┘   │   │
│   └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                     CORE ENGINE                           │   │
│   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │   │
│   │   │  Knowledge  │  │   Memory    │  │  Workflows  │   │   │
│   │   │   (FTS5)   │  │  (FTS5)     │  │   (Engine)  │   │   │
│   │   └─────────────┘  └─────────────┘  └─────────────┘   │   │
│   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │   │
│   │   │   Config    │  │   Provider  │  │   Gates     │   │   │
│   │   │  (Settings) │  │   (LLM)     │  │  (Approval) │   │   │
│   │   └─────────────┘  └─────────────┘  └─────────────┘   │   │
│   └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                      STORAGE                             │   │
│   │           SQLite (WAL) · All data local                 │   │
│   │         ~/.archonos/<project>/archonos.db              │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Core Components

#### Knowledge Engine
- **Import:** md, txt, pdf → chunks → FTS5
- **Search:** Full-text search with ranking
- **Query:** Natural language over local knowledge

#### Memory System
- **Remember:** Store decisions, lessons, notes
- **Recall:** Search across all memories
- **Types:** decision, state, lesson, note, workflow_outcome

#### Workflow Engine
- **Define:** JSON workflow specs
- **Execute:** Sequential steps with audit log
- **Approve:** Human-in-the-loop gates

#### Approval Gate System
```yaml
approvals:
  mode: ask       # ask | yolo | deny
  # ask: Pauses workflow, waits for human approval
  # yolo: Auto-approve (for trusted workflows)
  # deny: No execution without explicit approval
```

#### Provider Layer (Optional)
- **Local:** Ollama, llama.cpp
- **Cloud:** OpenAI, MiniMax, Anthropic
- **No key:** Degraded mode (FTS5 search still works)

---

## Part II: UI/UX Design

### 2.1 Design Philosophy

The UI must match the sophistication of the underlying system while remaining approachable. Drawing from your existing dashboard's aesthetic:

**Principles:**
1. **Dark theme by default** — Professional, reduces eye strain
2. **Information-dense** — Show status at a glance
3. **Terminal-inspired** — Monospace fonts, clear hierarchy
4. **Accent colors** — Green (success), Yellow (pending), Red (error), Cyan (info)

### 2.2 Color Palette

```css
:root {
  /* Backgrounds */
  --bg-primary: #0d1117;
  --bg-secondary: #161b22;
  --bg-tertiary: #21262d;
  --bg-elevated: #30363d;
  
  /* Text */
  --text-primary: #e6edf3;
  --text-secondary: #8b949e;
  --text-muted: #6e7681;
  
  /* Accents */
  --accent-cyan: #58a6ff;
  --accent-green: #3fb950;
  --accent-yellow: #d29922;
  --accent-red: #f85149;
  --accent-purple: #a371f7;
  
  /* Borders */
  --border-default: #30363d;
  --border-muted: #21262d;
}
```

### 2.3 Layout Structure

```
┌──────────────────────────────────────────────────────────────────┐
│  ┌──────┐                                                        │
│  │ LOGO │  ARCHONOS              [Status] [Settings] [Help]     │
│  └──────┘                                                        │
├──────────────────────────────────────────────────────────────────┤
│ ┌────────┐ ┌─────────────────────────────────────────────────┐  │
│ │        │ │                                                  │  │
│ │ NAV    │ │              MAIN CONTENT                        │  │
│ │        │ │                                                  │  │
│ │ □ Dash │ │  ┌──────────────────────────────────────────┐   │  │
│ │ □ KB   │ │  │                                          │   │  │
│ │ □ Memo │ │  │         Dynamic content area             │   │  │
│ │ □ Work │ │  │                                          │   │  │
│ │ □ Jobs │ │  │                                          │   │  │
│ │ □ API  │ │  └──────────────────────────────────────────┘   │  │
│ │        │ │                                                  │  │
│ └────────┘ └─────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│  Status: ● Online  |  v1.0.0  |  SQLite  |  CPU: 12%          │
└──────────────────────────────────────────────────────────────────┘
```

### 2.4 Page Designs

#### Dashboard (Home)
```
┌─────────────────────────────────────────────────────────────────┐
│  OVERVIEW                                                        │
│                                                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ CLUSTER  │ │ KNOWLEDGE │ │ MEMORY   │ │ WORKFLOW │          │
│  │ 4/4      │ │ 1,234    │ │ 89       │ │ 12       │          │
│  │ nodes    │ │ chunks    │ │ items    │ │ active   │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│                                                                 │
│  RECENT ACTIVITY                                                 │
│  ──────────────────────────────────────────────────────────    │
│  ● 07:35  Import completed: 23 documents                       │
│  ● 07:32  Workflow "daily-brief" approved                      │
│  ● 07:30  Memory: "Decision: use FTS5 for search"              │
│  ● 07:28  Search: "czmil lidar setup" → 12 results            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### Knowledge Search
```
┌─────────────────────────────────────────────────────────────────┐
│  KNOWLEDGE BASE                              [Import] [Settings] │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  🔍 Search knowledge...                              [→]  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  RESULTS (12 found in 45ms)                                     │
│  ──────────────────────────────────────────────────────────    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ▸ LIDAR Setup Guide                                    │   │
│  │    ...the sensor array requires precise calibration...  │   │
│  │    📄 docs/lidar/setup.md · 95% match · chars: 2,341  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ▸ Czmil Configuration                                 │   │
│  │    ...configuration file follows XML schema...          │   │
│  │    📄 docs/czmil/config.md · 87% match · chars: 1,892  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### Workflows & Approval
```
┌─────────────────────────────────────────────────────────────────┐
│  WORKFLOWS                                                    │
│                                                                 │
│  ACTIVE WORKFLOWS                          [+ New] [Register]  │
│  ──────────────────────────────────────────────────────────    │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ○ daily-brief                                           │   │
│  │    Import docs → Search topic → Remember summary         │   │
│  │    ⏳ PENDING APPROVAL                                   │   │
│  │                                                           │   │
│  │    Steps: 1/3 complete                                   │   │
│  │    [Approve] [Deny] [View Details]                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ● import-archive                                        │   │
│  │    Scan folder → Import all → Index                     │   │
│  │    ✓ Completed 2 min ago                                │   │
│  │    [View Log] [Run Again]                               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  APPROVAL SETTINGS                                             │
│  ──────────────────────────────────────────────────────────    │
│  Mode: [Ask ●] [Yolo] [Deny]                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.5 Technical UI Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Framework** | FastAPI + HTMX | Lightweight, no JS bloat |
| **Styling** | Tailwind CSS | Rapid development |
| **Templates** | Jinja2 | Python-native |
| **Icons** | Lucide | Clean, consistent |
| **Charts** | Chart.js | Simple, embeddable |

**Key insight:** Use HTMX for interactivity without React complexity. The UI should feel like a modern terminal.

---

## Part III: Technical Roadmap

### Phase 1: Foundation (Weeks 1-2)

| Week | Deliverable | Owner |
|------|-------------|-------|
| 1 | Complete M1-M4 (CLI core) | Implementation |
| 1 | Docker build + one-command run | Implementation |
| 1 | SQLite schema finalized | Design |
| 2 | Basic Web UI (dashboard + search) | Frontend |
| 2 | Local Alpha test (WSL2) | QA |

**Milestone:** `docker run archonos/archonos:latest` works → proceed.

### Phase 2: Intelligence (Weeks 3-4)

| Week | Deliverable | Owner |
|------|-------------|-------|
| 3 | Provider layer (OpenAI-compatible) | Implementation |
| 3 | RAG pipeline (search + ask) | Implementation |
| 4 | Approval gate UI | Frontend |
| 4 | Ollama integration (optional) | Implementation |

**Milestone:** `archonos ask` works with local or cloud LLM.

### Phase 3: Polish (Weeks 5-6)

| Week | Deliverable | Owner |
|------|-------------|-------|
| 5 | Workflow editor UI | Frontend |
| 5 | Memory recall UI | Frontend |
| 6 | Settings/configuration UI | Frontend |
| 6 | Performance tuning | Optimization |

**Milestone:** All features accessible via UI.

### Phase 4: Ship (Weeks 7-8)

| Week | Deliverable | Owner |
|------|-------------|-------|
| 7 | Documentation (docs.archonos.app) | Content |
| 7 | Landing page | Design |
| 8 | Docker Hub release | DevOps |
| 8 | Community launch | Marketing |

**Milestone:** Product publicly available.

---

## Part IV: Product Tiers

### Tier Comparison

| Feature | Community | Pro | Team |
|---------|-----------|-----|------|
| **Price** | $0 | $9/mo | $29/mo |
| **Storage** | SQLite | SQLite | SQLite |
| **Knowledge chunks** | 10,000 | Unlimited | Unlimited |
| **Memory items** | 1,000 | Unlimited | Unlimited |
| **Workflows** | 5 | Unlimited | Unlimited |
| **Search** | FTS5 | FTS5 + Semantic* | FTS5 + Semantic* |
| **Web UI** | ❌ | ✅ | ✅ |
| **API** | ❌ | ✅ | ✅ |
| **Approval Gates** | ✅ | ✅ | ✅ |
| **Multi-user** | ❌ | ❌ | ✅ |
| **Team Memory** | ❌ | ❌ | ✅ |
| **Priority Support** | ❌ | ❌ | ✅ |

*Semantic search requires embeddings (Ollama or cloud).

### Community Tier Positioning

**Purpose:** Adoption + word-of-mouth

- Free forever
- Limited but functional
- "Good enough" for individuals
- Powers the freemium funnel

### Pro Tier Positioning

**Purpose:** Power users + small projects

- $9/month = $108/year
- Target: Developers, indie hackers
- Full feature access
- Self-hosted = no subscription required (user hosts themselves)

### Team Tier Positioning

**Purpose:** Small teams + businesses

- $29/month = $348/year
- Target: 2-10 person teams
- Multi-user collaboration
- Shared team memory

---

## Part V: Competitive Analysis

### Landscape

| Product | Category | ArchonOS Advantage |
|---------|----------|-------------------|
| **Obsidian** | Local notes | AI-native, workflows, approval gates |
| **Notion** | All-in-one wiki | Self-hosted, local-first, privacy |
| **Qdrant** | Vector database | Complete OS, not just DB |
| **Supabase** | Backend platform | Pre-built AI OS, not just DB |
| **LangChain** | LLM framework | Batteries included, opinionated |
| **AutoGPT** | Autonomous agents | Approval gates, human-in-loop |
| **Mem Free** | Open-source Mem | Self-hosted, extensible |

### Differentiation

**Key differentiator:** "KB as OS" + "Approval Gates"

No other product combines:
1. Knowledge base as the operating system
2. Built-in approval gates for automation
3. Local-first (no cloud required)
4. Memory that persists across sessions

---

## Part VI: Go-to-Market Strategy

### Launch Sequence

1. **Week 8:** GitHub release + Docker Hub
2. **Week 9:** Product Hunt launch
3. **Week 10:** Hacker News thread
4. **Week 11:** Dev.to blog post
5. **Week 12:** YouTube demo video

### Messaging

**Headline:** "Your private AI brain with guardrails."

**Subhead:** A self-hosted knowledge operating system that remembers, thinks, and waits for your approval.

**Pitch:**
- Built your own AI assistant that actually knows your stuff
- Approval gates keep automation under your control
- 100% local — your data never leaves your machine
- From the creator of ArchonOS (your working prototype)

### Community Building

| Channel | Action |
|---------|--------|
| **GitHub** | Open-source core, Pro/Team closed |
| **Discord** | Community discussion + support |
| **Twitter/X** | Demo videos, updates |
| **Reddit** | r/selfhosted, r/aiagents |

---

## Part VII: Technical Deep Dives

### 7.1 Approval Gate Implementation

```python
# Approval states
class ApprovalState(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"

# Workflow execution with gates
async def execute_workflow(workflow: Workflow, params: dict):
    for step in workflow.steps:
        if step.requires_approval:
            # Pause and wait
            state = await request_approval(step)
            if state == ApprovalState.DENIED:
                return ExecutionResult(status="denied")
        
        # Execute step
        result = await step.execute()
        
    return ExecutionResult(status="completed")
```

### 7.2 RAG Pipeline

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Query     │───▶│   Search    │───▶│   Build     │
│   "question"│    │   (FTS5)    │    │   Context   │
└─────────────┘    └─────────────┘    └─────────────┘
                                              │
                                              ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Answer    │◀───│   LLM       │◀───│   Prompt    │
│   "answer"  │    │   Provider  │    │   Template  │
└─────────────┘    └─────────────┘    └─────────────┘
```

### 7.3 Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY static/ ./static/
COPY templates/ ./templates/

# Initialize on first run
RUN python -m archonos init

EXPOSE 8090

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8090"]
```

---

## Part VIII: Success Metrics

### Launch Metrics (First 30 Days)

| Metric | Target |
|--------|--------|
| GitHub Stars | 500 |
| Docker Pulls | 1,000 |
| Discord Members | 100 |
| Pro Subscribers | 20 |

### Growth Metrics (First Year)

| Metric | Target |
|--------|--------|
| GitHub Stars | 5,000 |
| Monthly Active Users | 1,000 |
| MRR (Monthly Recurring Revenue) | $5,000 |

---

## Part IX: Open Questions

1. **Brand name?** ArchonOS, or rebrand to something catchier?
2. **License?** AGPL (copyleft) or proprietary (dual-license)?
3. **Hosting?** Docker Hub or GitHub Container Registry?
4. **Payment?** Stripe, Paddle, or manual invoicing?
5. **Support model?** Discord community + docs, or email support?

---

## Appendix: File Structure

```
archonos-next/
├── src/
│   └── archonos/
│       ├── cli/           # CLI interface
│       ├── core/          # Business logic
│       ├── knowledge/     # KB engine
│       ├── memory/        # Memory system
│       ├── workflows/     # Workflow engine
│       ├── provider/      # LLM providers
│       ├── storage/       # SQLite management
│       └── server/        # Web UI (FastAPI)
├── static/                # CSS, JS, images
├── templates/             # Jinja2 templates
├── tests/                 # Test suite
├── docs/                 # Documentation
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

---

*Document Version: 1.0*
*Last Updated: 2026-06-11*
*Authors: Claude (architect), Alfred (founder)*
