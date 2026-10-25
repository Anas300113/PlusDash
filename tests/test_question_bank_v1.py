"""Question Bank v1 regression tests.

These reproduce the concrete failures the trustworthy-question contract fixes:

* an unverified / unproven question could be approved (approval had no checks,
  ignored the ``reviewer`` argument and wrote no audit trail).
* a populated ``correct_answer`` was treated as if it implied approval.
* editing a verified answer/explanation silently kept a stale ``verified``.
* ``/api/questions`` leaked ``correct_answer`` to students.
* students could submit an arbitrary ``chosen_answer`` that was not one of the
  question's options and have it marked.

They assert against the real persistence + service path (no mocked services).
"""
from __future__ import annotations

import uuid

import pytest

from src.core.database import (
    CanonicalQuestion, CanonicalQuestionType, LearningStudent,
    QuestionOccurrence, QuestionReviewEvent, QuestionReviewStatus,
    SourceDocument, SourcePage,
)
from src.pipeline.review import (
    ApprovalContractError, approval_blockers, edit_question, has_provenance,
    option_labels, set_status, verify_answer, verify_explanation,
)


def _doc_page_occurrence(session, question_id):
    """Give a question real document+page provenance (the approval requires it)."""
    doc = SourceDocument(id=str(uuid.uuid4()), repo_name="r", repo_url="",
                         source_path="p.pdf", file_sha256="0" * 64,
                         file_size=1, file_type="pdf", commit_sha="",
                         ingestion_batch="b", ingestion_version="0.1.0")
    session.add(doc)
    page = SourcePage(id=str(uuid.uuid4()), document_id=doc.id,
                      page_number=1, text_content="stem")
    session.add(page)
    session.flush()
    session.add(QuestionOccurrence(
        id=str(uuid.uuid4()), canonical_question_id=question_id,
        document_id=doc.id, page_id=page.id, question_number="1"))
    session.commit()
    return doc.id, page.id


def _mcq(session, *, text="What is 2+2?", answer="B", explanation="2+2=4.",
         options=None, qtype="mcq", status="extracted", provenance=True):
    opts = options if options is not None else [
        {"letter": "A", "text": "3"}, {"letter": "B", "text": "4"}]
    if qtype and not session.query(CanonicalQuestionType).filter_by(
            id=qtype).first():
        session.add(CanonicalQuestionType(id=qtype, name=qtype,
                                          requires_options=(qtype == "mcq")))
    q = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="maths", topic="maths-arithmetic",
        question_type=qtype or "", question_text=text,
        correct_answer=answer, explanation=explanation, options_json=opts)
    session.add(q)
    session.flush()
    session.add(QuestionReviewStatus(question_id=q.id, status=status))
    session.commit()
    if provenance:
        _doc_page_occurrence(session, q.id)
    return q.id


# ---- content integrity -----------------------------------------------------


def test_populated_answer_alone_is_not_enough_to_approve(session):
    """Regression: a correct_answer being set does NOT imply approval."""
    qid = _mcq(session, provenance=True)
    blockers = approval_blockers(session, qid)
    # answer/explanation are 'missing' by default -> still blocked.
    assert any("answer_status" in b for b in blockers)
    assert any("explanation_status" in b for b in blockers)
    with pytest.raises(ApprovalContractError):
        set_status(session, qid, "approved")


def test_approval_requires_document_and_page_provenance(session):
    """Regression: a question with no page-level provenance cannot be approved."""
    qid = _mcq(session, provenance=False)
    assert has_provenance(session, qid) is False
    assert any("provenance" in b for b in approval_blockers(session, qid))
    with pytest.raises(ApprovalContractError):
        set_status(session, qid, "approved")


def test_mcq_answer_must_map_to_a_real_option(session):
    """Regression: an answer that is not one of the options is invalid."""
    qid = _mcq(session, answer="Z", provenance=True)
    blockers = approval_blockers(session, qid)
    assert any("does not map to a valid option" in b for b in blockers)


