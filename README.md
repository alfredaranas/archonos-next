# ArchonOS Next

Local-first AI operating system — KB-as-OS with approval gates, memory, and workflows.

## Quick Start

```bash
# Clone and install
git clone https://github.com/alfredaranas/archonos-next.git
cd archonos-next
pip install -e .

# Initialize
archonos init

# Import knowledge
archonos import ./docs

# Search
archonos search "your query"

# Remember
archonos remember "important decision" --kind decision

# Chat with LLM
archonos chat "hello" --provider minimax
```

## Commands

| Command | Description |
|---------|------------|
| `init` | Initialize project |
| `status` | Show project state |
| `healthcheck` | Run health checks |
| `import <path>` | Import files into KB |
| `search <query>` | Search knowledge |
| `remember "text"` | Store memory |
| `recall` | Recall memories |
| `workflow-register` | Register workflow |
| `workflow-list` | List workflows |
| `workflow-run` | Run workflow |
| `chat` | Chat with LLM |
| `llm-providers` | List providers |

## Configuration

Set environment variables:

```bash
export MINIMAX_API_KEY="your-key"
export MINIMAX_MODEL="MiniMax-M2.5"
export LLM_PROVIDER="minimax"
```

## Docker

```bash
docker build -t archonos .
docker run -p 8090:8090 -v ~/.archonos:/home/archonos/.archonos archonos
```

## Project Structure

```
archonos-next/
├── src/archonos/
│   ├── cli/          # CLI commands
│   ├── core/        # init, status, healthcheck
│   ├── knowledge/   # import, search
│   ├── memory/      # remember, recall
│   ├── workflows/   # workflow ops
│   ├── llm/        # LLM providers
│   ├── server/      # Web UI
│   └── storage/     # SQLite + migrations
└── Dockerfile
```

## Features

- **Knowledge Base**: FTS5 full-text search
- **Memory**: Decision/state/lesson tracking
- **Workflows**: Programmable automation
- **LLM**: Model-replaceable (MiniMax, OpenAI, Anthropic)
- **Web UI**: FastAPI + HTMX dashboard
- **Docker**: Single-container deployment

## License

MIT