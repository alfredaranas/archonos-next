ARCHONOS NEXT — CODEX EXECUTION BACKBONE HANDOFF v1.0

Purpose

This document serves as the canonical handoff from Claude to Codex for the development of ArchonOS Next.

Claude is responsible for:

* Architecture
* Documentation
* Planning
* Workflow Design
* Knowledge Extraction
* Continuity Preservation
* Decision Recording

Codex is responsible for:

* Implementation
* Testing
* Refactoring
* Code Generation
* Code Review Support
* Repository Maintenance

This document must provide enough context that Codex can continue development without requiring access to prior chats.

⸻

Project Identity

Project Name:

ArchonOS Next

Repository:

alfredaranas/archonos-next

Status:

Engineering Phase

Current State:

Architecture Frozen

Current Development Scope:

Milestone 0.5 Repository Foundation
Milestone 1 CLI Kernel

⸻

Core Directive

Preserve continuity.

Transform information into structured knowledge.

Transform knowledge into workflows.

Transform workflows into execution.

Reduce friction between intention and action.

⸻

Product Definition

ArchonOS Next is a local-first AI operating system focused on:

* Knowledge
* Memory
* Workflows
* Automation
* Continuity

The system must survive:

* Model changes
* Provider changes
* Runtime changes
* Hardware changes
* Infrastructure changes

The model is replaceable.

The provider is replaceable.

The runtime is replaceable.

The knowledge is durable.

The memory is durable.

The workflows are durable.

⸻

Product Principles

Required

* Local First
* Knowledge First
* Workflow First
* Memory First
* Runtime Agnostic
* Provider Agnostic
* Inference Agnostic
* Explicit Documentation
* Observable Systems
* Replaceable Components

Avoid

* Hidden Dependencies
* Vendor Lock-In
* Architecture Drift
* Magic Behavior
* Implicit State
* Cloud Dependency

⸻

Local Alpha Scope

Current implementation target:

Milestone 0.5

Repository Foundation

Includes:

* Python project structure
* Documentation structure
* Test structure
* Initial package layout

⸻

Milestone 1

CLI Kernel

Required Commands:

archonos init
archonos status
archonos healthcheck

⸻

Milestone 2

Local Knowledge Base

Includes:

* SQLite document storage
* Chunk storage
* Search foundation
* Import pipeline

⸻

Milestone 3

Workflow Engine

Includes:

* Workflow registry
* Workflow execution
* Workflow audit logs

⸻

Milestone 4

Persistent Memory

Includes:

* Local memory storage
* Project memory
* Workflow memory
* Recall capabilities

⸻

Milestone 5

Local Alpha

A user must be able to:

1. Install ArchonOS
2. Initialize a project
3. Import documents
4. Search knowledge
5. Execute workflows
6. Persist memory

Using:

Windows 11
WSL2
SQLite

No external infrastructure required.

⸻

Explicitly Out of Scope

DO NOT IMPLEMENT:

* MCP Runtime
* Desktop UI
* Graph Database
* Agent Framework
* Multi-Agent Systems
* Distributed Execution
* Kubernetes
* Multi-Device Sync
* Cloud Dependency
* Required Supabase Dependency
* Vector Database Dependency
* Hosted Infrastructure Dependency

If implementation requires any of the above:

STOP.

Document.

Do not proceed.

⸻

Storage Strategy

Primary Storage:

SQLite

Optional Future Storage:

Supabase

Rule:

ArchonOS Next must function completely without Supabase.

SQLite is the canonical local store.

⸻

Repository Structure

Target structure:

archonos-next/
src/
└── archonos/
    ├── cli/
    ├── core/
    ├── config/
    ├── storage/
    ├── knowledge/
    ├── memory/
    └── workflows/
tests/
docs/
├── founding/
├── architecture/
├── onboarding/
└── product/
README.md
pyproject.toml

⸻

Database Foundation

Current tables:

documents
chunks
memories
workflows
workflow_runs
settings

Future schema changes require documentation.

Do not redesign schema without approval.

⸻

Architecture Rules

Simplicity First

Always choose:

* Simpler solution
* Fewer dependencies
* Less infrastructure
* Explicit behavior

⸻

Observability

Every major component should eventually expose:

* Health
* Status
* Logs
* Audit Trail

⸻

Replaceability

Every major subsystem should eventually be replaceable.

Examples:

SQLite → Supabase
OpenAI → Anthropic
Claude → ChatGPT
Local Runtime → Future Runtime

without redesigning ArchonOS Core.

⸻

Legacy ArchonOS Relationship

Legacy ArchonOS is:

Reference Only

Legacy ArchonOS is:

Capability Pool

Legacy ArchonOS is NOT:

Active Development

⸻

Infrastructure Absorption Strategy

ArchonOS Next does not ignore Legacy.

ArchonOS Next does not copy Legacy.

Instead:

Absorb capability.
Normalize interface.
Avoid inherited dependency.

