"""Web server — FastAPI + HTMX."""

from __future__ import annotations
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from archonos.storage import db
from archonos.core import ops
from archonos.knowledge import search as kb_search
from archonos.memory import ops as mem_ops
from archonos.workflows import ops as wf_ops

app = FastAPI(title="ArchonOS")

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

PROJECT = os.environ.get("ARCHONOS_PROJECT", "default")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    status = ops.status(PROJECT)
    return templates.TemplateResponse("dashboard.html", {"request": request, "status": status})

@app.get("/kb", response_class=HTMLResponse)
async def knowledge_base(request: Request, q: str = "", limit: int = 10):
    results = []
    if q.strip():
        conn = db.get_connection(PROJECT)
        try:
            results = kb_search.search(conn, q, k=limit)
        finally:
            conn.close()
    return templates.TemplateResponse("kb.html", {"request": request, "query": q, "results": results})

@app.get("/memory", response_class=HTMLResponse)
async def memory(request: Request, query: str = "", kind: str = "", limit: int = 20):
    conn = db.get_connection(PROJECT)
    try:
        memories = mem_ops.recall(conn, query=query if query else None, kind=kind if kind else None, limit=limit)
    finally:
        conn.close()
    return templates.TemplateResponse("memory.html", {"request": request, "memories": memories, "query": query, "kind": kind})

@app.get("/workflows", response_class=HTMLResponse)
async def workflows(request: Request):
    conn = db.get_connection(PROJECT)
    try:
        workflows = wf_ops.list_workflows(conn)
    finally:
        conn.close()
    return templates.TemplateResponse("workflows.html", {"request": request, "workflows": workflows})

@app.post("/workflows/run/{name}")
async def run_workflow(name: str):
    conn = db.get_connection(PROJECT)
    try:
        run_id = wf_ops.run_workflow(conn, name)
    finally:
        conn.close()
    return {"status": "ok", "run_id": run_id}

@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)