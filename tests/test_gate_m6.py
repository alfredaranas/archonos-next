"""Gate test for Milestone 6 — LLM Provider Layer (RAG).

Gate:
1. archonos.knowledge.ask exists and is callable
2. With a stub provider, ask() returns a grounded AskResult with chunks_used > 0
3. Without API key + real provider, ask() raises a clean RuntimeError (graceful degraded mode)
4. M1–M5 commands still work without any provider configured (local-first preserved)
5. CLI 'archonos ask' is wired up

Uses a stub provider so the test runs offline — no API calls, no keys needed.
"""
from __future__ import annotations

import os
import pytest

from archonos.core import ops
from archonos.knowledge import import_ as kb_import
from archonos.knowledge import ask as kb_ask
from archonos.llm import providers as llm_providers
from archonos.storage import db


# ── Stub provider ────────────────────────────────────────────────────────────


@llm_providers.register_provider("stub")
class StubProvider(llm_providers.Provider):
    """Test-only provider. Returns deterministic responses, no network."""

    def __init__(self):
        self.last_messages = None

    def complete(self, messages, **kwargs):
        self.last_messages = messages
        # Echo back what context the prompt contained (proves RAG worked)
        user = next((m for m in messages if m.role == "user"), None)
        return llm_providers.CompletionResult(
            content=f"stub_answer: received {len(messages)} messages, last user msg has {len(user.content) if user else 0} chars",
            model="stub-1",
            usage={"input_tokens": 10, "output_tokens": 5},
        )

    def chat(self, prompt, system="", **kwargs):
        msgs = []
        if system:
            msgs.append(llm_providers.Message(role="system", content=system))
        msgs.append(llm_providers.Message(role="user", content=prompt))
        return self.complete(msgs, **kwargs).content


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    # ensure clean provider registry state between tests
    llm_providers.registry._providers.clear()
    ops.init()
    return tmp_path


@pytest.fixture
def populated_kb(isolated_home):
    """A knowledge base with content the ask() can ground in."""
    docs = isolated_home / "kb"
    docs.mkdir()
    (docs / "sqlite_notes.md").write_text(
        "# SQLite Notes\n\nWAL mode improves concurrency. FTS5 needs INTEGER rowids. Foreign keys must be enabled per connection."
    )
    (docs / "fts5_rules.md").write_text(
        "# FTS5 Rules\n\nUse content_rowid pointing to the INTEGER primary key. UUID text columns are not valid rowid sources."
    )
    conn = db.get_connection()
    try:
        kb_import.import_path(conn, docs)
    finally:
        conn.close()


# ── Tests ────────────────────────────────────────────────────────────────────


def test_ask_module_exists():
    assert hasattr(kb_ask, "ask")
    assert hasattr(kb_ask, "AskResult")


def test_ask_returns_grounded_answer(populated_kb):
    conn = db.get_connection()
    try:
        result = kb_ask.ask(conn, "What does FTS5 require?", k=3, provider="stub")
    finally:
        conn.close()

    assert isinstance(result, kb_ask.AskResult)
    assert result.chunks_used > 0, "ask must retrieve before answering (RAG)"
    assert result.provider == "stub"
    assert result.answer  # non-empty
    assert "stub_answer" in result.answer


def test_ask_includes_retrieved_context_in_prompt(populated_kb):
    """The retrieved chunks must end up in the LLM's user message — the whole point of RAG."""
    conn = db.get_connection()
    try:
        kb_ask.ask(conn, "FTS5 rowid requirements", k=3, provider="stub")
    finally:
        conn.close()
    provider = llm_providers.registry.get("stub")
    user_msg = next((m for m in provider.last_messages if m.role == "user"), None)
    assert user_msg is not None
    assert "Context:" in user_msg.content
    assert "Question:" in user_msg.content
    # at least one of the docs should be referenced
    assert "FTS5" in user_msg.content or "rowid" in user_msg.content.lower()


def test_ask_empty_question_rejected(populated_kb):
    conn = db.get_connection()
    try:
        with pytest.raises(ValueError, match="empty"):
            kb_ask.ask(conn, "   ", provider="stub")
    finally:
        conn.close()


def test_ask_unknown_provider_clean_error(populated_kb):
    conn = db.get_connection()
    try:
        with pytest.raises(RuntimeError, match="unknown provider"):
            kb_ask.ask(conn, "anything", provider="nonexistent_provider_xyz")
    finally:
        conn.close()


def test_ask_no_api_key_graceful_error(populated_kb, monkeypatch):
    """No-key mode: ask() fails cleanly, everything else keeps working (local-first promise)."""
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    conn = db.get_connection()
    try:
        with pytest.raises(RuntimeError, match="no API key"):
            kb_ask.ask(conn, "test", provider="minimax")
    finally:
        conn.close()


def test_no_provider_does_not_break_other_commands(monkeypatch):
    """The core local-first guarantee: with no LLM config, all M1-M5 still pass."""
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    s = ops.status()  # M1
    assert s.schema_version == 1

    h = ops.healthcheck()  # M1
    assert h.ok

    from archonos.memory import ops as mem_ops
    from archonos.workflows import ops as wf_ops
    conn = db.get_connection()
    try:
        mem_id = mem_ops.remember(conn, "note", "no-key mode works")  # M4
        assert mem_id > 0
        wf_id = wf_ops.register(conn, "test", {"steps": [{"name": "noop", "action": "log"}]})  # M3
        assert wf_id > 0
    finally:
        conn.close()


def test_cli_ask_command_wired():
    """The 'archonos ask' command is registered in the argparse surface."""
    from archonos.cli.main import build_parser
    parser = build_parser()
    # Should parse without error
    args = parser.parse_args(["ask", "test question", "--provider", "stub", "-k", "3"])
    assert args.question == "test question"
    assert args.provider == "stub"
    assert args.k == 3


def test_provider_registry_has_three_providers():
    """MiniMax, OpenAI, Anthropic — replaceability promise."""
    # importing providers triggers registration
    from archonos.llm import providers as p
    assert "minimax" in p.PROVIDERS
    assert "openai" in p.PROVIDERS
    assert "anthropic" in p.PROVIDERS


def test_provider_swap_via_env(populated_kb, monkeypatch):
    """LLM_PROVIDER env var swaps the active provider — model-agnostic OS."""
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    conn = db.get_connection()
    try:
        result = kb_ask.ask(conn, "test the env swap")
    finally:
        conn.close()
    assert result.provider == "stub"
