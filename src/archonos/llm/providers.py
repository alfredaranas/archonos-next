"""LLM provider layer for ArchonOS (M6).

Per docs/architecture/CORE_ARCHITECTURE.md §6:
    ModelProvider Protocol:
        complete(messages, tools=None) -> ChatResponse
    OpenAICompatProvider(base_url, api_key, model)
        Covers MiniMax M3 (via OpenRouter), OpenAI, any local vLLM endpoint.

Per §6: no key configured -> archonos ask exits 1 with a clear message;
nothing else degrades. The kernel stays at stdlib-only (urllib for M6,
no httpx dependency).

Provider selection (in priority order):
    1. settings table: provider, model, api_key, base_url
    2. env vars: ARCHONOS_LLM_PROVIDER, ARCHONOS_LLM_MODEL,
       ARCHONOS_LLM_API_KEY, ARCHONOS_LLM_BASE_URL
    3. None -> degraded mode (ask returns a clear error)

The `step_ask` workflow step type calls into this module.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from archonos.storage import db as _storage_db


# --- public types ---


@dataclass
class ChatMessage:
    role: str  # 'system' | 'user' | 'assistant' | 'tool'
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResponse:
    text: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"


# --- errors ---


class ProviderError(Exception):
    """Raised when an LLM provider call fails (network, auth, bad response)."""


class ProviderNotConfigured(Exception):
    """Raised when ask is called with no provider / key configured."""


# --- protocol ---


@runtime_checkable
class ModelProvider(Protocol):
    """The contract every LLM provider implements.

    A provider has:
        name:  human-readable name (for `archonos llm-providers`)
        model: the model identifier this provider is currently configured for

    And one method:
        complete(messages, tools=None) -> ChatResponse
    """
    name: str
    model: str

    def complete(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse: ...


# --- settings helpers ---


def _read_settings_value(conn, key: str) -> str | None:
    """Read a value from the settings table. Returns None if absent."""
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    except Exception:
        return None
    return row["value"] if row else None


def resolve_provider_config(
    conn=None,
) -> dict[str, str | None] | None:
    """Resolve the active LLM provider config.

    Lookup order (first hit wins per field):
        1. settings table (project-level override)
        2. environment variables (system-level)

    Returns None if no provider is configured (degraded mode).
    Otherwise returns {provider, model, api_key, base_url}.
    """
    # Pull all from settings
    s_provider = _read_settings_value(conn, "llm_provider")
    s_model = _read_settings_value(conn, "llm_model")
    s_key = _read_settings_value(conn, "llm_api_key")
    s_base = _read_settings_value(conn, "llm_base_url")

    # Then env (overrides settings — env is highest priority so CLI/secret-store
    # tooling like 1Password, direnv, etc. can win over project config)
    provider = os.environ.get("ARCHONOS_LLM_PROVIDER") or s_provider or "minimax"
    model = os.environ.get("ARCHONOS_LLM_MODEL") or s_model or "MiniMax-M3"
    api_key = os.environ.get("ARCHONOS_LLM_API_KEY") or s_key
    base_url = (
        os.environ.get("ARCHONOS_LLM_BASE_URL")
        or s_base
        # Default: MiniMax M3 via OpenRouter. OpenAI and vLLM work by overriding.
        or "https://openrouter.ai/api/v1"
    )

    if not api_key:
        return None
    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
    }


# --- the one implementation: OpenAI-compatible HTTP ---


class OpenAICompatProvider:
    """OpenAI /v1/chat/completions-compatible HTTP provider.

    Works for: MiniMax M3 (via OpenRouter), OpenAI, vLLM, llama.cpp
    server, LM Studio, any local OpenAI-compatible endpoint.
    """
    name = "openai-compat"
    model: str

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        url = f"{self.base_url}/chat/completions"
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [_msg_to_dict(m) for m in messages],
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "archonos-next/0.1",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise ProviderError(
                f"provider {self.name} ({self.model}) HTTP {e.code}: {detail[:200]}"
            ) from e
        except urllib.error.URLError as e:
            raise ProviderError(f"network error calling {self.name}: {e}") from e

        return _parse_response(payload)


def _msg_to_dict(m: ChatMessage) -> dict[str, Any]:
    d: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.name:
        d["name"] = m.name
    if m.tool_call_id:
        d["tool_call_id"] = m.tool_call_id
    return d


def _parse_response(payload: dict[str, Any]) -> ChatResponse:
    """Parse an OpenAI /v1/chat/completions response."""
    choices = payload.get("choices") or []
    if not choices:
        raise ProviderError(f"no choices in response: {payload}")
    first = choices[0]
    msg = first.get("message") or {}
    text = msg.get("content") or ""
    finish = first.get("finish_reason") or "stop"

    tool_calls: list[ToolCall] = []
    for tc in msg.get("tool_calls") or []:
        try:
            args = json.loads(tc.get("function", {}).get("arguments", "{}"))
        except json.JSONDecodeError:
            args = {}
        tool_calls.append(
            ToolCall(
                id=tc.get("id", ""),
                name=tc.get("function", {}).get("name", ""),
                arguments=args,
            )
        )

    return ChatResponse(
        text=text,
        usage=payload.get("usage") or {},
        raw=payload,
        tool_calls=tool_calls,
        finish_reason=finish,
    )


# --- factory ---


def get_provider(conn=None) -> ModelProvider:
    """Resolve the active provider. Raises ProviderNotConfigured if absent."""
    cfg = resolve_provider_config(conn)
    if cfg is None:
        raise ProviderNotConfigured(
            "no LLM provider configured. Set one of:\n"
            "  - settings keys: llm_provider, llm_model, llm_api_key, llm_base_url\n"
            "  - env vars: ARCHONOS_LLM_PROVIDER, ARCHONOS_LLM_MODEL,\n"
            "              ARCHONOS_LLM_API_KEY, ARCHONOS_LLM_BASE_URL\n"
            "Example for MiniMax M3 via OpenRouter:\n"
            "  archonos config set llm_provider minimax\n"
            "  archonos config set llm_model MiniMax-M3\n"
            "  archonos config set llm_base_url https://openrouter.ai/api/v1\n"
            "  archonos config set llm_api_key <your-openrouter-key>\n"
        )
    # cfg is not None at this point; narrow types for the type checker
    base_url: str = cfg["base_url"] or "https://openrouter.ai/api/v1"
    api_key: str = cfg["api_key"] or ""
    model: str = cfg["model"] or "MiniMax-M3"
    return OpenAICompatProvider(
        base_url=base_url,
        api_key=api_key,
        model=model,
    )


# --- ask: retrieval + synthesis ---


def ask(
    conn,
    question: str,
    *,
    k: int = 5,
    provider: ModelProvider | None = None,
    system: str | None = None,
) -> ChatResponse:
    """Answer a question grounded in the knowledge base.

    1. FTS5 search the knowledge base (k=top k chunks)
    2. Build a context with the top hits
    3. Call the LLM with system + context + user question
    4. Return the model's answer
    """
    from archonos.knowledge import search as kb_search

    if provider is None:
        provider = get_provider(conn)

    hits = kb_search.search(conn, question, k=k) if question.strip() else []
    context = _format_context(hits) if hits else "(no relevant documents found in the knowledge base)"

    sys_prompt = system or (
        "You are ArchonOS, a local-first AI operating system. "
        "Answer the user's question based ONLY on the provided context. "
        "If the context does not contain the answer, say so explicitly. "
        "Cite the document title for each fact you use."
    )
    user_prompt = (
        f"Context (from the ArchonOS knowledge base):\n\n{context}\n\n"
        f"Question: {question}\n\n"
        f"Answer (with citations to the context above):"
    )
    return provider.complete([
        ChatMessage(role="system", content=sys_prompt),
        ChatMessage(role="user", content=user_prompt),
    ])


def _format_context(hits) -> str:  # type: ignore[no-untyped-def]
    parts = []
    for i, h in enumerate(hits, start=1):
        parts.append(f"[{i}] {h.doc_title}  (chunk {h.chunk_id}, rank {h.rank:.2f})\n{h.snippet}\n")
    return "\n".join(parts)
