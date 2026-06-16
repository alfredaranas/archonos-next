"""Tests for the Hugging Face source module (9th paper source).

Live-network tests. Skipped if network is unavailable (same gate as
tests/test_sources.py).
"""

from __future__ import annotations

import socket
import sys
import os

import pytest

from archonos.knowledge.sources.huggingface import (
    HuggingFaceSource,
    _strip_hf_prefix,
)
from archonos.knowledge.sources.base import (
    Document,
    SourceError,
    all_sources,
    parse_identifier,
)
from archonos.knowledge import import_ as kb_import
from archonos.core import ops


# --- network availability gate (same as test_sources.py) ---

def _network_ok() -> bool:
    try:
        with socket.create_connection(("huggingface.co", 443), timeout=3):
            return True
    except (OSError, socket.timeout):
        return False


def _skip_if_offline():
    if not _network_ok():
        pytest.skip("network unavailable")


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    return tmp_path


# --- identifier parsing (no network) ---


def test_strip_hf_prefix_bare_hf():
    assert _strip_hf_prefix("hf:meta-llama/Llama-3-70B") == ("model", "meta-llama/Llama-3-70B")


def test_strip_hf_prefix_explicit_model():
    assert _strip_hf_prefix("model:google-bert/bert-base-uncased") == ("model", "google-bert/bert-base-uncased")


def test_strip_hf_prefix_dataset():
    # HF has datasets that are owner/name and also a few root-level ones
    # (legacy). Use a real one to be safe.
    assert _strip_hf_prefix("dataset:rajpurkar/squad") == ("dataset", "rajpurkar/squad")


def test_strip_hf_prefix_space():
    assert _strip_hf_prefix("space:gradio/chatbot") == ("space", "gradio/chatbot")


def test_strip_hf_prefix_default_is_model():
    assert _strip_hf_prefix("google-bert/bert-base-uncased") == ("model", "google-bert/bert-base-uncased")


def test_strip_hf_prefix_rejects_no_slash():
    with pytest.raises(SourceError):
        _strip_hf_prefix("hf:noslash")


# --- registration ---


def test_hf_registered_in_all_sources():
    srcs = all_sources()
    assert "hf" in srcs
    assert isinstance(srcs["hf"], HuggingFaceSource)
    assert srcs["hf"].scheme == "hf"
    assert srcs["hf"].name == "Hugging Face"


def test_hf_url_recognized_by_parse_identifier():
    scheme, ident = parse_identifier("https://huggingface.co/google-bert/bert-base-uncased")
    assert scheme == "hf"


# --- search (live network) ---


def test_search_returns_results_for_common_query():
    _skip_if_offline()
    src = HuggingFaceSource()
    docs = src.search("bert", limit=5)
    assert len(docs) >= 1
    assert all(isinstance(d, Document) for d in docs)
    assert all("huggingface.co" in d.source_path for d in docs)


def test_search_respects_limit():
    _skip_if_offline()
    src = HuggingFaceSource()
    docs = src.search("transformer", limit=3)
    assert len(docs) <= 3
    assert len(docs) >= 1


def test_search_includes_metadata():
    _skip_if_offline()
    src = HuggingFaceSource()
    docs = src.search("llama", limit=3)
    assert len(docs) >= 1
    d = docs[0]
    assert "repo_id" in d.meta
    assert "downloads" in d.meta
    assert d.meta["kind"] == "model"


# --- fetch (live network) ---


def test_fetch_bert_model_card():
    _skip_if_offline()
    src = HuggingFaceSource()
    docs = src.fetch("hf:google-bert/bert-base-uncased")
    assert len(docs) == 1
    d = docs[0]
    assert d.title == "google-bert/bert-base-uncased"
    assert d.doc_type == "hf_model"
    assert d.meta["kind"] == "model"
    assert d.meta["repo_id"] == "google-bert/bert-base-uncased"
    assert d.meta["pipeline_tag"] == "fill-mask"
    assert d.meta["library_name"] == "transformers"
    # Our formatted content has these markers
    assert "Pipeline:" in d.content
    assert "Downloads:" in d.content
    assert "Tags:" in d.content


def test_fetch_via_url():
    _skip_if_offline()
    src = HuggingFaceSource()
    docs = src.fetch("https://huggingface.co/google-bert/bert-base-uncased")
    assert len(docs) == 1
    assert "bert" in docs[0].title.lower()


def test_fetch_unknown_repo_raises():
    _skip_if_offline()
    src = HuggingFaceSource()
    with pytest.raises(SourceError):
        src.fetch("hf:zzz-nonexistent-org-12345-zzz/zzz-nonexistent-model-67890-zzz")


# --- end-to-end: fetch + import into a real KB ---


def test_fetched_doc_imports_into_kb():
    _skip_if_offline()
    ops.init("default")
    from archonos.storage import db
    conn = db.get_connection("default")
    try:
        src = HuggingFaceSource()
        docs = src.fetch("hf:google-bert/bert-base-uncased")
        report = kb_import.import_documents(conn, docs)
        assert report.docs_added == 1
        assert report.chunks_added >= 1
        # Verify the doc landed
        row = conn.execute(
            "SELECT title, doc_type FROM documents WHERE source_path=?",
            (docs[0].source_path,),
        ).fetchone()
        assert row is not None
        assert row["title"] == "google-bert/bert-base-uncased"
        assert row["doc_type"] == "hf_model"
    finally:
        conn.close()
