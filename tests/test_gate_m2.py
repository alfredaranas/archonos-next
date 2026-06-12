"""Gate test for Milestone 2 — Local Knowledge Base.

Gate: import 10+ docs, ranked search returns results <200ms, dedup works.
"""

from __future__ import annotations

import time
import pytest
from pathlib import Path

from archonos.core import ops
from archonos.knowledge import import_ as kb_import
from archonos.knowledge import search as kb_search
from archonos.storage import db


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHONOS_HOME", str(tmp_path))
    ops.init()
    return tmp_path


@pytest.fixture
def conn(isolated_home):
    c = db.get_connection()
    yield c
    c.close()


@pytest.fixture
def sample_docs(tmp_path):
    """Create 10 sample markdown documents."""
    docs_dir = tmp_path / "sample_docs"
    docs_dir.mkdir()
    topics = [
        ("ultrasound_physics", "# Ultrasound Physics\n\nPiezoelectric crystals convert electrical energy to sound waves. Frequency determines resolution and penetration depth. Higher frequency = better resolution, less penetration."),
        ("artifacts", "# Ultrasound Artifacts\n\nReverberation artifacts occur when sound bounces between two strong reflectors. Mirror artifacts appear on opposite side of strong reflector. Shadowing occurs behind calcifications."),
        ("doppler", "# Doppler Effect\n\nDoppler shift measures velocity of moving structures. Color Doppler shows direction and velocity. Spectral Doppler quantifies blood flow velocity waveforms."),
        ("transducers", "# Transducer Types\n\nLinear transducers produce rectangular image, best for superficial structures. Curved transducers produce wider field of view. Phased array for cardiac imaging through small windows."),
        ("knobology", "# Knobology\n\nGain controls overall brightness. Time gain compensation adjusts depth-specific gain. Focus optimizes resolution at specific depth. Depth adjusts displayed range."),
        ("abdomen", "# Abdominal Ultrasound\n\nLiver evaluation includes echogenicity, size, and vascular anatomy. Gallbladder assessment for stones, wall thickening, and pericholecystic fluid. Kidneys measured in three planes."),
        ("obstetrics", "# Obstetric Ultrasound\n\nFirst trimester dating uses crown-rump length. Second trimester uses biparietal diameter, femur length, abdominal circumference. Amniotic fluid index assesses fluid volume."),
        ("cardiac", "# Cardiac Ultrasound\n\nEchocardiography assesses chamber size, wall motion, and valve function. Ejection fraction measures systolic function. Diastolic function assessed by mitral inflow patterns."),
        ("vascular", "# Vascular Ultrasound\n\nCarotid duplex evaluates for stenosis using peak systolic velocity. ABI compares ankle to brachial pressures. Deep vein thrombosis assessment uses compression technique."),
        ("msk", "# Musculoskeletal Ultrasound\n\nTendon evaluation in long and short axis. Dynamic imaging during movement. Calcifications appear hyperechoic with shadowing. Effusions appear anechoic."),
    ]
    for name, content in topics:
        (docs_dir / f"{name}.md").write_text(content)
    return docs_dir


def test_import_multiple_docs(conn, sample_docs):
    report = kb_import.import_path(conn, sample_docs)
    assert report.docs_added == 10
    assert report.chunks_added >= 10
    assert report.skipped_dupes == 0


def test_import_dedup(conn, sample_docs):
    kb_import.import_path(conn, sample_docs)
    report2 = kb_import.import_path(conn, sample_docs)
    assert report2.docs_added == 0
    assert report2.skipped_dupes == 10


def test_import_single_file(conn, tmp_path):
    f = tmp_path / "test.md"
    f.write_text("# Test\n\nThis is a test document about ultrasound imaging.")
    report = kb_import.import_path(conn, f)
    assert report.docs_added == 1
    assert report.chunks_added >= 1


def test_search_returns_results(conn, sample_docs):
    kb_import.import_path(conn, sample_docs)
    results = kb_search.search(conn, "piezoelectric crystal frequency")
    assert len(results) > 0
    assert results[0].title is not None
    assert results[0].snippet is not None


def test_search_ranking(conn, sample_docs):
    kb_import.import_path(conn, sample_docs)
    results = kb_search.search(conn, "doppler velocity blood flow")
    assert len(results) > 0
    # Most relevant result should mention doppler
    top_title = results[0].title.lower()
    top_snippet = results[0].snippet.lower()
    assert "doppler" in top_title or "doppler" in top_snippet


def test_search_performance(conn, sample_docs):
    kb_import.import_path(conn, sample_docs)
    start = time.time()
    for _ in range(10):
        kb_search.search(conn, "ultrasound physics resolution")
    elapsed = (time.time() - start) / 10
    assert elapsed < 0.2, f"Search too slow: {elapsed:.3f}s avg (gate: <200ms)"


def test_search_empty_query(conn, sample_docs):
    kb_import.import_path(conn, sample_docs)
    results = kb_search.search(conn, "")
    assert results == []


def test_search_no_results(conn, sample_docs):
    kb_import.import_path(conn, sample_docs)
    results = kb_search.search(conn, "xyzzy_nonexistent_term_12345")
    assert isinstance(results, list)


def test_chunk_text_basic():
    text = "word " * 1000
    chunks = kb_import.chunk_text(text, target_chars=1500, overlap=200)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 1500 + 50  # small tolerance for word boundary


def test_chunk_text_short():
    text = "Short text."
    chunks = kb_import.chunk_text(text)
    assert chunks == ["Short text."]


def test_status_reflects_imports(conn, sample_docs):
    kb_import.import_path(conn, sample_docs)
    conn.close()
    s = ops.status()
    assert s.documents == 10
    assert s.chunks >= 10
