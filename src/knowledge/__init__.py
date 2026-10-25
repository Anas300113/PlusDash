"""Knowledge engine: chunk, index and retrieve source-page passages.

This module builds a retrieval layer directly on top of the existing,
already-ingested ingestion foundation (SourceDocument / SourcePage). It never
re-parses files and never fabricates content: every returned passage carries a
verifiable filename, page number and excerpt, and is traceable back to the
SourcePage row it came from.

Design goals:
  * Low-cost, deterministic and offline: TF-IDF (scikit-learn) + joblib, no
    model downloads, no external services.
  * Restart-stable: the index is persisted to disk and reloaded verbatim.
  * Idempotent: re-indexing unchanged pages produces no duplicate chunks.
  * Streaming/bounded: pages are processed one at a time; the whole corpus is
    never loaded into memory at once.
"""