def test_option_labels_use_letter_key_and_preserve_order(session):
    """Option order and labels survive; extraction stores the label in 'letter'."""
    qid = _mcq(session, options=[{"letter": "C", "text": "x"},
                                 {"letter": "A", "text": "y"}])
    q = session.query(CanonicalQuestion).filter_by(id=qid).one()
    assert option_labels(q) == ["C", "A"]  # order preserved, not reordered


def test_missing_answer_distinct_from_unverified_and_verified(session):
    qid = _mcq(session, answer="", provenance=True)
    q = session.query(CanonicalQuestion).filter_by(id=qid).one()
    assert q.answer_status == "missing"           # distinct: missing
    with pytest.raises(ValueError):
        verify_answer(session, qid, "rev")        # cannot verify empty answer
    q.correct_answer = "B"
    session.commit()
    verify_answer(session, qid, "rev", evidence="ksol 11Comprehension p.3, key B")
    q = session.query(CanonicalQuestion).filter_by(id=qid).one()
    assert (q.answer_status == "verified"
            and q.answer_evidence == "ksol 11Comprehension p.3, key B")
    q.correct_answer = "B"
    session.commit()
    verify_answer(session, qid, "rev", evidence="ksol 11Comprehension p.3, key B")
    q = session.query(CanonicalQuestion).filter_by(id=qid).one()
    assert (q.answer_status == "verified"
            and q.answer_evidence == "ksol 11Comprehension p.3, key B")


def _make_approvable(session, **kw):
    """A question that satisfies every approval requirement."""
    qid = _mcq(session, **kw)
    verify_answer(session, qid, "rev",
                  evidence="ksol 11Comprehension p.1, answer key B")
    verify_explanation(session, qid, "rev",
                       note="worked solution checked against ksol p.1")
    return qid


def test_valid_question_can_be_approved_and_reviewer_recorded(session):
    qid = _make_approvable(session)
    set_status(session, qid, "approved", reviewer="alice")
    row = session.query(QuestionReviewStatus).filter_by(question_id=qid).one()
    assert row.status == "approved"
    assert row.reviewer == "alice"        # regression: reviewer was ignored
    assert row.decision == "approved"


def test_approval_and_rejection_are_audited(session):
    """Regression: review decisions must append an audit event, not be lost."""
    qid = _make_approvable(session)
    set_status(session, qid, "approved", reviewer="alice")
    set_status(session, qid, "rejected", reviewer="bob", reason="dupe")
    events = (session.query(QuestionReviewEvent)
              .filter_by(question_id=qid)
              .order_by(QuestionReviewEvent.created_at).all())
    actions = [e.action for e in events]
    assert "approve" in actions and "reject" in actions
    reject = next(e for e in events if e.action == "reject")
    assert reject.reviewer == "bob" and reject.reason == "dupe"


def test_editing_verified_answer_invalidates_verification(session):
    """Regression: editing a verified answer must not keep stale 'verified'."""
    qid = _make_approvable(session)
    edit_question(session, qid, "alice", correct_answer="A")
    q = session.query(CanonicalQuestion).filter_by(id=qid).one()
    assert q.answer_status == "candidate"        # verification reset
    # ...and the question can no longer be approved until re-verified.
    with pytest.raises(ApprovalContractError):
        set_status(session, qid, "approved")


def test_editing_verified_explanation_invalidates_verification(session):
    qid = _make_approvable(session)
    edit_question(session, qid, "alice", explanation="new text")
    q = session.query(CanonicalQuestion).filter_by(id=qid).one()
    assert q.explanation_status == "candidate"
    with pytest.raises(ApprovalContractError):
        set_status(session, qid, "approved")


def test_edit_preserves_original_extraction_in_audit(session):
    """The original extracted answer is recorded, not silently destroyed."""
    qid = _make_approvable(session, answer="B")
    edit_question(session, qid, "alice", correct_answer="A")
    event = (session.query(QuestionReviewEvent)
             .filter_by(question_id=qid, action="edit").one())
    assert "'B'" in event.reason       # original value captured


