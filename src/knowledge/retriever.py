"""TF-IDF retrieval index over source-page chunks.

Low-cost and deterministic: scikit-learn TfidfVectorizer + cosine similarity,
persisted with joblib. No model downloads, no external services, works fully
offline. The vectorizer is always fitted with an explicit fixed vocabulary so
that queries are projected into the exact same feature space across restarts.

Every hit is returned with its source chunk, hence a verifiable filename,
page number and excerpt. An empty vocabulary (no indexed content) or a query
that shares no terms yields NO hits -> retrieval never invents evidence; this
is the "insufficient evidence" behaviour tested explicitly.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .chunk import Chunk


def _is_answer_key_chunk(filename: str, text: str) -> bool:
    """True when a chunk carries explicit answer-key evidence.

    Defense-in-depth filter for retrieval: reuses the SAME authoritative
    classifier as the ingestion pipeline (via src.pipeline.link) so the
    knowledge engine can never disagree with answer-linking about what a key
    is. Imported lazily to keep the retrieval layer import-clean and to avoid
    a knowledge -> pipeline import cycle at module load.
    """
    from src.pipeline.link import (
        filename_is_answer_key, text_is_answer_key_heading,
    )
    return (filename_is_answer_key(filename)
            or text_is_answer_key_heading(text))


class KnowledgeIndex:
    """Persistable TF-IDF index over a set of chunks."""

    def __init__(self) -> None:
        self._vectorizer = None  # sklearn TfidfVectorizer (lazy import)
        self._matrix = None      # sparse csr (n_chunks, n_features)
        self._chunks: list[Chunk] = []
        self._vocabulary: list[str] = []

    # ---- construction ------------------------------------------------
    @property
    def size(self) -> int:
        return len(self._chunks)

    @property
    def vocabulary(self) -> list[str]:
        return list(self._vocabulary)

    @property
    def chunks(self) -> list[Chunk]:
        return list(self._chunks)

    def build(self, chunks: list[Chunk]) -> None:
        """Fit the vectorizer on the given chunks and store them.

        Idempotent by content: identical chunk sets -> identical vocabulary and
        matrix. Duplicate chunk_ids are collapsed (last wins) so re-indexing the
        same pages twice does not double the index.
        """
        from sklearn.feature_extraction.text import TfidfVectorizer

        # de-duplicate by stable content id, preserving order
        by_id: dict[str, Chunk] = {}
        for c in chunks:
            by_id[c.chunk_id] = c
        ordered = list(by_id.values())
        self._chunks = ordered
        texts = [c.text for c in ordered]

        vec = TfidfVectorizer(
            lowercase=True,
            token_pattern=r"(?u)\b\w\w+\b",
            sublinear_tf=True,
            norm="l2",
        )
        if texts:
            self._matrix = vec.fit_transform(texts)
        else:
            # fit on a tiny dummy so the vocabulary is well-defined (empty)
            self._matrix = vec.fit_transform(["__empty__"])
        self._vectorizer = vec
        self._vocabulary = list(vec.vocabulary_.keys())
        return self

    # ---- persistence -------------------------------------------------
    def save(self, path: str | Path) -> None:
        """Persist index to disk (vectorizer + matrix + chunk metadata)."""
        import joblib

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": 1,
            "vectorizer": self._vectorizer,
            "matrix": self._matrix,
            "vocabulary": self._vocabulary,
            "chunks": [c.__dict__ for c in self._chunks],
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        joblib.dump(payload, tmp)
        tmp.replace(path)  # atomic-ish on same filesystem

    @classmethod
    def load(cls, path: str | Path) -> "KnowledgeIndex":
        """Reload a persisted index. Raises FileNotFoundError if absent."""
        import joblib

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(str(path))
        payload = joblib.load(path)
        obj = cls()
        obj._vectorizer = payload["vectorizer"]
        obj._matrix = payload["matrix"]
        obj._vocabulary = payload.get("vocabulary", [])
        obj._chunks = [Chunk(**c) for c in payload["chunks"]]
        return obj

    # ---- retrieval ---------------------------------------------------
    def search(self, query: str, top_k: int = 5,
               min_score: float = 0.0) -> list[dict]:
        """Return the top-k chunks most similar to ``query``.

        Each result dict contains: score, chunk_id, filename, page_number,
        excerpt, text and provenance ids. Returns [] when the query shares no
        vocabulary with the index (insufficient evidence) -- never guesses.
        """
        if self._vectorizer is None or self._matrix is None or not self._chunks:
            return []
        q = (query or "").strip()
        if not q:
            return []
        from sklearn.metrics.pairwise import cosine_similarity

        qv = self._vectorizer.transform([q])
        # If the query has zero overlap with the fitted vocabulary, transform
        # yields an all-zero row -> all scores 0 -> treat as no evidence.
        if qv.nnz == 0:
            return []
        scores = cosine_similarity(qv, self._matrix).ravel()
        order = np.argsort(-scores)
        results: list[dict] = []
        for i in order:
            score = float(scores[i])
            if score < min_score:
                continue
            if score <= 0.0:
                continue  # no lexical evidence
            c = self._chunks[int(i)]
            # Answer-key protection (P0, defense-in-depth): the primary guard
            # excludes keys at build time, but a previously-built index on disk
            # may still contain answer-key chunks until it is rebuilt. Filter
            # here too, reusing the SAME authoritative classifier the pipeline
            # uses, so no path can surface key content.
            if _is_answer_key_chunk(c.filename, c.text):
                continue
            results.append({
                "score": round(score, 6),
                "chunk_id": c.chunk_id,
                "filename": c.filename,
                "page_number": c.page_number,
                "excerpt": c.excerpt(),
                "text": c.text,
                "document_id": c.document_id,
                "page_id": c.page_id,
            })
            if len(results) >= top_k:
                break
        return results
