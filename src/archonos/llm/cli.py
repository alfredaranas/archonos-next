"""LLM CLI commands."""

from __future__ import annotations
import os
from archonos.llm import providers

def chat(prompt: str, system: str = "", provider: str = None, model: str = None, **kwargs) -> str:
    provider = provider or os.environ.get("LLM_PROVIDER", "minimax")
    model = model or os.environ.get("LLM_MODEL")
    p = providers.registry.get(provider)
    if model:
        kwargs["model"] = model
    return p.chat(prompt, system=system, **kwargs)

def complete(messages: list[providers.Message], provider: str = None, **kwargs) -> providers.CompletionResult:
    provider = provider or os.environ.get("LLM_PROVIDER", "minimax")
    return providers.registry.complete(messages, provider=provider, **kwargs)

def providers_list() -> list[str]:
    return list(providers.PROVIDERS.keys())