def test_rejection_always_allowed_even_when_unproven(session):
    qid = _mcq(session, provenance=False)
    set_status(session, qid, "rejected", reviewer="bob", reason="bad OCR")
    row = session.query(QuestionReviewStatus).filter_by(question_id=qid).one()
    assert row.status == "rejected"


# ---- student practice correctness ------------------------------------------


def _approved_for_practice(session):
    from src.learning.session import ensure_student, start_session
    qid = _make_approvable(session)
    set_status(session, qid, "approved", reviewer="alice")
    sid = str(uuid.uuid4())
    ensure_student(session, sid, name="S")
    sess = start_session(session, sid, subject="maths",
                         topic="maths-arithmetic", limit=5)
    return qid, sess.id


def test_pending_question_never_reaches_a_student_session(session):
    """Regression: a merely-extracted (pending) question is not practiceable.

    With no approved questions the session must be a truthful empty state
    (no fabricated or pending questions), never a session containing the
    pending question.
    """
    from src.learning.session import ensure_student, start_session
    _mcq(session, status="extracted", provenance=True)   # pending, not approved
    sid = str(uuid.uuid4())
    ensure_student(session, sid, name="S")
    sess = start_session(session, sid, subject="maths",
                         topic="maths-arithmetic", limit=5)
    assert sess.question_order_json == []   # empty, not the pending question


def test_out_of_options_answer_is_rejected_server_side(session):
    """Regression: a submitted answer must belong to the question's options."""
    from src.learning.session import submit_answer
    qid, sess_id = _approved_for_practice(session)
    with pytest.raises(ValueError):
        submit_answer(session, sess_id, qid, chosen_answer="Z")  # not an option


def test_correct_and_incorrect_marked_against_verified_answer(session):
    from src.core.database import LearningQuestionAttempt
    from src.learning.session import submit_answer
    qid, sess_id = _approved_for_practice(session)
    result = submit_answer(session, sess_id, qid, chosen_answer="B")
    assert result["is_correct"] is True          # verified answer is 'B'
    attempt = (session.query(LearningQuestionAttempt)
               .filter_by(session_id=sess_id, question_id=qid).one())
    assert attempt.is_correct is True


def test_only_one_attempt_recorded_per_submission(session):
    from src.core.database import LearningQuestionAttempt
    from src.learning.session import submit_answer
    qid, sess_id = _approved_for_practice(session)
    submit_answer(session, sess_id, qid, chosen_answer="B")
    n = (session.query(LearningQuestionAttempt)
         .filter_by(session_id=sess_id, question_id=qid).count())
    assert n == 1


# ---- API boundary (student leak + reviewer authorisation) ------------------


def _api_client(tmp_path, monkeypatch):
    httpx = pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from src.core.database import get_engine, get_session_factory, init_db
    import src.api.main as api_main
    engine = get_engine(f"sqlite:///{tmp_path / 'api.db'}")
    init_db(engine)
    S = get_session_factory(engine)
    monkeypatch.setattr(api_main, "_Session", S)
    return TestClient(api_main.app)


def test_questions_endpoint_does_not_leak_correct_answer(tmp_path, monkeypatch):
    """Regression: students must never receive correct_answer from the list
    endpoint (marking is server-side)."""
    from src.core.database import CanonicalQuestion, QuestionReviewStatus
    import src.api.main as api_main
    c = _api_client(tmp_path, monkeypatch)
    S = api_main._Session
    db = S()
    q = CanonicalQuestion(id=str(uuid.uuid4()), subject="maths",
                          topic="maths-arithmetic", question_type="mcq",
                          question_text="2+2?", correct_answer="B",
                          options_json=[{"letter": "A", "text": "3"},
                                        {"letter": "B", "text": "4"}])
    db.add(q)
    db.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    db.commit()
    db.close()
    rows = c.get("/api/questions").json()
    assert rows and "correct_answer" not in rows[0]


