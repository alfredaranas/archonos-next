"""Retrieval-augmented answering — the moment archonos can think.

Workflow:
  1. Take a question
  2. Search the knowledge base (M2) for relevant chunks
  3. Build a context-grounded prompt
  4. Call the configured LLM provider (M6)
  5. Return the answer + the chunks it was grounded in

No provider key → graceful error. Knowledge/memory/workflows still work.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass

from archonos.knowledge import search as kb_search
from archonos.llm import providers as llm_providers


SYSTEM_PROMPT = """You are an assistant answering questions using ONLY the provided context.
Rules:
- If the context contains the answer, give it directly and cite the document titles in [brackets].
- If the context does not contain the answer, say "I don't have that in the knowledge base."
- Do not invent facts. Do not use general knowledge outside the context."""


@dataclass
class AskResult:
    answer: str
    chunks_used: int
    provider: str
    model: str


def _format_context(hits: list[kb_search.SearchHit]) -> str:
    """Turn search hits into a numbered context block for the LLM."""
    if not hits:
        return "(no relevant context found)"
    parts = []
    for i, h in enumerate(hits, 1):
        parts.append(f"[{i}] {h.title}\n{h.snippet}")
    return "\n\n".join(parts)


def ask(
    conn: sqlite3.Connection,
    question: str,
    k: int = 5,
    provider: str | None = None,
    model: str | None = None,
) -> AskResult:
    """Answer a question using retrieved context + LLM.

    Raises RuntimeError with a clean message if no provider key is configured.
    """
    if not question.strip():
        raise ValueError("question is empty")

    # 1. Retrieve
    hits = kb_search.search(conn, question, k=k)

    # 2. Build grounded prompt
    context = _format_context(hits)
    user_msg = f"Context:\n{context}\n\nQuestion: {question}"

    # 3. Call provider
    provider_name = provider or os.environ.get("LLM_PROVIDER", "minimax")
    try:
        p = llm_providers.registry.get(provider_name)
    except ValueError as e:
        raise RuntimeError(f"unknown provider '{provider_name}'") from e

    # Surface a friendly message when no API key is set
    api_key_env = {
        "minimax": "MINIMAX_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }.get(provider_name)
    if api_key_env and not os.environ.get(api_key_env):
        raise RuntimeError(
            f"no API key for provider '{provider_name}' — set {api_key_env} "
            f"to enable 'archonos ask'. All other commands work without it."
        )

    kwargs = {}
    if model:
        kwargs["model"] = model
    msgs = [
        llm_providers.Message(role="system", content=SYSTEM_PROMPT),
        llm_providers.Message(role="user", content=user_msg),
    ]
    result = p.complete(msgs, **kwargs)

    return AskResult(
        answer=result.content,
        chunks_used=len(hits),
        provider=provider_name,
        model=result.model,
    )
