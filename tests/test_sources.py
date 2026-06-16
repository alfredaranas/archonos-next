"""Tests for the paper-source modules (M6+ feature).

All tests are network-dependent. They are auto-skipped if the network
is unavailable or the remote API is unreachable, so the suite stays
green offline. The pytest marker `network` lets you opt in/out:

    pytest tests/test_sources.py -v                # all online tests
    pytest tests/test_sources.py -v -m "not network"   # skip network tests
    pytest tests/test_sources.py -v -m network          # only network tests
"""

from __future__ import annotations

import socket
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from archonos.cli.main import main
from archonos.core import ops
from archonos.knowledge.sources import (
    Document,
    SourceError,
    all_sources,
    parse_identifier,
)


# --- network availability gate ---


def _network_ok() -> bool:
    """Quick check: can we open a TCP connection to a known host?"""
    try:
        with socket.create_connection(("api.openalex.org", 443), timeout=3):
            return True
    except (OSError, socket.timeout):
        return False


# Single known-good identifier per source. If the network is down, all
# network-marked tests are skipped together.
NETWORK_IDS = {
    "arxiv":    "arxiv:1706.03762",    # Attention Is All You Need
    "openalex": "openalex:W2741809807",
    "pmid":     "pmid:33212345",
    "doi":      "doi:10.1038/nature12373",
    "crossref": "crossref:10.1126/science.169.3946.635",
}


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    return tmp_path


def _skip_if_offline():
    if not _network_ok():
        pytest.skip("network unavailable")


# --- identifier parsing (no network needed) ---


def test_parse_identifier_scheme_prefix():
    assert parse_identifier("arxiv:2501.12345") == ("arxiv", "2501.12345")
    assert parse_identifier("doi:10.1038/nature12373") == ("doi", "10.1038/nature12373")
    assert parse_identifier("pmid:33212345") == ("pmid", "33212345")


def test_parse_identifier_url_forms():
    assert parse_identifier("https://arxiv.org/abs/2501.12345") == ("arxiv", "https://arxiv.org/abs/2501.12345")
    assert parse_identifier("https://pubmed.ncbi.nlm.nih.gov/33212345/") == ("pmid", "https://pubmed.ncbi.nlm.nih.gov/33212345/")
    assert parse_identifier("https://doi.org/10.1038/nature12373") == ("doi", "https://doi.org/10.1038/nature12373")
    assert parse_identifier("https://openalex.org/W2741809807") == ("openalex", "https://openalex.org/W2741809807")
    assert parse_identifier("https://huggingface.co/google-bert/bert-base-uncased") == ("hf", "https://huggingface.co/google-bert/bert-base-uncased")


def test_parse_identifier_hf_dataset_space_aliases():
    # `dataset:` and `space:` are sub-types of `hf:` — they route to the
    # Hugging Face source but the source re-parses the kind from the prefix.
    assert parse_identifier("dataset:rajpurkar/squad") == ("hf", "dataset:rajpurkar/squad")
    assert parse_identifier("space:gradio/chatbot") == ("hf", "space:gradio/chatbot")
    assert parse_identifier("model:google-bert/bert-base-uncased") == ("hf", "model:google-bert/bert-base-uncased")


def test_parse_identifier_rejects_bare():
    with pytest.raises(SourceError):
        parse_identifier("2501.12345")  # no scheme


# --- registry ---


def test_registry_has_all_9_sources():
    srcs = all_sources()
    expected = {"arxiv", "openalex", "pmid", "pmcid", "doi", "core", "crossref", "doaj", "hf"}
    assert set(srcs) == expected
    for s in srcs.values():
        assert s.scheme
        assert s.base_url.startswith("http")
        assert s.name


# --- Document contract (no network needed) ---


def test_document_to_meta_round_trip():
    d = Document(
        source_path="https://arxiv.org/abs/1706.03762",
        title="Attention Is All You Need",
        doc_type="arxiv",
        content="...",
        meta={"arxiv_id": "1706.03762", "authors": ["A. Vaswani"]},
    )
    m = d.to_meta()
    assert m["source_path"] == "https://arxiv.org/abs/1706.03762"
    assert m["title"] == "Attention Is All You Need"
    assert m["doc_type"] == "arxiv"
    assert m["arxiv_id"] == "1706.03762"
    assert m["authors"] == ["A. Vaswani"]


