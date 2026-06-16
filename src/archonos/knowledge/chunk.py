"""Document chunking for ArchonOS knowledge base.

Per docs/architecture/CORE_ARCHITECTURE.md §4:
    chunk_text(text, target_chars=1500, overlap=200) -> list[str]

Per §8: M2 ships naive char-window chunking; tuning is post-alpha.
"""

from __future__ import annotations


def chunk_text(text: str, target_chars: int = 1500, overlap: int = 200) -> list[str]:
    """Split text into overlapping windows of approximately `target_chars`.

    Strategy: paragraph-aware sliding window.
    - If the full text fits in target_chars, return it as a single chunk.
    - Otherwise, walk paragraph boundaries and greedily pack them up to
      target_chars. If a single paragraph exceeds target_chars, fall back
      to character-window slicing for that paragraph.

    Args:
        text: The text to chunk. May contain \n-separated paragraphs.
        target_chars: Soft cap on chunk length.
        overlap: Approximate character overlap between consecutive chunks
            (only applied when we have to hard-window an oversized paragraph).

    Returns:
        Non-empty list of chunk strings. Order preserved.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= target_chars:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # Hard-window an oversized paragraph
        if len(para) > target_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(_window(para, target_chars, overlap))
            continue

        # Greedy pack
        candidate = (current + "\n\n" + para) if current else para
        if len(candidate) <= target_chars:
            current = candidate
        else:
            chunks.append(current.strip())
            current = para

    if current:
        chunks.append(current.strip())

    return [c for c in chunks if c]


def _window(text: str, size: int, overlap: int) -> list[str]:
    if overlap >= size:
        raise ValueError(f"overlap ({overlap}) must be < size ({size})")
    step = size - overlap
    return [text[i : i + size] for i in range(0, len(text), step)]
