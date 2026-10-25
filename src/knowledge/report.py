"""Reproducible, read-only content-readiness report.

Every figure is derived from stored records (SourceDocument/Page/Asset,
QuestionOccurrence, CanonicalQuestion, QuestionReviewStatus, PipelineRun).
Nothing is inferred or fabricated. Two different numbers matter here and are
never conflated:

  * ``0``    -- the concept exists in the schema but no rows satisfy it;
  * ``null`` -- the schema has no field that can represent the concept, so the
                metric is genuinely *not measurable* from the DB.

The report performs no writes, approves nothing and never labels an answer
"verified" unless the stored review/validation evidence supports it.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy.orm import Session

from src.core.database import (
    CanonicalQuestion,
    PipelineRun,
    QuestionOccurrence,
    QuestionReviewStatus,
    SourceAsset,
    SourceDocument,
    SourcePage,
)

# Review statuses the pipeline/review code actually writes. Anything outside
# this set is reported verbatim under "other" so surprises are visible.
KNOWN_STATUSES = (
    "discovered", "extracted", "validation_required",
    "ai_reviewed", "approved", "rejected",
)


def _nonempty(value) -> bool:
    """True when a stored value carries real content (not None/empty/blank)."""
    if value is None:
        return False
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return bool(str(value).strip())


def _options_are_valid_ordered(options) -> bool:
    """Options valid & ordered: >=2 options, letters ascending A,B,C... from A
    with no gaps, and every option carrying non-empty text."""
    if not isinstance(options, list) or len(options) < 2:
        return False
    letters = []
    for o in options:
        if not isinstance(o, dict):
            return False
        letter = str(o.get("letter", "")).strip().upper()
        text = str(o.get("text", "")).strip()
        if not letter or not text:
            return False
        letters.append(letter)
    expected = [chr(ord("A") + i) for i in range(len(letters))]
    return letters == expected

def content_report(session: Session) -> dict:
    """Return the full readiness report as a plain, JSON-serialisable dict.

    Read-only: no writes, no approval, no inference.
    """
    # ---- source / page / asset ----
    docs = session.query(SourceDocument).all()
    pages = session.query(SourcePage).all()
    assets = session.query(SourceAsset).all()

    docs_by_type = Counter(d.file_type or "unknown" for d in docs)
    total_bytes = sum(int(d.file_size or 0) for d in docs)

    # duplicate content hashes across documents (same bytes, multiple rows)
    sha_counts = Counter(d.file_sha256 for d in docs if d.file_sha256)
    duplicate_sha_groups = sum(1 for c in sha_counts.values() if c > 1)
    duplicate_extra_docs = sum(c - 1 for c in sha_counts.values() if c > 1)

    pages_with_native = sum(1 for p in pages if _nonempty(p.text_content))
    pages_ocr = sum(1 for p in pages if p.ocr_used)
    pages_ocr_text = sum(1 for p in pages if _nonempty(p.ocr_text))
    pages_empty = sum(
        1 for p in pages
        if not _nonempty(p.text_content) and not _nonempty(p.ocr_text))
    # OCR coverage over pages that actually needed it (no native text)
    pages_needing_ocr = sum(1 for p in pages if not _nonempty(p.text_content))
    ocr_coverage = (
        round(pages_ocr / pages_needing_ocr, 3)
        if pages_needing_ocr else None)

    # ---- question occurrences ----
    occurrences = session.query(QuestionOccurrence).all()
    occ_total = len(occurrences)
    occ_linked = sum(1 for o in occurrences if o.canonical_question_id)
    occ_unpromoted = occ_total - occ_linked
    occ_with_answer_evidence = sum(
        1 for o in occurrences if _nonempty(o.linked_answer))
    occ_mcq_candidates = sum(
        1 for o in occurrences
        if isinstance(o.options_json, list) and len(o.options_json) >= 2)

    # ---- canonical questions ----
    canonicals = session.query(CanonicalQuestion).all()
    cq_total = len(canonicals)
    cq_with_options = [q for q in canonicals if _nonempty(q.options_json)]
    cq_valid_ordered = [
        q for q in canonicals if _options_are_valid_ordered(q.options_json)]
    options_len_dist = Counter(
        len(q.options_json) for q in cq_with_options
        if isinstance(q.options_json, list))

    # occurrences back-reference per canonical -> provenance + missing provenance
    occ_by_canonical = Counter(
        o.canonical_question_id for o in occurrences if o.canonical_question_id)
    cq_with_provenance = sum(
        1 for q in canonicals if occ_by_canonical.get(q.id, 0) > 0)
    cq_missing_provenance = cq_total - cq_with_provenance

    # duplicate canonical questions by fingerprint (identical content)
    fp_counts = Counter(q.fingerprint for q in canonicals if q.fingerprint)
    duplicate_fp_groups = sum(1 for c in fp_counts.values() if c > 1)
    duplicate_cq_extra = sum(c - 1 for c in fp_counts.values() if c > 1)
    cq_no_fingerprint = sum(1 for q in canonicals if not q.fingerprint)

    cq_with_answer = sum(1 for q in canonicals if _nonempty(q.correct_answer))
    cq_with_explanation = sum(
        1 for q in canonicals if _nonempty(q.explanation))
    cq_with_worked = sum(1 for q in canonicals if _nonempty(q.worked_solution))
    cq_with_hint = sum(1 for q in canonicals if _nonempty(q.hint))

    # ---- review status ----
    statuses = session.query(QuestionReviewStatus).all()
    status_counts = Counter(s.status for s in statuses)
    canonical_ids = {q.id for q in canonicals}
    status_rows_without_canonical = sum(
        1 for s in statuses if s.question_id not in canonical_ids)

    approved = status_counts.get("approved", 0)
    rejected = status_counts.get("rejected", 0)
    pending = sum(
        status_counts.get(s, 0)
        for s in ("extracted", "validation_required", "ai_reviewed", "discovered"))
    other_statuses = {
        s: c for s, c in status_counts.items() if s not in KNOWN_STATUSES}

    approved_ids = {s.question_id for s in statuses if s.status == "approved"}
    approved_mcq_usable = sum(
        1 for q in canonicals
        if q.id in approved_ids
        and _options_are_valid_ordered(q.options_json)
        and _nonempty(q.correct_answer))
    approved_with_answer = sum(
        1 for q in canonicals
        if q.id in approved_ids and _nonempty(q.correct_answer))

    # ---- coverage ----
    by_subject = Counter(q.subject or "(unspecified)" for q in canonicals)
    by_topic = Counter(
        f"{q.subject or '?'}/{q.topic or '(unspecified)'}" for q in canonicals)
    by_type = Counter(q.question_type or "(unspecified)" for q in canonicals)
    occ_canon_to_doc = {
        o.canonical_question_id: o.document_id
        for o in occurrences if o.canonical_question_id}
    doc_id_to_path = {d.id: d.source_path for d in docs}
    by_source_doc = Counter()
    for q in canonicals:
        did = occ_canon_to_doc.get(q.id)
        by_source_doc[doc_id_to_path.get(did, "(no source)")] += 1

    # ---- pipeline runs / ingestion errors ----
    runs = session.query(PipelineRun).all()
    run_status = Counter(r.status for r in runs)
    failed_runs = [
        {"id": r.id, "error": r.error_message}
        for r in runs if r.status == "failed"]

    return {
        "source": {
            "documents": len(docs),
            "documents_by_type": dict(docs_by_type),
            "total_bytes": total_bytes,
            "duplicate_sha_groups": duplicate_sha_groups,
            "duplicate_extra_documents": duplicate_extra_docs,
        },
        "pages": {
            "total": len(pages),
            "with_native_text": pages_with_native,
            "ocr_used": pages_ocr,
            "with_ocr_text": pages_ocr_text,
            "empty": pages_empty,
            "needing_ocr": pages_needing_ocr,
            "ocr_coverage": ocr_coverage,
        },
        "assets": {"total": len(assets)},
        "question_occurrences": {
            "total": occ_total,
            "promoted_to_canonical": occ_linked,
            "unpromoted": occ_unpromoted,
            "with_answer_evidence": occ_with_answer_evidence,
            "mcq_candidates": occ_mcq_candidates,
        },
        "canonical_questions": {
            "total": cq_total,
            "with_options": len(cq_with_options),
            "valid_ordered_options": len(cq_valid_ordered),
            "options_count_distribution": dict(sorted(options_len_dist.items())),
            "with_provenance": cq_with_provenance,
            "missing_provenance": cq_missing_provenance,
            "duplicate_fingerprint_groups": duplicate_fp_groups,
            "duplicate_extra_questions": duplicate_cq_extra,
            "without_fingerprint": cq_no_fingerprint,
            "with_answer": cq_with_answer,
            "with_explanation": cq_with_explanation,
            "with_worked_solution": cq_with_worked,
            "with_hint": cq_with_hint,
        },
        "review": {
            "approved": approved,
            "pending": pending,
            "rejected": rejected,
            "other_statuses": other_statuses,
            "status_rows_without_canonical": status_rows_without_canonical,
            "approved_with_answer": approved_with_answer,
            "approved_usable_mcq": approved_mcq_usable,
        },
        "coverage": {
            "by_subject": dict(by_subject.most_common()),
            "by_topic": dict(by_topic.most_common()),
            "by_question_type": dict(by_type.most_common()),
            "by_source_document": dict(by_source_doc.most_common()),
        },
        "pipeline_runs": {
            "by_status": dict(run_status),
            "failed": failed_runs,
        },
    }
