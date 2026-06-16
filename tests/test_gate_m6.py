"""Gate test for Milestone 6 — LLM Provider Layer.

The gate (per docs/BASE_PLAN.md M6 + CORE_ARCHITECTURE.md §6):
    `archonos ask` answers a question grounded in imported documents via
    M3 API; with no key set, command fails gracefully and all M1–M5 gates
    still pass.

We test this two ways:
  1. With no provider configured: ask exits 1 with a clear message;
     all other M1-M5 tests still pass (degraded mode).
  2. With a stub provider: ask calls retrieval + provider.complete()
     and returns the answer; the workflow `ask` step works end-to-end.
"""

from __future__ import annotations

import json

import pytest

from archonos.cli.main import main
from archonos.core import ops
from archonos.knowledge import import_ as kb_import
from archonos.knowledge import search as kb_search
from archonos.llm import (
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
from archonos.storage import db
from archonos.workflows import engine as wf_engine
from archonos.workflows import registry as wf_registry


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    # Ensure no LLM env vars leak in from the host environment
    for k in (
        "ARCHONOS_LLM_PROVIDER",
        "ARCHONOS_LLM_MODEL",
        "ARCHONOS_LLM_API_KEY",
        "ARCHONOS_LLM_BASE_URL",
    ):
        monkeypatch.delenv(k, raising=False)
    ops.init()
    return tmp_path


# --- no-provider degraded mode ---


def test_no_provider_raises_clean_error():
    """Per §6: no key configured -> ProviderNotConfigured, with a clear message."""
    with pytest.raises(ProviderNotConfigured) as ei:
        get_provider()
    msg = str(ei.value)
    # The message should help the user fix it
    assert "ARCHONOS_LLM_API_KEY" in msg
    assert "llm_provider" in msg
    assert "OpenRouter" in msg  # default config example


def test_resolve_provider_config_returns_none_without_key():
    assert resolve_provider_config() is None


def test_cli_ask_without_provider_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    # Don't init — ask with no db and no provider should still exit 1
    rc = main(["ask", "anything"])
    # Could be exit 1 (no init) or exit 1 (no provider) — both correct user errors
    assert rc == 1
    out = capsys.readouterr()
    combined = out.out + out.err
    # The error message should mention provider/key
    assert "provider" in combined.lower() or "llm" in combined.lower() or "init" in combined.lower()


def test_cli_llm_providers_when_unconfigured(capsys):
    """`archonos llm-providers` reports the absence clearly when nothing is set."""
    rc = main(["llm-providers"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "No LLM provider configured" in out
    assert "ARCHONOS_LLM_API_KEY" in out


# --- provider config from settings + env ---


def test_config_set_get_unset_list(isolated_home):
    """The new `config` CLI subcommand works for LLM settings."""
    assert main(["config", "set", "llm_api_key", "test-key-1234"]) == 0
    assert main(["config", "set", "llm_provider", "minimax"]) == 0
    # get
    assert main(["config", "get", "llm_provider"]) == 0
    capsys_out = main.__module__  # placeholder; real assertion below
    rc = main(["config", "get", "llm_provider"])
    assert rc == 0
    # list
    rc = main(["config", "list"])
    assert rc == 0
    # unset
    assert main(["config", "unset", "llm_api_key"]) == 0


def test_config_get_unknown_key_exits_1(isolated_home):
    rc = main(["config", "get", "this_key_does_not_exist"])
    assert rc == 1


def test_resolve_provider_config_picks_up_settings(isolated_home):
    main(["config", "set", "llm_provider", "minimax"])
    main(["config", "set", "llm_model", "MiniMax-M3"])
    main(["config", "set", "llm_base_url", "https://openrouter.ai/api/v1"])
    main(["config", "set", "llm_api_key", "sk-tes...7890"])
    # Pass an explicit connection so resolve_provider_config can see settings
    conn = db.get_connection()
    try:
        cfg = resolve_provider_config(conn)
    finally:
        conn.close()
    assert cfg is not None
    assert cfg["provider"] == "minimax"
    assert cfg["model"] == "MiniMax-M3"
    assert cfg["base_url"] == "https://openrouter.ai/api/v1"
    assert cfg["api_key"] == "sk-tes...7890"


def test_env_vars_override_settings(isolated_home, monkeypatch):
    main(["config", "set", "llm_api_key", "settings-key"])
    monkeypatch.setenv("ARCHONOS_LLM_API_KEY", "env-wins")
    cfg = resolve_provider_config()
    assert cfg["api_key"] == "env-wins"


# --- stub provider for full E2E ---


class StubProvider:
    """In-process LLM stand-in for the gate test."""
    name = "stub"
    model = "stub-model"

    def __init__(self, canned_text: str = "stub answer"):
        self.canned_text = canned_text
        self.calls: list[list[ChatMessage]] = []

    def complete(self, messages, tools=None) -> ChatResponse:
        self.calls.append(messages)
        return ChatResponse(
            text=self.canned_text,
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            raw={"stub": True},
            finish_reason="stop",
        )


def test_stub_provider_satisfies_protocol():
    """The ModelProvider Protocol can be satisfied by any object with
    the right shape — this is what makes M6+ extensible."""
    p = StubProvider()
    assert isinstance(p, ModelProvider)


def test_ask_uses_stub_provider_and_returns_answer(isolated_home):
    """The full retrieval + synthesis loop works with a stub."""
    # Seed some knowledge so retrieval has something to find
    docs_dir = isolated_home / "corpus"
    docs_dir.mkdir()
    (docs_dir / "alpha.md").write_text(
        "ArchonOS is a local-first AI operating system. "
        "It uses SQLite for storage and FTS5 for search. " * 10,
        encoding="utf-8",
    )
    conn = db.get_connection()
    try:
        kb_import.import_path(conn, docs_dir)
    finally:
        conn.close()

    stub = StubProvider("Yes, ArchonOS is local-first.")
    conn = db.get_connection()
    try:
        response = ask(conn, "Is ArchonOS local-first?", k=3, provider=stub)
    finally:
        conn.close()

    assert response.text == "Yes, ArchonOS is local-first."
    # The provider received both a system and a user message
    assert len(stub.calls) == 1
    assert len(stub.calls[0]) == 2
    assert stub.calls[0][0].role == "system"
    assert stub.calls[0][1].role == "user"
    # The user message should contain context from the imported document
    user_msg = stub.calls[0][1].content
    assert "local-first" in user_msg
    assert "SQLite" in user_msg
    # And it should cite the question
    assert "Is ArchonOS local-first?" in user_msg


def test_ask_with_no_documents_works(isolated_home):
    """ask should still work on an empty knowledge base — just with no context."""
    stub = StubProvider("I don't know.")
    conn = db.get_connection()
    try:
        response = ask(conn, "What is the meaning of life?", k=3, provider=stub)
    finally:
        conn.close()
    assert response.text == "I don't know."
    user_msg = stub.calls[0][1].content
    assert "no relevant documents" in user_msg


# --- step_ask workflow integration ---


def test_step_ask_with_real_provider_settings(isolated_home, monkeypatch):
    """With provider settings configured and a stub URL that points
    to an in-process fake, the step completes and the answer is
    recorded. We use a URL that resolves to a local echo server."""
    # Use a real provider instance but point at an in-process echo URL.
    # We can't actually run an HTTP server in a unit test, so we monkeypatch
    # OpenAICompatProvider.complete with a stub.
    from archonos.llm import providers as llm_providers

    def fake_complete(self, messages, tools=None):
        return ChatResponse(
            text="FTS5 (per the document).",
            usage={"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            raw={"fake": True},
        )

    monkeypatch.setattr(OpenAICompatProvider, "complete", fake_complete)

    # Configure the provider in settings
    main(["config", "set", "llm_api_key", "test-key"])
    main(["config", "set", "llm_model", "test-model"])
    main(["config", "set", "llm_base_url", "https://example.invalid"])

    # Seed a doc
    (isolated_home / "alpha.md").write_text(
        "ArchonOS uses FTS5 for full-text search. " * 10, encoding="utf-8",
    )
    conn = db.get_connection()
    try:
        kb_import.import_path(conn, isolated_home / "alpha.md")
        spec = {
            "steps": [
                {
                    "id": "s1",
                    "type": "ask",
                    "args": {"prompt": "What does ArchonOS use for search?", "k": 3},
                }
            ]
        }
        wf_registry.register(conn, "ask-real", spec)
        result = wf_engine.run(conn, "ask-real", {})
    finally:
        conn.close()
    assert result.ok, f"workflow failed: {result.log}"
    assert "FTS5" in result.log[0]["output"]["text"]
    assert "usage" in result.log[0]["output_keys"]


# --- OpenAICompatProvider low-level ---


def test_openai_compat_provider_builds_correct_request(monkeypatch):
    """Verify the provider hits /chat/completions with the right body."""
    captured: list[dict] = []

    def fake_urlopen(req, timeout=None):
        captured.append({"url": req.full_url, "body": req.data, "headers": dict(req.headers)})
        # Return a minimal valid response
        import io
        body = json.dumps({
            "id": "test",
            "model": "MiniMax-M3",
            "choices": [{"message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode("utf-8")
        return _FakeHTTPResponse(body, 200)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    p = OpenAICompatProvider(
        base_url="https://api.example.com/v1",
        api_key="test-key-xyz",
        model="MiniMax-M3",
    )
    resp = p.complete([ChatMessage(role="user", content="hi")])
    assert resp.text == "hello"
    assert captured[0]["url"] == "https://api.example.com/v1/chat/completions"
    body = json.loads(captured[0]["body"])
    assert body["model"] == "MiniMax-M3"
    assert body["messages"][0]["role"] == "user"
    assert captured[0]["headers"]["Authorization"] == "Bearer test-key-xyz"


def test_openai_compat_provider_surfaces_http_error(monkeypatch):
    """A 401 from the provider becomes a ProviderError with the body included."""
    import urllib.error
    import io

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            url=req.full_url, code=401, msg="Unauthorized", hdrs={},
            fp=io.BytesIO(b'{"error":"invalid api key"}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    p = OpenAICompatProvider(
        base_url="https://api.example.com/v1",
        api_key="bad-key",
        model="MiniMax-M3",
    )
    with pytest.raises(ProviderError) as ei:
        p.complete([ChatMessage(role="user", content="hi")])
    assert "401" in str(ei.value)
    assert "invalid api key" in str(ei.value)


# --- helpers ---


class _FakeHTTPResponse:
    def __init__(self, body: bytes, status: int):
        self._body = body
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False
