"""Knowledge import — file/folder → documents + chunks."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ImportReport:
    docs_added: int
    chunks_added: int
    skipped_dupes: int


def import_path(conn: sqlite3.Connection, path: Path) -> ImportReport:
    """Import a file or folder into the knowledge base.
    
    Returns an ImportReport with counts.
    """
    path = path.resolve()
    
    docs_added = 0
    chunks_added = 0
    skipped_dupes = 0
    
    # Collect files to import
    files = []
    if path.is_file():
        files.append(path)
    elif path.is_dir():
        for ext in ("*.md", "*.txt", "*.pdf"):
            files.extend(path.rglob(ext))
    
    for file_path in files:
        # Read and hash
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
            
        sha = hashlib.sha256(content.encode()).hexdigest()
        
        # Check for duplicate
        existing = conn.execute(
            "SELECT id FROM documents WHERE sha256 = ?", (sha,)
        ).fetchone()
        
        if existing:
            skipped_dupes += 1
            continue
        
        # Determine doc type
        ext = file_path.suffix.lower()
        doc_type = {"md": "md", ".txt": "txt", ".pdf": "pdf"}.get(ext, "txt")
        
        # Insert document
        cursor = conn.execute(
            """INSERT INTO documents (source_path, title, doc_type, sha256, byte_size)
               VALUES (?, ?, ?, ?, ?)""",
            (str(file_path), file_path.stem, doc_type, sha, len(content.encode()))
        )
        doc_id = cursor.lastrowid
        
        # Chunk the content
        chunks = chunk_text(content)
        for idx, chunk_body in enumerate(chunks):
            conn.execute(
                """INSERT INTO chunks (document_id, chunk_idx, body, body_chars)
                   VALUES (?, ?, ?, ?)""",
                (doc_id, idx, chunk_body, len(chunk_body))
            )
            chunks_added += 1
        
        docs_added += 1
    
    conn.commit()
    return ImportReport(docs_added=docs_added, chunks_added=chunks_added, skipped_dupes=skipped_dupes)


def chunk_text(text: str, target_chars: int = 1500, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks."""
    if len(text) <= target_chars:
        return [text] if text.strip() else []
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + target_chars
        
        # Try to break at word boundary
        if end < len(text):
            # Look for whitespace in the overlap region
            break_point = text.rfind(" ", start + target_chars - overlap, end)
            if break_point > start:
                end = break_point
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        start = end - overlap if end < len(text) else end
    
    return chunks
