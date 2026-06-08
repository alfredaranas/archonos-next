# ArchonOS Next

ArchonOS Next is a local-first AI operating layer for knowledge, memory, workflows, automation, and continuity.

Architecture is frozen for Local Alpha. Current implementation scope is limited to Repository Foundation and CLI Kernel.

## Local Alpha Scope

Included now:

- CLI Kernel
- SQLite local storage foundation
- Local project directory initialization
- Health and status checks

Not included until after Local Alpha:

- MCP
- Desktop UI
- Graph Database
- Agent Framework
- Distributed Execution
- Multi-device Sync

## Commands

```bash
archonos init
archonos status
archonos healthcheck
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
archonos init
archonos status
archonos healthcheck
python -m pytest
```
