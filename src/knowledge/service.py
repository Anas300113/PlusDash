"""Build a KnowledgeIndex from already-ingested SourcePage rows.

This is the bridge between the (frozen) ingestion foundation and the retrieval
layer. It reads text directly from the database -- SourcePage.text_content,
which already includes OCR text merged in by the pipeline -- and never re-parses
source files. Streaming: pages are iterated with a bounded query; each page's
text is chunked and released before the next.

Incremental + idempotent:
  * ``build_index`` chunks only the requested pages; because chunk ids are
    content-stable and the index de-duplicates by chunk_id, re-running against
    unchanged pages yields an identical index and no duplicate chunks.
  * Pass ``only_document_ids`` to index a subset incrementally.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from src.core.database import SourceDocument, SourcePage
from src.knowledge.chunk import chunk_text
from src.knowledge.retriever import KnowledgeIndex


def _key_document_ids(
    session: Session,
    *,
    only_document_ids: list[str] | None = None,
    batch_size: int = 200,
) -> set[str]:
    """Document ids classified as answer keys by a page-level key *heading*.

    Document-level policy (foundation gate): if ANY page of a document opens
    with an explicit answer/marking-scheme heading, the WHOLE document is an
    answer key -- later pages of a key document repeat bare answer lines
    without the heading and must never be indexed. The heading classifier is
    the pipeline's authoritative :func:`text_is_answer_key_heading`; it is
    applied to both ``text_content`` and ``ocr_text`` so scanned key documents
    are caught too (fail closed). Only the document id set is retained --
    never page content.

    Filename-classified documents need no scan (the filename is shared by all
    pages) and are filtered separately in :func:`iter_page_chunks`.
    """
    from src.pipeline.link import text_is_answer_key_heading

    from src.core.logging import get_logger
    log = get_logger("knowledge.service")

    key_docs: set[str] = set()
    last_id = ""
    while True:
        q = (session.query(SourcePage.id, SourcePage.document_id,
                           SourcePage.text_content, SourcePage.ocr_text)
             .order_by(SourcePage.id))
        if last_id:
            q = q.filter(SourcePage.id > last_id)
        if only_document_ids is not None:
            q = q.filter(SourcePage.document_id.in_(only_document_ids))
        rows = q.limit(batch_size).all()
        if not rows:
            break
        for pid, doc_id, text_content, ocr_text in rows:
            last_id = pid
            if doc_id in key_docs:
                continue
            if text_is_answer_key_heading(text_content or "") or \
                    text_is_answer_key_heading(ocr_text or ""):
                key_docs.add(doc_id)
                # Review record: which document was classified. Filename only,
                # never answer-key contents.
                doc = session.query(SourceDocument).filter_by(
                    id=doc_id).first()
                name = (doc.source_path if doc else doc_id)
                log.info(
                    "answer-key document classified by page heading; "
                    "excluded from retrieval index: %s", name)
        if len(rows) < batch_size:
            break
    return key_docs


def iter_page_chunks(
    session: Session,
    *,
    only_document_ids: list[str] | None = None,
    chunk_size: int = 700,
    overlap: int = 80,
    batch_size: int = 200,
):
    """Yield Chunk objects page-by-page (bounded memory).

    Uses keyset pagination on SourcePage.id so memory stays bounded regardless
    of corpus size.

    Answer-key protection (P0) is document-level: a document is excluded in
    full when its filename is key-marked OR any of its pages opens with an
    answer/marking-scheme heading. Later pages of a key document repeat bare
    answer lines without the heading, so page-level filtering alone leaks them.
    """
    # Document-level classification pass (heading evidence). Filename evidence
    # needs no pass -- every page shares the document's filename.
    key_docs = _key_document_ids(
        session, only_document_ids=only_document_ids, batch_size=batch_size)
    logged_skip: set[str] = set()
    from src.pipeline.link import filename_is_answer_key

    from src.core.logging import get_logger
    log = get_logger("knowledge.service")
    last_id = ""
    while True:
        q = session.query(SourcePage).order_by(SourcePage.id)
        if last_id:
            q = q.filter(SourcePage.id > last_id)
        if only_document_ids is not None:
            q = q.filter(SourcePage.document_id.in_(only_document_ids))
        rows = q.limit(batch_size).all()
        if not rows:
            break
        # cache doc filenames for this batch
        doc_ids = {r.document_id for r in rows}
        docs = {
            d.id: d for d in session.query(SourceDocument)
            .filter(SourceDocument.id.in_(doc_ids)).all()
        }
        for page in rows:
            doc = docs.get(page.document_id)
            filename = doc.source_path if doc else page.document_id
            text = (page.text_content or "").strip()
            if not text:
                # scanned pages carry their readable text in ocr_text
                text = (page.ocr_text or "").strip()
            if not text:
                continue  # never fabricate content for empty pages
            # human-facing filename (basename); keep full path in meta
            fname = filename.replace("\\", "/").rsplit("/", 1)[-1] or filename
            # Answer-key protection (P0): document-level exclusion. The whole
            # document is skipped when it is filename-classified or its id was
            # flagged by the heading scan above. Nothing from a classified
            # answer document enters the persisted index, so it cannot leak
            # via the search endpoint, the explain grounding path, or a raw
            # index file.
            if page.document_id in key_docs or filename_is_answer_key(fname):
                if page.document_id not in logged_skip:
                    logged_skip.add(page.document_id)
                    log.info(
                        "answer-key document excluded from retrieval index: %s",
                        fname)
                last_id = page.id
                continue
            yield from chunk_text(
                text,
                filename=fname,
                page_number=page.page_number,
                page_id=page.id,
                document_id=page.document_id,
                chunk_size=chunk_size,
                overlap=overlap,
                meta={"ocr_used": bool(page.ocr_used), "source_path": filename},
            )
            last_id = page.id
        if len(rows) < batch_size:
            break


def build_index(
    session: Session,
    *,
    only_document_ids: list[str] | None = None,
    chunk_size: int = 700,
    overlap: int = 80,
) -> KnowledgeIndex:
    """Build and return a KnowledgeIndex from ingested pages."""
    chunks = list(iter_page_chunks(
        session,
        only_document_ids=only_document_ids,
        chunk_size=chunk_size,
        overlap=overlap,
    ))
    return KnowledgeIndex().build(chunks)


def index_to_path(path: str | Path, index: KnowledgeIndex) -> Path:
    p = Path(path)
    index.save(p)
    return p