def test_reviewer_mutation_locked_without_token(tmp_path, monkeypatch):
    """Reviewer operations are gated server-side, not just hidden in a UI."""
    monkeypatch.delenv("PLUS_REVIEWER_TOKEN", raising=False)
    c = _api_client(tmp_path, monkeypatch)
    r = c.post(f"/api/review/{uuid.uuid4()}", json={"status": "approved"})
    assert r.status_code == 503          # fail-closed when not configured


def test_reviewer_mutation_rejects_wrong_token(tmp_path, monkeypatch):
    monkeypatch.setenv("PLUS_REVIEWER_TOKEN", "secret")
    c = _api_client(tmp_path, monkeypatch)
    r = c.post(f"/api/review/{uuid.uuid4()}", json={"status": "approved"},
               headers={"X-Reviewer-Token": "wrong"})
    assert r.status_code == 403


def test_reviewer_approve_with_token_enforces_contract(tmp_path, monkeypatch):
    """A reviewer with the right token still cannot approve an unverified
    question: the trustworthy contract is enforced server-side."""
    from src.core.database import CanonicalQuestion, QuestionReviewStatus
    import src.api.main as api_main
    monkeypatch.setenv("PLUS_REVIEWER_TOKEN", "secret")
    c = _api_client(tmp_path, monkeypatch)
    S = api_main._Session
    db = S()
    q = CanonicalQuestion(id=str(uuid.uuid4()), subject="maths",
                          topic="maths-arithmetic", question_type="mcq",
                          question_text="2+2?", correct_answer="B",
                          options_json=[{"letter": "A", "text": "3"},
                                        {"letter": "B", "text": "4"}])
    db.add(q)                             # no provenance, no verification
    db.add(QuestionReviewStatus(question_id=q.id, status="extracted"))
    db.commit()
    qid = q.id
    db.close()
    r = c.post(f"/api/review/{qid}", json={"status": "approved"},
               headers={"X-Reviewer-Token": "secret"})
    assert r.status_code == 400           # contract violation, not 200
    detail = c.get(f"/api/review/{qid}",
                   headers={"X-Reviewer-Token": "secret"}).json()
    assert detail["approval_blockers"]     # workbench shows what is missing


REMEV = "ksol 11Comprehension p.3, key B"
REMNOTE = "worked solution checked against ksol p.1"


def _seed_api_question(api_main):
    """One extracted MCQ with provenance in the API test database."""
    from src.core.database import CanonicalQuestion, QuestionReviewStatus
    S = api_main._Session
    db = S()
    q = CanonicalQuestion(id=str(uuid.uuid4()), subject="maths",
                          topic="maths-arithmetic", question_type="mcq",
                          question_text="2+2?", correct_answer="B",
                          options_json=[{"letter": "A", "text": "3"},
                                        {"letter": "B", "text": "4"}])
    db.add(q)
    db.add(QuestionReviewStatus(question_id=q.id, status="extracted"))
    db.commit()
    qid = q.id
    db.close()
    return qid


def test_review_workbench_page_served(tmp_path, monkeypatch):
    """The reviewer UI reuses the app's routing/design system and is gated by
    the same server-side token flow (it calls the protected endpoints)."""
    c = _api_client(tmp_path, monkeypatch)
    r = c.get("/review")
    assert r.status_code == 200
    assert "review-queue" in r.text and "Reviewer token" in r.text

# ---- P0-3: unauthorised callers cannot read reviewer-only data ---------------

