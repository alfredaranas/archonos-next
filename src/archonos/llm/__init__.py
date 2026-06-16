"""LLM integration for ArchonOS (M6+).

Public surface:
    providers.ModelProvider           -- the protocol
    providers.OpenAICompatProvider    -- the v1 implementation
    providers.get_provider            -- factory (settings + env)
    providers.ask                     -- RAG over the knowledge base
    providers.ChatMessage, ChatResponse
    providers.ProviderError, ProviderNotConfigured
"""
from archonos.llm.providers import (
    ChatMessage,
    ChatResponse,
    ModelProvider,
    OpenAICompatProvider,
    ProviderError,
    ProviderNotConfigured,
    ask,
    get_provider,
    resolve_provider_config,
)

__all__ = [
    "ChatMessage",
    "ChatResponse",
    "ModelProvider",
    "OpenAICompatProvider",
    "ProviderError",
    "ProviderNotConfigured",
    "ask",
    "get_provider",
    "resolve_provider_config",
]
