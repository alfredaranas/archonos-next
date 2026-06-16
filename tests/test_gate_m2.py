"""Gate test for Milestone 2 — Local Knowledge Base.

The gate (per docs/BASE_PLAN.md M2):
    import 100 mixed docs, search returns ranked results < 200ms.

Per docs/architecture/CORE_ARCHITECTURE.md §7:
    every module contract gets a unit test against a tmp-path SQLite db.
    The gate test IS the milestone definition of done.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from archonos.cli.main import main
from archonos.core import ops
from archonos.knowledge import import_ as kb_import
from archonos.knowledge import search as kb_search
from archonos.knowledge.chunk import chunk_text
from archonos.storage import db


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    ops.init()
    return tmp_path


# --- chunk_text: unit tests against the spec contract ---


def test_chunk_text_empty_returns_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_text_short_text_single_chunk():
    text = "Hello world. " * 50  # ~650 chars
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text.strip()


def test_chunk_text_paragraph_aware():
    para1 = "a" * 800
    para2 = "b" * 800
    para3 = "c" * 800
    text = f"{para1}\n\n{para2}\n\n{para3}"
    chunks = chunk_text(text, target_chars=1500, overlap=200)
    # Each para fits, so we pack greedily
    assert len(chunks) >= 2
    # All text present
    reconstructed = " ".join(chunks).replace(" ", "")
    assert reconstructed == (para1 + para2 + para3)


def test_chunk_text_long_paragraph_uses_sliding_window():
    long = "x" * 5000
    chunks = chunk_text(long, target_chars=1000, overlap=100)
    assert len(chunks) >= 5
    # First and last chunks should be non-empty
    for c in chunks:
        assert c


def test_chunk_text_overlap_validation():
    long_text = "x" * 5000  # long enough to trigger hard-window
    with pytest.raises(ValueError):
        chunk_text(long_text, target_chars=100, overlap=100)


# --- import_path: contract per §4 ---


def test_import_path_file_md(isolated_home):
    f = isolated_home / "alpha.md"
    f.write_text("# Alpha\n\nFirst document body.", encoding="utf-8")
    conn = db.get_connection()
    try:
        report = kb_import.import_path(conn, f)
    finally:
        conn.close()
    assert report.docs_added == 1
    assert report.chunks_added == 1
    assert report.skipped_dupes == 0
    assert report.errors == []


def test_import_path_dedupes_by_sha256(isolated_home):
    f = isolated_home / "alpha.md"
    f.write_text("# Alpha\n\nFirst document body.", encoding="utf-8")
    conn = db.get_connection()
    try:
        r1 = kb_import.import_path(conn, f)
        r2 = kb_import.import_path(conn, f)
    finally:
        conn.close()
    assert r1.docs_added == 1
    assert r2.docs_added == 0
    assert r2.skipped_dupes == 1


def test_import_path_directory_recursive(isolated_home):
    docs = isolated_home / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("alpha content", encoding="utf-8")
    (docs / "b.txt").write_text("beta content", encoding="utf-8")
    (docs / "ignored.xyz").write_text("should be ignored", encoding="utf-8")
    nested = docs / "sub"
    nested.mkdir()
    (nested / "c.md").write_text("gamma content", encoding="utf-8")

    conn = db.get_connection()
    try:
        report = kb_import.import_path(conn, docs)
    finally:
        conn.close()
    assert report.docs_added == 3
    assert report.skipped_dupes == 0
    assert report.errors == []


def test_import_path_missing_path_raises(isolated_home):
    conn = db.get_connection()
    try:
        with pytest.raises(FileNotFoundError):
            kb_import.import_path(conn, isolated_home / "nope.md")
    finally:
        conn.close()


def test_import_path_preserves_metadata(isolated_home):
    f = isolated_home / "alpha.md"
    body = "Hello world body content for chunking test"
    f.write_text(body, encoding="utf-8")
    conn = db.get_connection()
    try:
        kb_import.import_path(conn, f)
        row = conn.execute("SELECT title, doc_type, byte_size, sha256 FROM documents").fetchone()
    finally:
        conn.close()
    assert row["title"] == "alpha"
    assert row["doc_type"] == "md"
    assert row["byte_size"] == f.stat().st_size
    assert len(row["sha256"]) == 64  # sha256 hex


# --- search: contract per §4 + performance gate from BASE_PLAN M2 ---


def _make_100_docs(home: Path) -> Path:
    """Generate 100 mixed md/txt docs with searchable terms."""
    docs = home / "corpus"
    docs.mkdir(exist_ok=True)
    terms_pool = [
        "python", "rust", "database", "kernel", "compilation", "memory",
        "binary", "fuzzing", "compiler", "interpreter", "bytecode", "stack",
        "queue", "linked", "graph", "tree", "hash", "sort", "search", "index",
    ]
    for i in range(100):
        suffix = "md" if i % 2 == 0 else "txt"
        # Mix 1-3 topic terms per doc
        a = terms_pool[i % len(terms_pool)]
        b = terms_pool[(i * 7 + 3) % len(terms_pool)]
        c = terms_pool[(i * 13 + 5) % len(terms_pool)] if i % 3 == 0 else None
        words = " ".join(filter(None, [a, b, c]))
        body = (
            f"Document {i}\n\n"
            f"This is filler text for document {i}. " * 8
            + f"\n\nTopics: {words}\n\n"
            + "Closing paragraph with no special keywords. " * 6
        )
        (docs / f"doc-{i:03d}.{suffix}").write_text(body, encoding="utf-8")
    return docs


def test_search_returns_ranked_results(isolated_home):
    docs = _make_100_docs(isolated_home)
    conn = db.get_connection()
    try:
        kb_import.import_path(conn, docs)
    finally:
        conn.close()

    conn = db.get_connection()
    try:
        hits = kb_search.search(conn, "python kernel", k=5)
    finally:
        conn.close()
    assert len(hits) >= 1
    # BM25 ties are possible; assert weak monotonicity (allow tiny FP noise).
    # Best (index 0) must be >= worst (last) and never strictly less.
    for i in range(len(hits) - 1):
        assert hits[i].rank >= hits[i + 1].rank - 1e-9, (
            f"rank not monotonic: hits[{i}].rank={hits[i].rank} < hits[{i+1}].rank={hits[i+1].rank}"
        )
    # Each hit has the required fields populated
    for h in hits:
        assert h.snippet
        assert h.doc_title
        assert h.chunk_id > 0
        assert 0.0 <= h.rank <= 1.0


def test_search_empty_query_returns_empty(isolated_home):
    conn = db.get_connection()
    try:
        assert kb_search.search(conn, "") == []
        assert kb_search.search(conn, "   ") == []
    finally:
        conn.close()


def test_search_no_results_returns_empty(isolated_home):
    docs = _make_100_docs(isolated_home)
    conn = db.get_connection()
    try:
        kb_import.import_path(conn, docs)
    finally:
        conn.close()
    conn = db.get_connection()
    try:
        hits = kb_search.search(conn, "xyzzyplugh_nonexistent_term", k=5)
    finally:
        conn.close()
    assert hits == []


# --- THE GATE: 100 docs, search < 200ms ---


def test_gate_m2_100_docs_search_under_200ms(isolated_home):
    """The M2 gate from BASE_PLAN.md: 100 mixed docs, search < 200ms."""
    docs = _make_100_docs(isolated_home)

    conn = db.get_connection()
    try:
        report = kb_import.import_path(conn, docs)
        assert report.errors == []
        assert report.docs_added == 100
        assert report.skipped_dupes == 0
        # Sanity: chunks > docs (each doc has 1+ chunks)
        assert report.chunks_added >= 100
    finally:
        conn.close()

    # Verify FTS5 is in sync (sync triggers fired on insert)
    conn = db.get_connection()
    try:
        fts_count = int(
            conn.execute("SELECT COUNT(*) AS n FROM chunks_fts").fetchone()["n"]
        )
        chunks_count = int(
            conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        )
        assert fts_count == chunks_count, (
            f"FTS out of sync: {fts_count} in chunks_fts vs {chunks_count} in chunks"
        )
    finally:
        conn.close()

    # THE GATE: < 200ms
    conn = db.get_connection()
    try:
        # Warm up (first query parses the FTS5 query expression)
        kb_search.search(conn, "python", k=10)
        # Measured query
        t0 = time.perf_counter()
        hits = kb_search.search(conn, "python kernel", k=10)
        elapsed_ms = (time.perf_counter() - t0) * 1000
    finally:
        conn.close()
    assert hits, "search returned no results for known terms"
    assert elapsed_ms < 200, f"search took {elapsed_ms:.1f}ms (gate: <200ms)"


# --- CLI wiring: §5 surface ---


def test_cli_import_command(isolated_home):
    f = isolated_home / "alpha.md"
    f.write_text("# Alpha\n\nBody for CLI test.", encoding="utf-8")
    rc = main(["import", str(f)])
    assert rc == 0


def test_cli_search_command(isolated_home):
    f = isolated_home / "alpha.md"
    f.write_text("Python is a programming language. " * 20, encoding="utf-8")
    assert main(["import", str(f)]) == 0
    assert main(["search", "python"]) == 0


def test_cli_import_missing_path_is_user_error(isolated_home):
    rc = main(["import", str(isolated_home / "nope.md")])
    assert rc == 1


def test_cli_search_before_init_is_user_error(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path / "fresh"))
    assert main(["search", "anything"]) == 1