⸻

Current Legacy Infrastructure Pool

Potential future integrations:

* Continuum
* SupaBrain
* Hermes
* Yoda
* Oracle
* Sentinel
* Parallax
* Trading Brain
* Existing MCP Servers
* Existing Knowledge Bases

These are future adapter targets.

They are NOT Local Alpha dependencies.

⸻

Infrastructure Absorption Model

Future architecture:

Legacy Infrastructure
        ↓
Adapter Layer
        ↓
Provider Contracts
        ↓
ArchonOS Core
        ↓
SQLite
Knowledge
Memory
Workflows

⸻

Future Provider Contracts

Future absorbed infrastructure should eventually map into:

ProjectProvider
KnowledgeProvider
MemoryProvider
WorkflowProvider
ExecutionProvider
ApprovalProvider
AuditProvider

Do not implement during Local Alpha.

Document only.

⸻

MCP Strategy

MCP is:

Transport Layer

MCP is NOT:

The Product

The product is:

* Knowledge
* Memory
* Workflows
* Continuity

⸻

Future MCP Architecture

Future only:

Client
    ↓
MCP
    ↓
ArchonOS Core
    ↓
Knowledge
Memory
Workflows

Never:

Client
    ↓
MCP
    ↓
Business Logic

Business logic belongs in ArchonOS Core.

⸻

MCP Status

Current Status:

Deferred

No MCP implementation before Local Alpha.

⸻

Knowledge Strategy

Transform information into:

* Concepts
* Patterns
* Frameworks
* Heuristics
* Checklists
* Workflows
* Knowledge Packs

Do not create document dumps.

Create reusable knowledge.

⸻

Memory Strategy

Memory should preserve:

* Decisions
* Project State
* Context
* Lessons Learned
* Workflow Outcomes

Memory is durable.

Sessions are not.

⸻

Workflow Strategy

Every recurring task should eventually become:

Documented
Repeatable
Observable
Auditable

⸻

Coding Rules

Prefer:

* Small files
* Type hints
* Explicit code
* Deterministic behavior
* Readability
* Testability

Avoid:

* Hidden globals
* Complex frameworks
* Clever abstractions
* Premature optimization
* Runtime magic

⸻

Dependency Rules

Every dependency must justify itself.

Before adding a dependency ask:

Can the standard library do this?
Can SQLite do this?
Can existing code do this?

If yes:

Do not add dependency.

⸻

Git Rules

Commits should be:

* Small
* Focused
* Atomic

One concern per commit.

Avoid:

* Drive-by refactors
* Unrelated changes
* Scope expansion

⸻

Testing Rules

Before any commit:

Run:

python -m venv .venv
source .venv/bin/activate
pip install -e .
pytest
archonos init
archonos status
archonos healthcheck

Failures must be fixed or documented.

⸻

Documentation Rules

All architecture decisions must be documented.

Major changes require:

Decision
Reason
Tradeoffs
Dependencies
Future Impact

Documentation is a first-class deliverable.

⸻

Codex Operating Instructions

Codex is an implementation worker.

Codex is NOT the architect.

Codex may:

* Create code
* Modify code
* Add tests
* Fix bugs
* Improve documentation

Codex may NOT:

* Expand architecture
* Introduce MCP
* Introduce cloud services
* Introduce agents
* Introduce distributed systems
* Introduce graph databases
* Introduce desktop UI

without explicit approval.

⸻

Decision Hierarchy

When choosing between alternatives:

1. Preserve continuity
2. Preserve user ownership
3. Preserve simplicity
4. Preserve portability
5. Preserve observability
6. Optimize performance
7. Optimize convenience

⸻

Success Criteria

ArchonOS Next Local Alpha succeeds when:

A user on:

Windows 11
WSL2
16GB+ RAM

can:

Install ArchonOS
Initialize a project
Store documents
Search knowledge
Run workflows
Persist memory

using only:

Python
SQLite
Local filesystem

No cloud required.

No homelab required.

No external services required.

⸻

Future Vision

Future capabilities may include:

* MCP
* Desktop UI
* Knowledge Packs
* Optional Supabase
* Optional Remote Infrastructure
* Optional Agent Systems

These are future layers.

They must sit on top of a stable Local Alpha foundation.

⸻

Final Rules

When uncertain:

Choose the simpler solution.

When uncertain:

Protect continuity.

When uncertain:

Preserve local-first operation.

When uncertain:

Avoid scope expansion.

When uncertain:

Do not build infrastructure that has not yet earned its existence.

⸻

Immediate Task For Codex

1. Verify repository structure.
2. Verify CLI kernel.
3. Verify SQLite foundation.
4. Verify tests.
5. Restore any missing documentation.
6. Review architecture docs.
7. Ensure Local Alpha scope is enforced.
8. Open PR for review.
9. Do not expand scope.

Architecture is frozen.

Local Alpha comes first.