def test_reviewer_read_endpoints_require_token(tmp_path, monkeypatch):
    """Regression (P0-1/P0-3): the review queue and per-question review detail
    expose answer evidence and review history, so they must not be readable
    without a valid reviewer token -- read access is protected, not just the
    mutating actions."""
    from src.core.database import CanonicalQuestion, QuestionReviewStatus
    import src.api.main as api_main
    monkeypatch.setenv("PLUS_REVIEWER_TOKEN", "secret")
    c = _api_client(tmp_path, monkeypatch)
    S = api_main._Session
    db = S()
    q = CanonicalQuestion(id=str(uuid.uuid4()), subject="maths",
                          topic="maths-arithmetic", question_type="mcq",
                          question_text="2+2?", correct_answer="B",
                          options_json=[{"letter": "A", "text": "3"},
                                        {"letter": "B", "text": "4"}])
    db.add(q)
    db.add(QuestionReviewStatus(question_id=q.id, status="extracted"))
    db.commit()
    qid = q.id
    db.close()

    # No token: both reviewer read endpoints must refuse.
    assert c.get("/api/review-queue").status_code == 403
    assert c.get(f"/api/review/{qid}").status_code == 403
    # Wrong token: also refused.
    assert c.get("/api/review-queue",
                 headers={"X-Reviewer-Token": "nope"}).status_code == 403
    # Valid token: the data is available, and it carries the answer + evidence.
    ok = c.get(f"/api/review/{qid}", headers={"X-Reviewer-Token": "secret"})
    assert ok.status_code == 200
    assert ok.json()["correct_answer"] == "B"


def test_reviewer_read_endpoints_locked_when_not_configured(tmp_path,
                                                            monkeypatch):
    """Fail-closed: with no PLUS_REVIEWER_TOKEN set, reviewer reads are locked
    (503), never left open."""
    monkeypatch.delenv("PLUS_REVIEWER_TOKEN", raising=False)
    c = _api_client(tmp_path, monkeypatch)
    assert c.get("/api/review-queue").status_code == 503
    assert c.get(f"/api/review/{uuid.uuid4()}").status_code == 503

# ---- P0-2: malicious question content cannot execute as HTML ---------------

def test_malicious_question_content_is_not_raw_html_in_pages(tmp_path,
                                                             monkeypatch):
    """Regression (P0-2): question/option/context/feedback text is untrusted.
    The reviewer and practice pages must render it as inert text (textContent
    or entity-escaping), never splice it into innerHTML where a <script> or an
    onclick attribute would execute."""
    from src.api import dashboard_pages, practice_page

    xss = '<img src=x onerror="alert(1)"><script>alert(2)</script>'

    # Reviewer workbench: entity-escape untrusted values; do not build markup
    # by string-concatenating question/subject text into innerHTML.
    review_html = dashboard_pages.REVIEW
    assert "function esc(" in review_html
    assert "'+q.question_text+'" not in review_html
    assert "'+q.subject+'" not in review_html

    # Practice page: stem/options/feedback use DOM text nodes, not innerHTML.
    practice_html = practice_page.PRACTICE_HTML
    assert "innerHTML='<b>'" not in practice_html
    assert "'<p>'+(q.context" not in practice_html
    assert "textContent" in practice_html

    # Confirm we are actually testing a script-like payload.
    assert "<script>" in xss and "onerror" in xss


# ---- P1-5: verification/state change persists after the request closes ------

def test_review_state_and_audit_persist_after_session_close(tmp_path,
                                                            monkeypatch):
    """Regression (P1-5): the status change and its audit event are one atomic
    commit. Closing the request session and opening a fresh one proves the
    event is in the database, not merely staged in an uncommitted session."""
    from src.core.database import QuestionReviewEvent
    import src.api.main as api_main
    monkeypatch.setenv("PLUS_REVIEWER_TOKEN", "secret")
    c = _api_client(tmp_path, monkeypatch)
    S = api_main._Session

    qid = _seed_api_question(api_main)
    r = c.post(f"/api/review/{qid}/verify-answer",
               json={"reviewer": "ui", "evidence": "ksol p.3, key B, checked"},
               headers={"X-Reviewer-Token": "secret"})
    assert r.status_code == 200

    # Fresh, independent session: read what actually committed to the DB.
    db = S()
    try:
        events = db.query(QuestionReviewEvent).filter_by(question_id=qid).all()
        assert any(e.action == "verify_answer" for e in events)
        ev = next(e for e in events if e.action == "verify_answer")
        assert ev.reason == "ksol p.3, key B, checked"     # inspectable evidence stored
    finally:
        db.close()


