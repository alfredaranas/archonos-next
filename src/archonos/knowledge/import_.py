"""Document import for ArchonOS knowledge base.

Per docs/architecture/CORE_ARCHITECTURE.md §4:
    import_path(conn, path) -> ImportReport(docs_added, chunks_added, skipped_dupes)

Per §1: pure functions, no printing.
Per §2: documents table has sha256 UNIQUE for dedupe.
Per BASE_PLAN.md M2: import md/txt into documents + chunks; FTS5 is the search story.

Post-alpha extensions (M6+):
    import_documents(conn, documents) -> ImportReport
        Bulk-import a list of Document objects from any source
        (arXiv, OpenAlex, Unpaywall, etc.) without writing to disk.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from archonos.knowledge.chunk import chunk_text
from archonos.storage import db


SUPPORTED_SUFFIXES = {".md", ".txt"}
ENCODING = "utf-8"


@dataclass
class ImportReport:
    docs_added: int = 0
    chunks_added: int = 0
    skipped_dupes: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    if path.is_dir():
        for p in sorted(path.rglob("*")):
            if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES:
                yield p
        return
    raise FileNotFoundError(f"Path not found: {path}")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode(ENCODING)).hexdigest()


def _title_from(path: Path) -> str:
    # Use filename stem; strips .md / .txt
    return path.stem


def import_path(conn, path) -> ImportReport:  # type: ignore[no-untyped-def]
    """Import a file or directory of supported files into the knowledge base.

    Dedupe: if a document with the same sha256 already exists, skip.
    Re-importing the same content is a no-op; re-importing after a content
    change creates a new document (the old one is kept — we don't auto-prune
    in v1).
    """
    report = ImportReport()
    p = Path(path).resolve()

    for file in _iter_files(p):
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
        doc_type = "md" if file.suffix.lower() == ".md" else "txt"
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
