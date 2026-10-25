"""Gate 3: review-workbench integrity. No parallel approval system, and no
bypass of the verification-evidence contract."""

import pytest
import uuid
from datetime import datetime

from src.pipeline.review import (APPROVED, VALIDATED_REQUIRES_REVIEW,
                                  ApprovalContractError, edit_question,
                                  set_status, QuestionReviewEvent)
from src.core.database import CanonicalQuestion, QuestionReviewStatus, utcnow


def _make_approvable(session, answer_evidence="ksol 11Comprehension p.3, key B",
                     explanation_evidence="worked solution checked against ksol p.3",
                     review_status="discovered", pre_verified=True):
    from src.core.database import SourceDocument, SourcePage, QuestionOccurrence
    q = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="maths", topic="arithmetic",
        question_type="mcq", question_text="What is 256 x 4?",
        correct_answer="B",
        options_json=[{"letter": "A", "text": "984"},
                      {"letter": "B", "text": "1024"}],
        explanation="Because 256 x 4 = 1024.", fingerprint=str(uuid.uuid4()))
    session.add(q)
    session.flush()
    # Source document + page surrogate, exactly as ingestion creates them.
    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="gate3-dbg",
        repo_url="https://github.com/SahirVhora/11plus-prep",
        source_path="gate3-dbg.pdf", file_sha256=str(uuid.uuid4()),
        file_size=0, file_type="pdf", commit_sha="d970c16614c95140",
        rights_status="licensed", rights_note="MIT License, Copyright (c) 2026 "
        "Sahir Vhora", ingestion_batch="gate3", first_seen_at=utcnow())
    session.add(doc)
    session.flush()
    page = SourcePage(
        id=str(uuid.uuid4()), document_id=doc.id, page_number=1,
        text_content="What is 256 x 4?", text_confidence=0.9, ocr_used=False,
        ocr_text="")
    session.add(page)
    session.flush()
    q.answer_status = "verified" if pre_verified else "missing"
    q.explanation_status = "verified" if pre_verified else "missing"
    q.answer_evidence = answer_evidence if pre_verified else ""
    q.explanation_evidence = explanation_evidence if pre_verified else ""
    session.flush()
    row = QuestionReviewStatus(
        question_id=q.id, status=review_status,
        source=f"gate3-dbg:{doc.id}", confidence=1.0)
    session.add(row)
    session.flush()
    # Every source record keeps its own occurrence. Reference documents are
    # ingested as whole files (no page extraction), so the occurrence carries
    # honest file-level provenance: a real document id + source record id, and
    # an empty page id. It never fabricates a page id from the document id.
    session.add(QuestionOccurrence(
        id=str(uuid.uuid4()), canonical_question_id=q.id,
        document_id=doc.id, page_id=page.id, question_number=q.id,
        extraction_run="gate3", extraction_version="adapter-0.2.0",
        extraction_confidence=1.0))
    session.flush()
    return q.id, session


def test_repeat_approve_is_idempotent_no_duplicate_event(session):
    """Foundation gate 3.6: two identical approval requests must not create
    two approvals and two audit events."""
    qid, s = _make_approvable(session)
    set_status(s, qid, "approved", reviewer="alice", reason="human review")
    assert s.query(QuestionReviewEvent).filter_by(
        question_id=qid, action="approve").count() == 1
    set_status(s, qid, "approved", reviewer="bob", reason="repetition attack")
    assert s.query(QuestionReviewEvent).filter_by(
        question_id=qid, action="approve").count() == 1
    assert s.query(QuestionReviewStatus).filter_by(question_id=qid).one().\
        status == APPROVED


def test_wrong_reviewer_or_reason_on_approved_is_idempotent(session):
    qid, s = _make_approvable(session)
    set_status(s, qid, "approved", reviewer="alice", reason="ok")
    set_status(s, qid, "approved", reviewer="mallory", reason="x")
    assert s.query(QuestionReviewEvent).filter_by(
        question_id=qid, action="approve").count() == 1
    assert s.query(QuestionReviewStatus).filter_by(
        question_id=qid).one().reviewer == "alice"


def test_repeated_reject_is_idempotent(session):
    qid, s = _make_approvable(session)
    set_status(s, qid, "rejected")
    assert s.query(QuestionReviewEvent).filter_by(
        question_id=qid, action="reject").count() == 1
    set_status(s, qid, "rejected")
    assert s.query(QuestionReviewEvent).filter_by(
        question_id=qid, action="reject").count() == 1
    assert s.query(QuestionReviewStatus).filter_by(
        question_id=qid).one().status == "rejected"

def test_edit_after_approval_downgrades_review_status(session):
    """A review edit that invalidates verification must pull an approved
    question back out of the student feed and record the audit trail."""
    qid, s = _make_approvable(session)
    set_status(s, qid, "approved", reviewer="alice", reason="approved")
    edit_question(s, qid, "alice", correct_answer="A")
    row = s.query(QuestionReviewStatus).filter_by(question_id=qid).one()
    assert row.status == VALIDATED_REQUIRES_REVIEW
    assert row.reason.startswith("reviewer edit invalidated")
    assert (s.query(QuestionReviewEvent)
            .filter_by(question_id=qid, action="status").count()) == 1
    assert (s.query(QuestionReviewEvent)
            .filter_by(question_id=qid, from_status=APPROVED,
                       to_status=VALIDATED_REQUIRES_REVIEW).count()) == 1
    q = s.query(CanonicalQuestion).filter_by(id=qid).one()
    assert q.answer_status == "candidate"


def test_edit_of_unapproved_does_not_downgrade(session):
    """A downgrade happens only when the review row is currently APPROVED.
    Editing a merely-discovered question still invalidates the verified answer
    (so it can never be served), but must NOT move the review row and must NOT
    emit a spurious status-change event."""
    qid, s = _make_approvable(session)
    row = s.query(QuestionReviewStatus).filter_by(question_id=qid).one()
    assert row.status == "discovered"
    edit_question(s, qid, "alice", correct_answer="A")
    row = s.query(QuestionReviewStatus).filter_by(question_id=qid).one()
    assert row.status == "discovered"              # no downgrade
    assert s.query(QuestionReviewEvent).filter_by(
        question_id=qid, from_status=APPROVED).count() == 0
    assert s.query(QuestionReviewEvent).filter_by(
        question_id=qid, action="verify_answer").count() == 0
    q = s.query(CanonicalQuestion).filter_by(id=qid).one()
    assert q.answer_status == "candidate"          # verification invalidated


def test_approve_blocked_until_verification_evidence_present(session):
    """No approval without recorded verification evidence on the answer and
    the explanation. Seed UNVERIFIED so the contract is genuinely exercised
    (a pre-verified seed would make the raises vacuous)."""
    qid, s = _make_approvable(session, pre_verified=False)
    with pytest.raises(ApprovalContractError):
        set_status(s, qid, "approved", reviewer="alice")
    from src.pipeline.review import verify_answer, verify_explanation
    verify_answer(s, qid, reviewer="alice",
                  evidence="ksol 11Comprehension p.3, key B")
    verify_explanation(s, qid, reviewer="alice",
                       note="worked solution checked against ksol p.3")
    set_status(s, qid, "approved", reviewer="alice")
    assert s.query(QuestionReviewStatus).filter_by(question_id=qid).one().status == \
        "approved"
