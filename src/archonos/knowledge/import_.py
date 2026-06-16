"""Document import for ArchonOS knowledge base.

Per docs/architecture/CORE_ARCHITECTURE.md §4:
    import_path(conn, path) -> ImportReport(docs_added, chunks_added, skipped_dupes)

Per §1: pure functions, no printing.
Per §2: documents table has sha256 UNIQUE for dedupe.
Per BASE_PLAN.md M2: import md/txt into documents + chunks; FTS5 is the search story.

Post-alpha extensions (M6+):
    import_documents(conn, documents) -> ImportReport
        Bulk-import a list of Document objects from any source
        (arXiv, OpenAlex, etc.) without writing to disk.
    PDF import: supported via pdfminer.six if installed, else a
        stdlib fallback for text-based PDFs. The fallback is best-effort
        and may fail on scanned PDFs.
    .archonosignore: same syntax as .gitignore; patterns relative to
        the import root.
"""

from __future__ import annotations

import fnmatch
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from archonos.knowledge.chunk import chunk_text
from archonos.storage import db


SUPPORTED_SUFFIXES = {".md", ".txt", ".pdf"}
ENCODING = "utf-8"


@dataclass
class ImportReport:
    docs_added: int = 0
    chunks_added: int = 0
    skipped_dupes: int = 0
    skipped_ignored: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


# --- .archonosignore ---


def _load_ignore_patterns(root: Path) -> list[str]:
    """Load ignore patterns from <root>/.archonosignore. Patterns are
    fnmatch globs (same syntax as .gitignore's simplest form). Lines
    starting with '#' are comments. Empty lines are skipped."""
    ignore_file = root / ".archonosignore"
    if not ignore_file.is_file():
        return []
    patterns: list[str] = []
    for line in ignore_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def _is_ignored(path: Path, root: Path, patterns: list[str]) -> bool:
    """True if path matches any of the ignore patterns (relative to root)."""
    if not patterns:
        return False
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return False
    for pat in patterns:
        # Match against both the full relative path and just the filename
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(path.name, pat):
            return True
        # Directory-level: "node_modules" matches anything inside
        if "/" not in pat and any(part == pat for part in rel.split("/")):
            return True
    return False


# --- PDF text extraction (best-effort) ---


_PDF_NEEDS_MINER = "install pdfminer.six (`pip install pdfminer.six`) for better PDF text extraction"


def _extract_pdf_text(path: Path) -> str:
    """Extract text from a PDF. Tries pdfminer.six first; falls back to
    a stdlib text-stream extraction (works for many text-based PDFs,
    fails on image-only / scanned PDFs).

    Raises RuntimeError with a helpful message if neither path works.
    """
    # First choice: pdfminer.six (best fidelity, handles fonts, layout)
    try:
        from pdfminer.high_level import extract_text as _pdfminer_extract
        return _pdfminer_extract(str(path))
    except ImportError:
        pass
    except Exception as e:
        # If pdfminer is installed but the file is malformed, fall through
        # to the stdlib attempt before erroring.
        last_err = e
    else:
        last_err = None  # type: ignore[assignment]

    # Fallback: stdlib text-stream extraction.
    # Many academic PDFs store text in uncompressed streams we can read
    # by looking for parenthesized strings. This is best-effort — it
    # misses glyphs that are encoded as drawing commands (e.g. scanned
    # PDFs) but works on the majority of text-based papers.
    try:
        raw = path.read_bytes()
        # Extract anything inside (...) that's a printable TJ/Tj arg.
        # The PDF text-showing operators are: Tj, TJ, ', "
        # Their string args are parenthesized or hex.
        candidates = re.findall(rb"\((.*?)\)\s*T[jJ]", raw, flags=re.DOTALL)
        text = b" ".join(candidates).decode("latin-1", errors="replace")
        if text.strip():
            return text
        # Try hex strings
        hex_candidates = re.findall(rb"<([0-9a-fA-F\s]+)>\s*T[jJ]", raw)
        text = b" ".join(bytes.fromhex(re.sub(rb"\s+", b"", h).decode("ascii")) for h in hex_candidates).decode(
            "latin-1", errors="replace"
        )
        if text.strip():
            return text
        raise RuntimeError(
            f"could not extract text from {path.name}: no text streams found. "
            + _PDF_NEEDS_MINER
        )
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(
            f"failed to extract text from {path.name}: {e}. " + _PDF_NEEDS_MINER
        ) from e


# --- file iteration ---


def _iter_files(
    path: Path,
    ignore_patterns: list[str] | None = None,
    report: ImportReport | None = None,
) -> Iterable[Path]:
    """Yield supported files under `path`. If path is a file, yield it
    directly. If a directory, walk recursively. Honors .archonosignore
    in the root. If a report is given, ignored files are counted in
    report.skipped_ignored."""
    if path.is_file():
        # Single file: no ignore applies unless caller checks separately
        yield path
        return
    if path.is_dir():
        patterns = ignore_patterns or []
        for p in sorted(path.rglob("*")):
            if not p.is_file():
                continue
            if p.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if _is_ignored(p, path, patterns):
                if report is not None:
                    report.skipped_ignored += 1
                continue
            yield p
        return
    raise FileNotFoundError(f"Path not found: {path}")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode(ENCODING)).hexdigest()


