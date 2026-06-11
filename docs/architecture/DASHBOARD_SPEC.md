# ArchonOS Dashboard Specification

> Generic, modular dashboard API spec — importable, extensible, local-first.

---

## Philosophy

- **Simple** — stdlib http.server, no heavy frameworks
- **Local-first** — SQLite + local filesystem, no cloud required
- **Modular** — plug in new data sources easily
- **Observable** — everything returns JSON, easy to consume

---

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Clients   │────▶│  HTTP Server │────▶│  Handlers  │
│  (browser, │     │  (stdlib)    │     │  (routes)  │
│   scripts) │     └──────────────┘     └──────┬──────┘
└─────────────┘                               │
                                              ▼
                                     ┌─────────────────┐
                                     │   Data Sources  │
                                     │ • SQLite        │
                                     │ • Filesystem    │
                                     │ • GitHub API    │
                                     │ • Hermes Fleet  │
                                     │ • External APIs │
                                     └─────────────────┘
```

---

## Core API Contract

Every dashboard MUST implement these routes:

### `GET /api/health`

Liveness check.

```json
{ "ok": true }
```

### `GET /api/state`

Full internal state dump. Debugging endpoint.

```json
{
  "generated_at": "2026-06-11T12:00:00Z",
  "version": "1.0.0",
  "data": { ... }
}
```

### `GET /api/mission`

**Boot route.** Returns critical operational state.

```json
{
  "threads": [
    {
      "id": "unique-thread-id",
      "project": "PROJECT_CODE",
      "project_name": "Human readable name",
      "repo": "owner/repo",
      "task": "current task (120 char max)",
      "next_action": "concrete next step",
      "status": "ACTIVE|BLOCKED|DONE",
      "updated_at": "2026-06-11T12:00"
    }
  ],
  "ops": [
    {
      "name": "Operation name",
      "status": "running|done|dead",
      "detail": "last log line or error"
    }
  ]
}
```

---

## Optional Modules

Implement only what you need.

### 📊 Metrics Module

### `GET /api/metrics`

```json
{
  "cpu": 45.2,
  "memory": { "used": 8192, "total": 16384 },
  "disk": { "used": 45, "total": 100 },
  "uptime_seconds": 86400
}
```

### 📅 Schedule Module

### `GET /api/schedule`

```json
{
  "jobs": [
    {
      "id": "job_123",
      "name": "premarket-brief",
      "schedule": "0 6 * * 1-5",
      "last_run": "2026-06-11T06:00:00Z",
      "next_run": "2026-06-12T06:00:00Z",
      "status": "completed|failed|pending"
    }
  ]
}
```

### `POST /api/schedule/<job_id>/run`

Trigger a job immediately.

```json
{ "started": true, "job_id": "job_123" }
```

### 🔧 Infrastructure Module

### `GET /api/nodes`

```json
{
  "nodes": [
    {
      "name": "node-1",
      "status": "online|offline",
      "services": ["hermes", "dashboard"],
      "last_seen": "2026-06-11T12:00:00Z"
    }
  ]
}
```

### 💾 Backup Module

### `POST /api/backup/run`

```json
{ "started": true, "pid": 12345 }
```

### `GET /api/backup/status`

```json
{
  "running": false,
  "last_exit": 0,
  "last_run": "2026-06-11T04:00:00Z",
  "log_tail": "..."
}
```

### 📁 Knowledge Module

### `GET /api/knowledge`

```json
{
  "documents": 142,
  "chunks": 5893,
  "last_indexed": "2026-06-11T12:00:00Z"
}
```

### `GET /api/knowledge/search?q=<query>`

```json
{
  "query": "search term",
  "results": [
    {
      "doc_id": "doc_123",
      "title": "Document Title",
      "snippet": "...matching text...",
      "score": 0.92
    }
  ]
}
```

### 🧠 Memory Module

### `GET /api/memory`

```json
{
  "memories": 89,
  "projects": 5,
  "sessions": 234
}
```

### ⚙️ Settings Module

### `GET /api/settings`

```json
{
  "theme": "dark",
  "language": "en",
  "refresh_interval": 30
}
```

### `PATCH /api/settings`

Update settings.

```json
{ "theme": "light" }
```

---

## HTML Pages (Optional)

| Route | Purpose |
|-------|---------|
| `/` | Main dashboard |
| `/status` | System status |
| `/logs` | Log viewer |
| `/settings` | Settings UI |

---

## Implementation Guide

### Minimal Server (Python stdlib)

```python
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        routes = {
            "/api/health": self.health,
            "/api/mission": self.mission,
            "/api/state": self.state,
        }
        handler = routes.get(self.path)
        if handler:
            handler()
        else:
            self.send_error(404)

    def health(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode())

    def mission(self):
        # Return mission data
        pass

    def state(self):
        # Return full state
        pass

HTTPServer(("", 8090), DashboardHandler).serve_forever()
```

### With SQLite

```python
import sqlite3

def get_db():
    return sqlite3.connect("dashboard.db")
```

### Adding Custom Data Sources

```python
def fetch_custom_data():
    # GitHub, Hermes, external APIs, filesystem, etc.
    return {"custom": "data"}
```

---

## Configuration

```yaml
# dashboard.yaml
server:
  host: "0.0.0.0"
  port: 8092

database:
  path: "data/dashboard.db"

refresh:
  fast_interval: 30   # seconds
  slow_interval: 300   # seconds

modules:
  - health
  - mission
  - schedule
  - backup
  - knowledge
  # add more...
```

---

## Port Convention

| Port | Service |
|------|---------|
| 8090 | Generic dashboard |
| 8091 | Hermes Gateway |
| 8092 | ArchonOS Dashboard |
| 8093 | Metrics |
| 8094 | Development |

---

## Versioning

```
Version: MAJOR.MINOR.PATCH

MAJOR — Breaking changes to API contract
MINOR — New features, backward compatible
PATCH — Bug fixes
```

---

## Extending

To add a new module:

1. Define route in `docs/architecture/DASHBOARD_SPEC.md`
2. Implement handler in `dashboard/server.py`
3. Add tests in `tests/test_dashboard.py`
4. Document in README

---

## References

- Original spec: `archonos/docs/api/DASHBOARD_API.md`
- Implementation: `archonos/dashboard/server.py`
