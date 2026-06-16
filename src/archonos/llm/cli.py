"""CLI helpers for the LLM provider layer.

The archonos CLI (cli/main.py) imports _cmd_ask / _cmd_llm_providers from
here, keeping this layer's CLI surface separated from the kernel CLI.

Per CORE_ARCHITECTURE.md §1: CLI formats; core returns data.
"""

from __future__ import annotations

import argparse
import sys

from archonos.llm import (
    ProviderError,
    ProviderNotConfigured,
    ask,
    get_provider,
    resolve_provider_config,
)
from archonos.storage import db


def _cmd_ask(args: argparse.Namespace) -> int:
    """archonos ask "..." — retrieval + synthesis."""
    try:
        conn = db.get_connection(args.project)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    try:
        try:
            response = ask(conn, args.question, k=args.limit)
        except ProviderNotConfigured as e:
            print(str(e), file=sys.stderr)
            return 1
        except ProviderError as e:
            print(f"provider error: {e}", file=sys.stderr)
            return 2
    finally:
        conn.close()
    print(response.text)
    if response.usage:
        usage = response.usage
        # OpenAI-shaped: prompt_tokens, completion_tokens, total_tokens
        pt = usage.get("prompt_tokens", "?")
        ct = usage.get("completion_tokens", "?")
        tot = usage.get("total_tokens", "?")
        print(f"\n[usage: {pt}+{ct}={tot} tokens]", file=sys.stderr)
    return 0


def _cmd_llm_providers(args: argparse.Namespace) -> int:
    """archonos llm-providers — show the active provider (or list available)."""
    try:
        cfg = resolve_provider_config()
    except Exception as e:
        print(f"error reading config: {e}", file=sys.stderr)
        return 2

    if cfg is None:
        print("No LLM provider configured.")
        print()
        print("To enable the AI layer, set the following:")
        print("  - settings:  llm_provider, llm_model, llm_api_key, llm_base_url")
        print("  - env vars:   ARCHONOS_LLM_PROVIDER, ARCHONOS_LLM_MODEL,")
        print("                ARCHONOS_LLM_API_KEY, ARCHONOS_LLM_BASE_URL")
        print()
        print("The kernel still works without a provider — knowledge, memory,")
        print("workflows, and search are unaffected. Only `archonos ask` and")
        print("the `ask` workflow step type require a provider.")
        return 1

    print("Active LLM provider:")
    print(f"  provider: {cfg['provider']}")
    print(f"  model:    {cfg['model']}")
    print(f"  base_url: {cfg['base_url']}")
    key = cfg.get("api_key") or ""
    print(f"  api_key:  {'*' * max(0, len(key) - 4)}{key[-4:] if key else '(empty)'}")
    print()
    print("Implementation: OpenAICompatProvider (covers MiniMax M3 via")
    print("OpenRouter, OpenAI, vLLM, llama.cpp, LM Studio, etc.)")
    return 0


def _cmd_llm_config(args: argparse.Namespace) -> int:
    """archonos config set|get|unset KEY [VALUE] — get/set a settings row."""
    try:
        conn = db.get_connection(args.project)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    try:
        if args.action == "get":
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (args.key,)
            ).fetchone()
            if row is None:
                print(f"(not set: {args.key})", file=sys.stderr)
                return 1
            print(row["value"])
            return 0
        elif args.action == "set":
            if args.value is None:
                print("config set requires a value", file=sys.stderr)
                return 1
            conn.execute(
                "INSERT INTO settings(key, value, updated_at) VALUES (?, ?, datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
                (args.key, args.value),
            )
            conn.commit()
            print(f"set {args.key}")
            return 0
        elif args.action == "unset":
            conn.execute("DELETE FROM settings WHERE key = ?", (args.key,))
            conn.commit()
            print(f"unset {args.key}")
            return 0
        elif args.action == "list":
            rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
            for r in rows:
                v = r["value"]
                if any(s in r["key"].lower() for s in ("key", "secret", "token", "password")):
                    v = "*" * max(0, len(v) - 4) + v[-4:] if len(v) > 4 else "****"
                print(f"{r['key']:30s} = {v}")
            return 0
    finally:
        conn.close()
    return 0