def _title_from(path: Path) -> str:
    return path.stem


def _doc_type_from(path: Path) -> str:
    s = path.suffix.lower()
    if s == ".md":
        return "md"
    if s == ".txt":
        return "txt"
    if s == ".pdf":
        return "pdf"
    return s.lstrip(".")


def import_path(conn, path, *, honor_ignore: bool = True) -> ImportReport:  # type: ignore[no-untyped-def]
    """Import a file or directory of supported files into the knowledge base.

    Dedupe: if a document with the same sha256 already exists, skip.
    Re-importing the same content is a no-op; re-importing after a content
    change creates a new document (the old one is kept — we don't auto-prune
    in v1).

    If `path` is a directory, .archonosignore in that directory is honored
    (set honor_ignore=False to disable).
    """
    report = ImportReport()
    p = Path(path).resolve()

    if p.is_dir() and honor_ignore:
        ignore_patterns = _load_ignore_patterns(p)
    else:
        ignore_patterns = []

    for file in _iter_files(p, ignore_patterns, report=report):
        if file.suffix.lower() == ".pdf":
            try:
                text = _extract_pdf_text(file)
            except RuntimeError as e:
                report.errors.append(f"{file}: {e}")
                continue
        else:
            try:
                text = file.read_text(encoding=ENCODING)
            except UnicodeDecodeError as e:
                report.errors.append(f"{file}: decode error: {e}")
                continue
            except OSError as e:
                report.errors.append(f"{file}: read error: {e}")
                continue

        digest = _sha256(text)
        existing = conn.execute(
            "SELECT id FROM documents WHERE sha256 = ?", (digest,)
        ).fetchone()
        if existing is not None:
            report.skipped_dupes += 1
            continue

        # Insert document
        byte_size = file.stat().st_size
        doc_type = _doc_type_from(file)
        cur = conn.execute(
            "INSERT INTO documents(source_path, title, doc_type, sha256, byte_size) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(file), _title_from(file), doc_type, digest, byte_size),
        )
        doc_id = int(cur.lastrowid)
        report.docs_added += 1

        # Chunk + insert chunks
        chunks = chunk_text(text)
        for idx, body in enumerate(chunks):
            conn.execute(
                "INSERT INTO chunks(document_id, chunk_idx, body, body_chars) "
                "VALUES (?, ?, ?, ?)",
                (doc_id, idx, body, len(body)),
            )
            report.chunks_added += 1

    conn.commit()
    return report


def import_documents(
    conn,
    documents: Iterable,  # Iterable[Document] from archonos.knowledge.sources
) -> ImportReport:  # type: ignore[no-untyped-def]
    """Bulk-import a list of Document objects (from any source) into
    the knowledge base. Same dedupe contract as import_path: a document
    whose sha256 already exists is skipped.

    This is the integration point for the paper-source modules
    (arXiv, OpenAlex, etc.) — the kernel doesn't care whether content
    came from a local .md file or a remote API, only that it has the
    right shape.
    """
    import json as _json
    report = ImportReport()

    for doc in documents:
        try:
            text = doc.content
            digest = doc.sha256 or _sha256(text)
            existing = conn.execute(
                "SELECT id FROM documents WHERE sha256 = ?", (digest,)
            ).fetchone()
            if existing is not None:
                report.skipped_dupes += 1
                continue

            byte_size = doc.byte_size or len(text.encode(ENCODING))
            meta_json = _json.dumps(doc.to_meta())
            cur = conn.execute(
                "INSERT INTO documents(source_path, title, doc_type, sha256, byte_size, meta) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (doc.source_path, doc.title, doc.doc_type, digest, byte_size, meta_json),
            )
            doc_id = int(cur.lastrowid)
            report.docs_added += 1

            chunks = chunk_text(text)
            for idx, body in enumerate(chunks):
                conn.execute(
                    "INSERT INTO chunks(document_id, chunk_idx, body, body_chars) "
                    "VALUES (?, ?, ?, ?)",
                    (doc_id, idx, body, len(body)),
                )
                report.chunks_added += 1
        except Exception as e:
            report.errors.append(f"{getattr(doc, 'source_path', '<unknown>')}: {type(e).__name__}: {e}")

    conn.commit()
    return report


# Convenience: for tests + direct use
def get_document_count(conn) -> int:  # type: ignore[no-untyped-def]
    return int(conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"])


def get_chunk_count(conn) -> int:  # type: ignore[no-untyped-def]
    return int(conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"])


# Public so other modules + tests can introspect
__all__ = [
    "ImportReport",
    "SUPPORTED_SUFFIXES",
    "import_documents",
    "import_path",
    "get_document_count",
    "get_chunk_count",
]
