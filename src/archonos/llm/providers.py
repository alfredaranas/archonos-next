"""LLM provider — model-replaceable interface."""

from __future__ import annotations
import os
from dataclasses import dataclass
from abc import ABC, abstractmethod

PROVIDERS = {}

def register_provider(name: str):
    def decorator(cls):
        PROVIDERS[name] = cls
        return cls
    return decorator

@dataclass
class Message:
    role: str
    content: str

@dataclass
class CompletionResult:
    content: str
    model: str
    usage: dict

class Provider(ABC):
    @abstractmethod
    def complete(self, messages: list[Message], **kwargs) -> CompletionResult:
        pass
    
    @abstractmethod
    def chat(self, prompt: str, system: str = "", **kwargs) -> str:
        messages = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=prompt))
        return self.complete(messages, **kwargs).content

class ProviderRegistry:
    def __init__(self):
        self._providers = {}
    
    def get(self, name: str = None) -> Provider:
        name = name or os.environ.get("LLM_PROVIDER", "minimax")
        if name not in self._providers:
            if name in PROVIDERS:
                self._providers[name] = PROVIDERS[name]()
            else:
                raise ValueError(f"Unknown provider: {name}")
        return self._providers[name]
    
    def complete(self, messages: list[Message], provider: str = None, **kwargs) -> CompletionResult:
        return self.get(provider).complete(messages, **kwargs)
    
    def chat(self, prompt: str, system: str = "", provider: str = None, **kwargs) -> str:
        return self.get(provider).chat(prompt, system, **kwargs)

registry = ProviderRegistry()

@register_provider("minimax")
class MiniMaxProvider(Provider):
    def __init__(self):
        import httpx
        self.base_url = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
        self.api_key = os.environ.get("MINIMAX_API_KEY", "")
        self.model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
    
    def complete(self, messages: list[Message], **kwargs) -> CompletionResult:
        import httpx
        resp = httpx.Client(timeout=120).post(
            f"{self.base_url}/text/chatcompletion_v2",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": kwargs.get("model", self.model),
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "temperature": kwargs.get("temperature", 0.7),
                "max_tokens": kwargs.get("max_tokens", 4096),
            },
        )
        resp.raise_for_status()
        result = resp.json()
        return CompletionResult(
            content=result["choices"][0]["message"]["content"],
            model=result.get("model", self.model),
            usage=result.get("usage", {}),
        )

@register_provider("openai")
class OpenAIProvider(Provider):
    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    
    def complete(self, messages: list[Message], **kwargs) -> CompletionResult:
        import httpx
        resp = httpx.Client(timeout=120).post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": kwargs.get("model", self.model),
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "temperature": kwargs.get("temperature", 0.7),
                "max_tokens": kwargs.get("max_tokens", 4096),
            },
        )
        resp.raise_for_status()
        result = resp.json()
        return CompletionResult(
            content=result["choices"][0]["message"]["content"],
            model=result["model"],
            usage=result.get("usage", {}),
        )

@register_provider("anthropic")
class AnthropicProvider(Provider):
    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    
    def complete(self, messages: list[Message], **kwargs) -> CompletionResult:
        import httpx
        system = ""
        msgs = []
        for m in messages:
            if m.role == "system":
                system = m.content
            else:
                msgs.append({"role": m.role, "content": m.content})
        
        resp = httpx.Client(timeout=120).post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": kwargs.get("model", self.model),
                "max_tokens": kwargs.get("max_tokens", 4096),
                "system": system,
                "messages": msgs,
            },
        )
        resp.raise_for_status()
        result = resp.json()
        return CompletionResult(
            content=result["content"][0]["text"],
            model=result["model"],
            usage=result.get("usage", {}),
        )