# --- source.fetch (network) ---


@pytest.mark.parametrize("scheme,ident", list(NETWORK_IDS.items()))
def test_source_fetch_live(scheme, ident):
    """Each source returns at least one Document for its known-good id."""
    _skip_if_offline()
    sources = all_sources()
    src = sources[scheme]
    docs = src.fetch(ident)
    assert len(docs) >= 1
    d = docs[0]
    assert d.title.strip()
    assert d.content.strip()
    # doc_type identifies the kind of document (e.g. 'pubmed', 'arxiv',
    # 'unpaywall'). The scheme may differ (e.g. 'doi' -> 'unpaywall').
    assert d.doc_type
    assert d.source_path.startswith("http")
    # Meta round-trips through to_meta()
    m = d.to_meta()
    assert m["source_path"] == d.source_path


# --- source.search (network) ---


@pytest.mark.parametrize("scheme", ["arxiv", "openalex", "crossref"])
def test_source_search_returns_results(scheme):
    _skip_if_offline()
    sources = all_sources()
    docs = sources[scheme].search("neural network", limit=2)
    assert len(docs) >= 1
    for d in docs:
        assert d.title.strip()
        assert d.content.strip()


# --- import_documents integration ---


def test_import_documents_persists_via_fetch(tmp_path, monkeypatch):
    """Fetch from a real source, then import_documents into the kernel."""
    _skip_if_offline()
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    ops.init()
    from archonos.knowledge import import_ as kb_import
    from archonos.storage import db

    sources = all_sources()
    docs = sources["arxiv"].fetch("arxiv:1706.03762")
    assert docs, "no docs fetched"

    conn = db.get_connection()
    try:
        report = kb_import.import_documents(conn, docs)
    finally:
        conn.close()
    assert report.docs_added == 1
    assert report.chunks_added >= 1
    assert report.skipped_dupes == 0
    assert report.errors == []


def test_import_documents_dedupes_by_sha256(tmp_path, monkeypatch):
    """Re-importing the same Document is a no-op."""
    _skip_if_offline()
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    ops.init()
    from archonos.knowledge import import_ as kb_import
    from archonos.storage import db

    sources = all_sources()
    docs = sources["arxiv"].fetch("arxiv:1706.03762")

    conn = db.get_connection()
    try:
        r1 = kb_import.import_documents(conn, docs)
        r2 = kb_import.import_documents(conn, docs)
    finally:
        conn.close()
    assert r1.docs_added == 1
    assert r2.docs_added == 0
    assert r2.skipped_dupes == 1


# --- CLI: archonos fetch ---


def test_cli_list_sources():
    assert main(["list-sources"]) == 0


def test_cli_fetch_paper(tmp_path, monkeypatch):
    _skip_if_offline()
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    assert main(["init"]) == 0
    rc = main(["fetch", "arxiv:1706.03762"])
    assert rc == 0


def test_cli_fetch_unknown_scheme(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    assert main(["init"]) == 0
    assert main(["fetch", "nosuchscheme:1"]) == 1


def test_cli_search_sources(tmp_path, monkeypatch):
    _skip_if_offline()
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    # Don't init — search-sources doesn't need the DB
    rc = main(["search-sources", "attention", "--source", "arxiv", "--limit", "2"])
    assert rc == 0


# --- workflow step: fetch ---


def test_workflow_step_fetch(tmp_path, monkeypatch):
    """The 'fetch' step type works in a workflow."""
    _skip_if_offline()
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    ops.init()
    from archonos.workflows import engine as wf_engine
    from archonos.workflows import registry as wf_registry
    from archonos.storage import db

    spec = {
        "steps": [
            {
                "id": "s1",
                "type": "fetch",
                "args": {"identifier": "arxiv:1706.03762"},
            }
        ]
    }
    conn = db.get_connection()
    try:
        wf_registry.register(conn, "fetch-test", spec)
        result = wf_engine.run(conn, "fetch-test", {})
    finally:
        conn.close()
    assert result.ok, f"workflow failed: {result.log}"
    assert "docs_added" in result.log[0]["output_keys"]
    assert result.log[0]["output"]["docs_added"] == 1
