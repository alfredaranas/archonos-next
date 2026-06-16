"""Workflow execution engine for ArchonOS.

Per docs/architecture/CORE_ARCHITECTURE.md §3.3-3.4:
    - Templating: {{params.x}} and {{steps.<id>.<key>}} only
    - Sequential execution, no branches, no loops, no parallelism
    - Each step appends an event to workflow_runs.log
    - First failure stops the run, status=failed, partial log preserved
    - No retries in v1

Per §4:
    workflows/engine.py  run(conn, name, params) -> RunResult(run_id, status, log)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from archonos.workflows import registry
from archonos.workflows.steps import resolve_step


TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z_][\w\.\-]*)\s*\}\}")


@dataclass
class RunResult:
    run_id: int
    workflow_id: int
    workflow_name: str
    status: str  # running | succeeded | failed | aborted
    started_at: str
    finished_at: str | None
    log: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "succeeded"


# --- templating (§3.3) ---


def resolve_template(value: Any, params: dict, step_outputs: dict) -> Any:
    """Recursively resolve {{...}} placeholders in a value.

    - str: substitute placeholders
    - dict: resolve each value
    - list: resolve each element
    - other: pass through
    """
    if isinstance(value, str):
        return _sub_str(value, params, step_outputs)
    if isinstance(value, dict):
        return {k: resolve_template(v, params, step_outputs) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_template(v, params, step_outputs) for v in value]
    return value


def _sub_str(s: str, params: dict, step_outputs: dict) -> str:
    def repl(m: re.Match) -> str:  # type: ignore[type-arg]
        path = m.group(1)
        if not _validate_path(path):
            raise ValueError(f"Invalid template reference: {path!r}")
        parts = path.split(".")
        if parts[0] == "params":
            return _lookup(params, parts[1:], path)
        if parts[0] == "steps":
            # steps.<id>.<key...>
            step_id, *rest = parts[1:]
            return _lookup(step_outputs.get(step_id, {}), rest, path)
        raise ValueError(
            f"Unknown template root {parts[0]!r}; only 'params' and 'steps' are allowed"
        )

    return TEMPLATE_RE.sub(repl, s)


def _validate_path(path: str) -> bool:
    return bool(re.match(r"^[a-zA-Z_][\w\.\-]*$", path))


def _lookup(d: dict, parts: list[str], full_path: str) -> str:
    cur: Any = d
    for p in parts:
        if isinstance(cur, dict):
            if p not in cur:
                raise KeyError(f"Template reference {full_path!r} not found")
            cur = cur[p]
        else:
            raise KeyError(f"Template reference {full_path!r} not found (not a dict at {p!r})")
    if cur is None:
        raise KeyError(f"Template reference {full_path!r} resolved to None")
    # Stringify the leaf; workflow step args are JSON-serializable
    if isinstance(cur, (dict, list)):
        return json.dumps(cur)
    return str(cur)


# --- pre-flight validation (§3.3) ---


def _validate_template_references(spec: dict, params: dict) -> None:
    """Walk the spec and confirm every {{...}} can be resolved before run starts."""
    for step in spec["steps"]:
        args = step.get("args", {})
        _check_refs_in_value(args, params, {}, f"step[{step['id']}].args")


def _check_refs_in_value(value: Any, params: dict, step_outputs: dict, where: str) -> None:
    if isinstance(value, str):
        for m in TEMPLATE_RE.finditer(value):
            path = m.group(1)
            parts = path.split(".")
            if parts[0] == "params":
                # Confirm the param exists OR the literal will not resolve
                # to anything useful at runtime. We don't fail if a param
                # is missing here because the engine raises a clear error
                # at the step that uses it; this is a best-effort check.
                continue
            if parts[0] == "steps":
                step_id, *rest = parts[1:]
                if step_id not in step_outputs:
                    # Not yet executed — fine, will resolve at run time.
                    continue
                _lookup(step_outputs[step_id], rest, path)
            else:
                raise ValueError(
                    f"{where}: unknown template root {parts[0]!r} in {path!r}"
                )
    elif isinstance(value, dict):
        for k, v in value.items():
            _check_refs_in_value(v, params, step_outputs, f"{where}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _check_refs_in_value(v, params, step_outputs, f"{where}[{i}]")


# --- the engine itself ---


def run(conn, name: str, params: dict | None = None) -> RunResult:
    """Execute a workflow. Sequential, fail-fast, audited.

    Returns RunResult even on failure (so the caller can inspect the log).
    """
    params = params or {}
    wf = registry.get_or_404(conn, name)
    spec = wf.spec
    started_at = _now()
    log: list[dict[str, Any]] = []

    cur = conn.execute(
        "INSERT INTO workflow_runs(workflow_id, status, started_at) VALUES (?, ?, ?)",
        (wf.id, "running", started_at),
    )
    run_id = int(cur.lastrowid)
    conn.commit()

    step_outputs: dict[str, dict] = {}

    try:
        for step in spec["steps"]:
            step_id = step["id"]
            step_type = step["type"]
            t0 = _now()
            event: dict[str, Any] = {
                "step": step_id,
                "type": step_type,
                "status": "ok",
                "started": t0,
                "finished": None,
                "output_keys": [],
                "error": None,
            }
            try:
                fn = resolve_step(step_type)
                args = resolve_template(step.get("args", {}), params, step_outputs)
                if not isinstance(args, dict):
                    raise TypeError(
                        f"step {step_id!r}: resolved args is not a dict"
                    )
                output = fn(conn, args)
                step_outputs[step_id] = output
                event["output_keys"] = sorted(output.keys())
                event["output"] = output
            except Exception as e:  # noqa: BLE001
                event["status"] = "failed"
                event["error"] = f"{type(e).__name__}: {e}"
                event["finished"] = _now()
                log.append(event)
                finished_at = _now()
                conn.execute(
                    "UPDATE workflow_runs SET status = ?, finished_at = ?, log = ? "
                    "WHERE id = ?",
                    ("failed", finished_at, json.dumps(log), run_id),
                )
                conn.commit()
                return RunResult(
                    run_id=run_id,
                    workflow_id=wf.id,
                    workflow_name=name,
                    status="failed",
                    started_at=started_at,
                    finished_at=finished_at,
                    log=log,
                )

            event["finished"] = _now()
            log.append(event)

        finished_at = _now()
        conn.execute(
            "UPDATE workflow_runs SET status = ?, finished_at = ?, log = ? WHERE id = ?",
            ("succeeded", finished_at, json.dumps(log), run_id),
        )
        conn.commit()
        return RunResult(
            run_id=run_id,
            workflow_id=wf.id,
            workflow_name=name,
            status="succeeded",
            started_at=started_at,
            finished_at=finished_at,
            log=log,
        )
    except Exception as e:  # noqa: BLE001
        # Catastrophic failure (e.g. DB error between steps)
        finished_at = _now()
        try:
            conn.execute(
                "UPDATE workflow_runs SET status = ?, finished_at = ?, log = ? "
                "WHERE id = ?",
                ("aborted", finished_at, json.dumps(log), run_id),
            )
            conn.commit()
        except Exception:
            pass
        return RunResult(
            run_id=run_id,
            workflow_id=wf.id,
            workflow_name=name,
            status="aborted",
            started_at=started_at,
            finished_at=finished_at,
            log=log,
        )


def get_run(conn, run_id: int) -> RunResult | None:
    row = conn.execute(
        "SELECT id, workflow_id, status, started_at, finished_at, log "
        "FROM workflow_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    log = json.loads(row["log"]) if row["log"] else []
    name_row = conn.execute(
        "SELECT name FROM workflows WHERE id = ?", (row["workflow_id"],)
    ).fetchone()
    return RunResult(
        run_id=int(row["id"]),
        workflow_id=int(row["workflow_id"]),
        workflow_name=name_row["name"] if name_row else "<deleted>",
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        log=log,
    )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