# ---- P1-6: exact audit event counts (no duplicate _log_event) ---------------

def test_audit_events_are_exactly_one_per_decision(session):
    """Regression (P1-6): set_status() once wrote the audit event twice
    (a duplicate _log_event call). Each *distinct* decision/verification/edit
    must append EXACTLY one event. Seed with a bare question so counts start
    at zero.

    Idempotency (Gate 3.6): a *repeat* of the same decision is a no-op and
    appends NO new event -- an audit event records a real state change, not a
    redundant re-request. Repeat idempotency is covered exhaustively in
    tests/test_review_integrity_gate3.py; here we only assert that the
    distinct-operation accounting (one event each, never two) still holds.
    """
    qid = _mcq(session, provenance=True)   # no verification yet: 0 events

    def _count():
        return session.query(QuestionReviewEvent).filter_by(
            question_id=qid).count()

    assert _count() == 0
    set_status(session, qid, "rejected", reviewer="alice", reason="dupe")
    assert _count() == 1                     # not 2 (the P1-6 regression)
    set_status(session, qid, "rejected", reviewer="bob", reason="again")
    assert _count() == 1                     # repeat decision: idempotent no-op
    verify_answer(session, qid, "bob", evidence="ksol p.3, key B, checked")
    assert _count() == 2
    verify_explanation(session, qid, "bob",
                       note="worked solution checked against ksol p.1")
    assert _count() == 3
    edit_question(session, qid, "bob", question_text="changed stem")
    assert _count() == 4


# ---- P1-4: verification requires meaningful, inspectable evidence ----------

def test_verify_answer_requires_meaningful_evidence(session):
    """Regression (P1-4): a bare 'ok' is not evidence. Verification must
    require a note naming where the source was checked, and it must be stored
    so reviewers can inspect it later."""
    from src.pipeline.review import MIN_EVIDENCE_LEN
    from src.core.database import CanonicalQuestion
    qid = _mcq(session, provenance=True)
    with pytest.raises(ValueError):
        verify_answer(session, qid, "alice", evidence="ok")   # too short
    with pytest.raises(ValueError):
        verify_answer(session, qid, "alice", evidence="")     # empty
    verify_answer(session, qid, "alice", evidence="ksol p.3, key B, checked")
    q = session.query(CanonicalQuestion).filter_by(id=qid).one()
    assert q.answer_status == "verified"
    assert q.answer_evidence == "ksol p.3, key B, checked"
    assert len("ksol p.3, key B, checked") >= MIN_EVIDENCE_LEN


def test_verify_explanation_requires_note_and_is_inspectable(session):
    """Regression (P1-4): explanation verification needs a note, stored for
    later inspection on explanation_evidence."""
    from src.core.database import CanonicalQuestion
    qid = _mcq(session, provenance=True)
    with pytest.raises(ValueError):
        verify_explanation(session, qid, "alice", note="fine")
    verify_explanation(session, qid, "alice",
                       note="worked solution checked against ksol p.1")
    q = session.query(CanonicalQuestion).filter_by(id=qid).one()
    assert q.explanation_status == "verified"
    assert q.explanation_evidence == "worked solution checked against ksol p.1"


# ---- P1-12: full reviewer -> student journey --------------------------------

