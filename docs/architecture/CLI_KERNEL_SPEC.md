# CLI Kernel Spec

## Commands

### archonos init

Creates local ArchonOS project state:

```text
.archonos/
  config/
  knowledge/
  memory/
  workflows/
  logs/
  archonos.db
```

### archonos status

Displays:

- Version
- Database Status
- Knowledge Count
- Memory Count
- Workflow Count

### archonos healthcheck

Verifies:

- Filesystem
- Database
- Configuration
- Environment
