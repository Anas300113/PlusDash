"""Content hashing utilities. Deterministic, idempotent."""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: str | Path, chunk_size: int = 65536) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def content_fingerprint(*parts: str) -> str:
    """Stable fingerprint for a tuple of normalized strings."""
    joined = "\u241f".join(p.strip().lower() for p in parts)
    return sha256_text(joined)
