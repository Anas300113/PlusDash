"""Deterministic chunking of source-page text.

Chunks keep a hard link back to (document filename, page_number) so retrieval
can always produce verifiable provenance. Chunking is character-window based
with sentence-aware boundaries and configurable size/overlap. It is pure
(strings in -> chunk dicts out) so it is trivially unit-testable and does not
touch the database or filesystem.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Chunk:
    """A retrievable passage with full provenance.

    ``chunk_id`` is a stable content hash of (filename, page, index, text) so
    re-indexing identical content yields identical ids -> idempotent index.
    """
    chunk_id: str
    text: str
    filename: str
    page_number: int
    page_id: str
    document_id: str
    index: int  # chunk ordinal within the page
    char_start: int
    char_end: int
    meta: dict = field(default_factory=dict)

    def excerpt(self, limit: int = 240) -> str:
        t = " ".join(self.text.split())
        return t if len(t) <= limit else t[: limit - 1].rstrip() + "\u2026"


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("\u241f".join(parts).encode("utf-8")).hexdigest()[:24]


def _sentence_boundaries(text: str) -> list[int]:
    """Return candidate split offsets at sentence ends, plus whitespace runs."""
    bounds: list[int] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in ".!?\u3002\uff01\uff1f":
            # include trailing quotes/parens and following spaces
            j = i + 1
            while j < n and text[j] in "\"')]} \t":
                j += 1
            bounds.append(j)
            i = j
        else:
            i += 1
    if not bounds:
        # fall back to newlines / spaces as soft boundaries
        bounds = [k for k, c in enumerate(text) if c == "\n"]
    return bounds


def chunk_text(
    text: str,
    *,
    filename: str,
    page_number: int,
    page_id: str,
    document_id: str,
    chunk_size: int = 700,
    overlap: int = 80,
    meta: dict | None = None,
) -> list[Chunk]:
    """Split ``text`` into provenance-preserving chunks.

    - Windows are ``chunk_size`` characters with ``overlap`` character overlap.
    - Prefers to end each window at a sentence boundary when one falls inside
      the last ~20% of the window; otherwise it cuts at ``chunk_size``.
    - Whitespace-only / empty pages yield no chunks (never fabricate content).
    """
    meta = meta or {}
    norm = text.strip()
    if not norm:
        return []
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")

    bounds = set(_sentence_boundaries(norm))
    chunks: list[Chunk] = []
    start = 0
    idx = 0
    n = len(norm)
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            # try to snap to a sentence boundary in the tail region
            soft_lo = start + int(chunk_size * 0.8)
            snap = None
            for b in sorted(bounds):
                if soft_lo <= b <= end:
                    snap = b
            if snap is not None and snap > start + overlap:
                end = snap
        seg = norm[start:end].strip()
        if seg:
            cid = _stable_id(filename, str(page_number), str(idx), seg)
            chunks.append(
                Chunk(
                    chunk_id=cid,
                    text=seg,
                    filename=filename,
                    page_number=page_number,
                    page_id=page_id,
                    document_id=document_id,
                    index=idx,
                    char_start=start,
                    char_end=start + len(seg),
                    meta=dict(meta),
                )
            )
            idx += 1
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks
