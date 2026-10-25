"""Trustworthy review/approval service.

Single authority for moving a canonical question toward the student-facing
bank. It enforces the Question Bank v1 contract:

* A question is NEVER approved merely because ``correct_answer`` is set.
* Approval requires: usable text, sufficient page-level provenance,
  question-type specific validity (MCQ: ordered, distinguishable options
  whose label maps unambiguously to the verified answer), a **verified**
  answer, and a **verified** explanation.
* Every status change and every edit is appended to ``QuestionReviewEvent``
  (reviewer, UTC timestamp, decision, reason). The review trail is never
  overwritten.

Editing a verified answer or explanation resets that field to ``candidate``
so a later edit can never silently keep a stale verification.

Reviewer identity model
-----------------------
The review trail records a ``reviewer`` identity. The application has no user
identity provider, so this value is the *shared development credential*
(its token hash and name), not an individual human. It is stored verbatim in
``CanonicalQuestion.answer_evidence``/``question_review_events.reviewer`` purely
as an audit reference. It must never be interpreted as evidence of who a
student is or of any individual's verified identity. Reviewer mutations are
gated server-side by ``require_reviewer()`` (P0-1 / P1-7).
so a later edit can never silently keep a stale verification.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.core.database import (
    CanonicalQuestion, QuestionOccurrence, QuestionReviewEvent,
    QuestionReviewStatus, SourceDocument, SourcePage,
)

REVIEWABLE = ("discovered", "extracted", "ai_reviewed", "validation_required")
APPROVED = "approved"
REJECTED = "rejected"
VALIDATED_REQUIRES_REVIEW = "validation_required"
VERIFIED = "verified"
CANDIDATE = "candidate"
MISSING = "missing"

# Minimum inspectable content for a verification note/evidence string.
# A note must name WHERE the reviewer checked the source (e.g. "ksol p.3,
# key C"), not just "ok". 16 chars is deliberately low: it blocks empty and
# trivial notes ("yes", "ok") without demanding a rigid evidence schema.
MIN_EVIDENCE_LEN = 16


class ApprovalContractError(ValueError):
    """Raised when a requested approval violates the trustworthy-question
    contract (unmet requirements). Distinct from a missing-row ValueError so
    callers can map it to a 400 rather than a 404."""
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _log_event(session: Session, question_id: str, action: str,
               reviewer: str, from_status: str = "", to_status: str = "",
               reason: str = "") -> None:
    session.add(QuestionReviewEvent(
        id=str(uuid.uuid4()), question_id=question_id, action=action,
        reviewer=reviewer, from_status=from_status, to_status=to_status,
        reason=reason, created_at=_now()))


def review_queue(session: Session, limit: int = 50):
    return (
        session.query(CanonicalQuestion, QuestionReviewStatus)
        .join(QuestionReviewStatus,
              QuestionReviewStatus.question_id == CanonicalQuestion.id)
        .filter(QuestionReviewStatus.status.in_(REVIEWABLE))
        .order_by(CanonicalQuestion.id)
        .limit(limit).all()
    )


# ---- contract checks -------------------------------------------------------


def _occurrences(session: Session, question_id: str):
    return (session.query(QuestionOccurrence)
            .filter_by(canonical_question_id=question_id).all())


def provenance_level(session: Session, question_id: str) -> str:
    """Resolve how well a question's source location can actually be trusted.

    Returns one of:

    * ``"page"`` -- an occurrence pins a document AND a page id that resolves
      to a real ``SourcePage`` row belonging to that same document. This is
      page-level provenance from the PDF/OCR pipeline.
    * ``"file"`` -- no resolvable page, but an occurrence pins a real
      ``SourceDocument`` AND a non-empty source record id (``question_number``).
      This is honest file-and-record provenance for structured JSON banks,
      which are ingested per file and deliberately carry no page rows.
    * ``"none"`` -- no occurrence offers either. A populated ``page_id`` that
      does NOT resolve to a real ``SourcePage`` (e.g. the historical
      fabrication that stored the *document* id in the page column) never
      counts as provenance.

    Ids are only trusted when the row they reference actually exists; being
    populated is never sufficient.
    """
    occs = _occurrences(session, question_id)
    doc_ids = {o.document_id for o in occs if o.document_id}
    page_ids = {o.page_id for o in occs if o.page_id}
    real_page_doc: dict[str, str] = {}
    if page_ids:
        for p in session.query(SourcePage).filter(SourcePage.id.in_(page_ids)):
            real_page_doc[p.id] = p.document_id
    real_docs: set[str] = set()
    if doc_ids:
        real_docs = {d.id for d in session.query(SourceDocument)
                     .filter(SourceDocument.id.in_(doc_ids))}
    # Page-level: a page id that resolves to a real page of the same document.
    for o in occs:
        if (o.page_id and o.page_id in real_page_doc
                and real_page_doc[o.page_id] == o.document_id
                and o.document_id in real_docs):
            return "page"
    # File-level: a real document plus a non-empty source record id.
    for o in occs:
        if (o.document_id and o.document_id in real_docs
                and (o.question_number or "").strip()):
            return "file"
    return "none"


def has_provenance(session: Session, question_id: str) -> bool:
    """True when a question has verifiable page- or file-level provenance.

    A populated id is not enough: the referenced ``SourcePage`` /
    ``SourceDocument`` row must actually exist.
    """
    return provenance_level(session, question_id) != "none"


def _looks_mcq(question: CanonicalQuestion) -> bool:
    qt = (question.question_type or "").lower()
    return ("mcq" in qt or "multiple" in qt or "choice" in qt
            or bool(question.options_json))


def option_labels(question: CanonicalQuestion) -> list[str]:
    opts = question.options_json or []
    labels = []
    for opt in opts:
        if isinstance(opt, dict):
            # Extraction stores the label under "letter"; accept "label"/"key"
            # too so adapters with other keys still resolve.
            labels.append(str(opt.get("letter") or opt.get("label")
                               or opt.get("key") or "").strip())
        else:
            labels.append(str(opt).strip())
    return [l for l in labels if l]


def approval_blockers(session: Session, question_id: str) -> list[str]:
    """Unmet requirements that block approval. Empty list == eligible.

    A question is NEVER approved merely because ``correct_answer`` is set.
    """
    q = session.query(CanonicalQuestion).filter_by(id=question_id).first()
    if q is None:
        raise ValueError(f"no canonical question {question_id}")
    blockers: list[str] = []
    if not (q.question_text or "").strip():
        blockers.append("question_text is empty")
    if not has_provenance(session, question_id):
        blockers.append(
            "no occurrence with verifiable page- or file-level provenance")
    if _looks_mcq(q):
        labels = option_labels(q)
        option_items = q.options_json or []
        option_texts = [
            (str(o.get("text", "") if isinstance(o, dict) else o)).strip()
            for o in option_items]
        if len(option_items) < 2:
            blockers.append("mcq requires at least two options")
        if len(labels) < 2:
            blockers.append("mcq requires at least two labelled options")
        if len(labels) != len(option_items):
            # option_labels() drops empties, so a length mismatch means some
            # option has a missing/blank label (or a duplicate-shaped entry).
            blockers.append("mcq option has empty label")
        if len(set(l.upper() for l in labels)) != len(labels):
            blockers.append("mcq option labels are not distinguishable")
        if len(option_texts) != len(set(t.lower() for t in option_texts)):
            blockers.append("mcq option texts are not distinguishable")
        if any(not t for t in option_texts):
            blockers.append("mcq option has empty text")
        ans = (q.correct_answer or "").strip()
        if not ans:
            blockers.append("mcq requires a correct_answer")
        elif labels and ans.upper() not in {l.upper() for l in labels}:
            blockers.append("correct_answer does not map to a valid option")
    if q.answer_status != VERIFIED:
        blockers.append(f"answer_status is '{q.answer_status}', not verified")
    if q.explanation_status != VERIFIED:
        blockers.append(
            f"explanation_status is '{q.explanation_status}', not verified")
    return blockers


# ---- mutation --------------------------------------------------------------


def set_status(session: Session, question_id: str, status: str,
               reviewer: str = "cli", reason: str = "") -> None:
    row = session.query(QuestionReviewStatus).filter_by(
        question_id=question_id).first()
    if row is None:
        raise ValueError(f"no review row for {question_id}")
    if status == APPROVED:
        blockers = approval_blockers(session, question_id)
        if blockers:
            raise ApprovalContractError(
                "cannot approve; unmet requirements: " + "; ".join(blockers))
    if row.status == status:
        # Repeat request with the same decision: idempotent no-op. Re-logging
        # would create duplicate audit events for a single real decision
        # (foundation gate: "repeat requests do not create duplicate
        # approvals or audit events").
        return
    from_status = row.status
    row.status = status
    row.reviewer = reviewer
    row.decision = status
    row.reason = reason
    row.updated_at = _now()
    action = "approve" if status == APPROVED else (
        "reject" if status == REJECTED else "status")
    _log_event(session, question_id, action, reviewer,
               from_status=from_status, to_status=status, reason=reason)
    # Atomic: state change + audit event persist in ONE commit. Splitting them
    # across commits would leave the DB half-written on failure (status moved
    # but no audit, or vice versa). P1-5.
    session.commit()


def verify_answer(session: Session, question_id: str, reviewer: str,
                  evidence: str = "") -> None:
    """Record that a human verified the answer against source evidence.

    ``evidence`` is required and must be meaningful (P1-4): it must name
    WHERE the answer was checked (e.g. "ksol p.3, key C"), not just "ok".
    The evidence is stored verbatim on ``answer_evidence`` so reviewers can
    inspect it later, and copied into the audit event reason.
    """
    q = session.query(CanonicalQuestion).filter_by(id=question_id).first()
    if q is None:
        raise ValueError(f"no canonical question {question_id}")
    if not (q.correct_answer or "").strip():
        raise ValueError(f"question {question_id} has no answer to verify")
    if len((evidence or "").strip()) < MIN_EVIDENCE_LEN:
        raise ValueError(
            "answer evidence is too short; record where you checked the "
            "source (e.g. filename p.N, key X) before marking verified")
    prev = q.answer_status
    q.answer_status = VERIFIED
    q.answer_evidence = evidence.strip()
    q.updated_at = _now()
    _log_event(session, question_id, "verify_answer", reviewer,
               from_status=prev, to_status=VERIFIED,
               reason=evidence.strip())
    # Atomic (P1-5): status flip + evidence + audit event in ONE commit.
    session.commit()


def verify_explanation(session: Session, question_id: str, reviewer: str,
                       note: str = "") -> None:
    """Record that a human verified the explanation supports the answer.

    ``note`` is required and must be meaningful (P1-4): it must record what
    was checked (e.g. "worked solution matches options, ksol p.3"). Stored
    verbatim on ``explanation_evidence`` so reviewers can inspect it later.
    """
    q = session.query(CanonicalQuestion).filter_by(id=question_id).first()
    if q is None:
        raise ValueError(f"no canonical question {question_id}")
    if not (q.explanation or "").strip():
        raise ValueError(f"question {question_id} has no explanation to verify")
    if len(note.strip()) < MIN_EVIDENCE_LEN:
        raise ValueError(
            "verification note is too short; record where you checked the "
            "source (e.g. filename p.N) before marking verified")
    prev_expl = q.explanation_status
    q.explanation_status = VERIFIED
    q.explanation_evidence = note.strip()
    q.updated_at = _now()
    _log_event(session, question_id, "verify_explanation", reviewer,
               from_status=prev_expl, to_status=VERIFIED,
               reason=note.strip())
    # Atomic (P1-5): status flip + evidence + audit event in ONE commit.
    session.commit()


def _downgrade_review_if_approved(session: Session, q: CanonicalQuestion,
                                  reviewer: str) -> None:
    """Verification was invalidated by an edit while the question was already
    approved. Re-deposit it at ``validation_required`` so the student feed
    can never serve a stale ``verified`` answer (Gate 3: no bypass)."""
    from src.core.database import QuestionReviewStatus

    row = session.query(QuestionReviewStatus).filter_by(
        question_id=q.id).first()
    if row is not None and row.status == APPROVED:
        row.status = VALIDATED_REQUIRES_REVIEW
        row.reviewer = reviewer
        row.decision = VALIDATED_REQUIRES_REVIEW
        row.reason = "reviewer edit invalidated the verified answer"
        row.updated_at = _now()
        _log_event(session, q.id, "status", reviewer,
                   from_status=APPROVED,
                   to_status=VALIDATED_REQUIRES_REVIEW,
                   reason=row.reason)


def edit_question(session: Session, question_id: str, reviewer: str,
                  question_text: str | None = None,
                  correct_answer: str | None = None,
                  explanation: str | None = None,
                  options_json: list | None = None) -> None:
    """Apply a reviewer edit while preserving the original extraction.

    Editing a verified answer or explanation (or the MCQ option set an
    answer maps to) RESETS that field to ``candidate`` so a stale
    ``verified`` can never survive an edit. The original pipeline-extracted
    text is preserved in the audit ``reason`` so nothing is destroyed.
    """
    q = session.query(CanonicalQuestion).filter_by(id=question_id).first()
    if q is None:
        raise ValueError(f"no canonical question {question_id}")
    notes: list[str] = []
    if question_text is not None and question_text != q.question_text:
        notes.append(f"question_text was {q.question_text!r}")
        q.question_text = question_text
    if correct_answer is not None and correct_answer != q.correct_answer:
        notes.append(f"correct_answer was {q.correct_answer!r}")
        q.correct_answer = correct_answer
        if q.answer_status == VERIFIED:
            q.answer_status = CANDIDATE  # edit invalidates verification
            _downgrade_review_if_approved(session, q, reviewer)
    if explanation is not None and explanation != q.explanation:
        notes.append(f"explanation was {q.explanation!r}")
        q.explanation = explanation
        if q.explanation_status == VERIFIED:
            q.explanation_status = CANDIDATE
            _downgrade_review_if_approved(session, q, reviewer)
    if options_json is not None and options_json != q.options_json:
        notes.append(f"options_json was {q.options_json!r}")
        q.options_json = options_json
        if q.answer_status == VERIFIED:
            q.answer_status = CANDIDATE  # option->answer mapping may be stale
            _downgrade_review_if_approved(session, q, reviewer)
    q.updated_at = _now()
    # Atomic (P1-5): edited fields + audit event in ONE commit. The original
    # code committed, logged, then committed again, leaving a partial edit
    # visible if the second commit failed.
    _log_event(session, question_id, "edit", reviewer,
               reason="; ".join(notes) if notes else "no-op")
    session.commit()


# ---- Gate 5: educational correctness ---------------------------------------

def gate5_educational_correctness_check(session: Session) -> dict:
    """Gate 5: educational-correctness readiness for the question corpus.

    The ingested corpus is *safe* (nothing unverified reaches students -- see
    Gate 4 / ``tests/test_unapproved_exposure.py``) but it is *not*
    human-reviewed at scale. Before any question can be served to students,
    every imported question must still carry ``validation_required`` (or
    another non-approved review status) and zero questions may be approved.
    Bulk approval is explicitly forbidden; each question needs individual
    human sign-off.

    Returns a report dict:
      total_questions        -- all canonical questions
      approved_questions     -- questions with status == \"approved\"
      pending_review_questions -- questions awaiting review
      gate5_safe             -- True when approved_questions == 0
      per_source             -- breakdown by source repo (licence/attribution)
    """
    from sqlalchemy import func

    from src.core.database import (  # noqa: PLC0415
        CanonicalQuestion, QuestionReviewStatus, SourceDocument,
    )

    total_questions = (
        session.query(func.count(CanonicalQuestion.id)).scalar() or 0)
    approved_questions = (
        session.query(func.count(QuestionReviewStatus.question_id))
        .filter(QuestionReviewStatus.status == "approved")
        .scalar() or 0)
    pending_review_questions = (
        session.query(func.count(QuestionReviewStatus.question_id))
        .filter(QuestionReviewStatus.status != "approved")
        .scalar() or 0)

    per_source: dict[str, dict] = {}
    rows = (
        session.query(
            SourceDocument.repo_name,
            func.count(CanonicalQuestion.id).label("q_count"),
        )
        .outerjoin(QuestionOccurrence,
                   QuestionOccurrence.document_id == SourceDocument.id)
        .outerjoin(CanonicalQuestion,
                   CanonicalQuestion.id == QuestionOccurrence.canonical_question_id)
        .group_by(SourceDocument.repo_name)
        .all())
    for repo, q_count in rows:
        per_source[repo or "unknown"] = {"questions": q_count or 0}

    gate5_safe = approved_questions == 0

    return {
        "total_questions": total_questions,
        "approved_questions": approved_questions,
        "pending_review_questions": pending_review_questions,
        "gate5_safe": gate5_safe,
        "per_source": per_source,
    }
