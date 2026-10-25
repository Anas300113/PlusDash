# ADR-001 — Knowledge/retrieval engine for 11+ Study (reuse, don't rebuild)

Date: 2026-10-10
Status: Accepted
Branch: feat/knowledge-engine

## Context

We need a document-grounded knowledge/retrieval layer that can discover the
existing 11+ corpus, extract text and page boundaries, persist content +
provenance, index it, and return a *verifiable* citation (filename, page,
excerpt) for a query — restart-safe and idempotent.

Upstream candidate inspected: **HKUDS/DeepTutor** (41k★, Apache-2.0,
Data Intelligence Lab @ HKU; https://github.com/HKUDS/DeepTutor).

## Decision

Reuse the existing Plus ingestion foundation. Add a small, local,
low-cost retrieval engine (`src/knowledge/`). Reject DeepTutor as a
dependency and reject a heavy vector stack.

## Evidence

### DeepTutor — inspected
- It is a full multi-agent tutoring *application* (web UI, CLI, sub-agent
  connectors for Claude Code/Codex/Grok/etc., co-writer, notebook). Not a
  focused ingestion/RAG library.
- License Apache-2.0 (compatible, but the code is an app, not a component).
- Adopting it would mean embedding a second application + its runtime
  (agent backends, LLM providers, web stack) — the opposite of the prompt's
  "do not introduce an unnecessary second application / add unrelated
  features".
- **Verdict: REJECT as a dependency.** (Apache-2.0 is fine for reference/
  inspiration only.)

### Plus ingestion foundation — reused as-is (frozen)
Already proven end-to-end on the real 21-file corpus (previous milestone):
- `SourceDocument` / `SourcePage` / `SourceAsset` with content hashes,
  page boundaries, OCR text merged into pages, image assets.
- Idempotent, checkpointed, resumable pipeline; provenance intact.
- These are the *source of truth* for retrieval. Retrieval reads
  `SourcePage.text_content` (already includes merged OCR text) and never
  re-parses source files or fabricates content.

### Vector stack — rejected for now
Environment check (measured, not assumed):
- `numpy` ✓, `scikit-learn` 1.9.1 ✓, `joblib` 1.6.0 ✓.
- `sentence_transformers` ✗, `faiss` ✗, `lightrag` ✗, `qdrant` ✗,
  `chromadb` ✗, `openai` ✗.
- Disk free: ~6.9 GB.
A semantic-embedding + vector-DB stack would require model downloads and
new runtime deps whose footprint/resource needs we would be *assuming*. A
local TF-IDF + cosine retriever (scikit-learn) needs **no downloads**, is
deterministic, fully offline, and is sufficient to prove the vertical slice
and produce verifiable citations. Embeddings/vector DB remain a possible
future upgrade behind the same `KnowledgeIndex` interface (no call-site
changes).

## Architecture

- `src/knowledge/chunk.py` — pure, deterministic, sentence-aware chunking;
  stable content-hash `chunk_id` (idempotent); carries
  `(filename, page_number, page_id, document_id, char span)`.
- `src/knowledge/retriever.py` — `KnowledgeIndex`: TF-IDF vectors + cosine
  top-k; `.save/.load` (joblib) for restart-safety; returns
  `insufficient_evidence` (empty) rather than guessing; `repair()` to
  reconcile index vs DB.
- `src/knowledge/service.py` — streaming, keyset-paginated bridge from
  `SourcePage` rows to the index (bounded memory; skips empty pages;
  never fabricates).
- `scripts/knowledge_cli.py` — `index | search | inventory | repair`.
- `src/api/main.py` — read-only `POST /api/knowledge/search` (503 if no
  index; returns evidence or `insufficient_evidence`).

## Guardrails honored

- Retrieval only returns evidence; it never promotes/approves questions or
  answers (structured extraction + validation + approval pipeline untouched).
- Additive only: no migrations touching frozen tables; new index artifact is
  git-ignored (`data/knowledge/`, `*.joblib`).
- Bounded/streaming; never loads the whole corpus into memory.