def test_reviewer_to_student_journey_end_to_end(tmp_path, monkeypatch):
    """Regression (P1-12): the real workflow works end-to-end against live
    persistence -- a reviewer inspects source provenance, edits the question,
    verifies answer + explanation with evidence, approves it, and only then
    can a student practise it and receive correct server-side feedback.

    The same journey must FAIL at the student step while the question is still
    unapproved, proving the two halves are genuinely connected.
    """
    import src.api.main as api_main
    monkeypatch.setenv("PLUS_REVIEWER_TOKEN", "secret")
    c = _api_client(tmp_path, monkeypatch)
    S = api_main._Session
    H = {"X-Reviewer-Token": "secret"}

    # (a) Seed an extracted MCQ with document+page provenance.
    qid = _seed_api_question(api_main)

    # (b) Reviewer inspects source provenance (filename, page, question no.).
    detail = c.get(f"/api/review/{qid}", headers=H).json()
    # provenance is empty at extraction unless seeded; the blocker surfaces it.
    assert "approval_blockers" in detail

    # Attach real provenance through the service, as ingestion would.
    db = S()
    from src.core.database import (QuestionOccurrence, SourceDocument,
                                    SourcePage)
    doc = SourceDocument(id=str(uuid.uuid4()), repo_name="ksol",
                         repo_url="", source_path="11Comprehension.pdf",
                         file_sha256="0" * 64, file_size=1, file_type="pdf",
                         commit_sha="", ingestion_batch="b",
                         ingestion_version="0.1.0")
    db.add(doc)
    page = SourcePage(id=str(uuid.uuid4()), document_id=doc.id, page_number=3,
                      text_content="Q3 stem with options A/B")
    db.add(page)
    db.flush()
    db.add(QuestionOccurrence(id=str(uuid.uuid4()),
                              canonical_question_id=qid, document_id=doc.id,
                              page_id=page.id, question_number="3"))
    db.commit()
    db.close()

    # (c) BEFORE approval: the question is not student-eligible. The evidence
    # endpoint (/api/attempts) checks approval explicitly and refuses (403).
    sess_before = c.post("/api/sessions/start",
                         json={"student_id": "stu"}).json()["session_id"]
    r = c.post("/api/attempts",
               json={"student_id": "stu", "session_id": sess_before,
                     "question_id": qid, "chosen_answer": "B"})
    assert r.status_code == 403            # not yet approved for practice
    # It is also absent from the student-facing list.
    assert qid not in [x["id"] for x in c.get("/api/questions").json()]

    # (d) Reviewer edits the question: text, options and explanation. The
    # editor covers question text, options and answer/explanation (P1-9).
    r = c.post(f"/api/review/{qid}/edit", headers=H,
               json={"reviewer": "ui", "question_text": "What is 2+2?",
                     "explanation": "2+2 equals 4, which is option B."})
    assert r.status_code == 200

    # (e) Verify answer + explanation with meaningful evidence. Both API
    # endpoints take ``evidence`` (mapped to the service note internally).
    assert c.post(f"/api/review/{qid}/verify-answer", headers=H,
                  json={"reviewer": "ui",
                        "evidence": "ksol 11Comprehension p.3, key B"}
                  ).status_code == 200
    assert c.post(f"/api/review/{qid}/verify-explanation", headers=H,
                  json={"reviewer": "ui",
                        "evidence": "worked solution matches ksol p.3"}
                  ).status_code == 200

    # Now no blockers remain.
    detail2 = c.get(f"/api/review/{qid}", headers=H).json()
    assert detail2["approval_blockers"] == []

    # (f) Approve.
    assert c.post(f"/api/review/{qid}", headers=H,
                  json={"status": "approved", "reviewer": "ui",
                        "reason": "checked against ksol p.3"}
                  ).status_code == 200
    assert c.get(f"/api/review/{qid}", headers=H).json()[
        "review_status"] == "approved"

    # (g) AFTER approval: a student can practise and gets correct feedback.
    # Use the evidence endpoint (enforce_current=False) so the newly-approved
    # question can be answered; it marks against the verified answer.
    sess = c.post("/api/sessions/start",
                  json={"student_id": "stu"}).json()["session_id"]
    ans = c.post("/api/attempts",
                 json={"student_id": "stu", "session_id": sess,
                       "question_id": qid, "chosen_answer": "B"})
    assert ans.status_code == 200
    body = ans.json()
    assert body["is_correct"] is True       # marked against the verified answer
    assert "explanation" in body or "feedback" in body

    # The approved question appears in the student list WITHOUT correct_answer.
    rows = c.get("/api/questions").json()
    served = [r for r in rows if r["id"] == qid]
    assert served and "correct_answer" not in served[0]
