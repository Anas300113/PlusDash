"""FastAPI application: approved questions, practice sessions,
review queue. Only APPROVED questions are student-facing.

Learning-layer endpoints (session state machine, statistics, review items,
educational loop) live in src/learning/*; the routes here are thin wrappers
that translate HTTP into those functions and never re-implement their rules.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from fastapi.responses import HTMLResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from src.api.dashboard_pages import HOME, LEARN, MOCKS, PARENT, PROGRESS, REVIEW
from src.api.practice_page import PRACTICE_HTML

from src.core.database import (
    CanonicalQuestion, QuestionOccurrence, QuestionReviewStatus,
    SourceDocument, SourcePage, get_engine, get_session_factory,
)

DB_URL = (os.environ.get("DATABASE_URL") or os.environ.get(
    "PLUS_DATABASE_URL", "sqlite:///./elevenplus.db"))
_engine = get_engine(DB_URL)
_Session = get_session_factory(_engine)


def get_db():
    db = _Session()
    try:
        yield db
    finally:
        db.close()


# Reviewer authorisation boundary.
# -------------------------------
# The application has no user/identity model yet (student routes take a bare
# ``student_id``). Reviewer operations change persisted state and can publish
# a question to students, so they MUST be gated server-side, not just hidden in
# the UI. The smallest correct boundary is a shared reviewer token supplied in
# the ``X-Reviewer-Token`` header and compared (constant-time) against the
# ``PLUS_REVIEWER_TOKEN`` environment variable.
#
# Fail-closed: when the token is not configured, reviewer MUTATIONS are locked
# (503) rather than left open. Read-only reviewer endpoints stay available so
# the workbench can render. This is a thin boundary pending a real auth system;
# it is never the sole protection for student data (answers are never sent to
# students regardless of this guard).
REVIEWER_TOKEN_ENV = "PLUS_REVIEWER_TOKEN"


def _reviewer_credential_name(token: str) -> str:
    """Stable audit label for the shared reviewer credential (P1-7).

    The app has no per-human identity provider, so the review trail cannot
    honestly record "who reviewed this" as an individual. It records
    ``reviewer:<sha256(token)[:12]>`` -- which token was used -- so the audit
    stays truthful without leaking the secret itself.
    """
    import hashlib
    return "reviewer:" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def require_reviewer(x_reviewer_token: str | None = Header(default=None)) -> str:
    import hmac
    import os as _os
    expected = _os.environ.get(REVIEWER_TOKEN_ENV, "")
    if not expected:
        raise HTTPException(
            503, "reviewer operations are locked: set PLUS_REVIEWER_TOKEN")
    if not x_reviewer_token or not hmac.compare_digest(
            x_reviewer_token, expected):
        raise HTTPException(403, "invalid or missing reviewer token")
    return _reviewer_credential_name(x_reviewer_token)


# Legacy student ownership boundary (P1-13).
# ------------------------------------------
# Historical endpoints accept bare ``student_id`` values and do not resolve a
# verified principal. In real-data mode (the default), their route guards fail
# closed with HTTP 503 before reading or mutating a learner's record. Do not
# expose these legacy routes as an authenticated substitute for `/api/me`.
#
# The account-backed Plus11 router is separate: `/api/me/*` derives the learner
# from a verified Manus HS256 bearer token (signature, expiry, and project claim
# checked in `src/api/manus_identity.py`) and never uses client-supplied IDs for
# ownership. `X-Student-Id` is not an authentication mechanism. The optional
# `PLUS_REQUIRE_STUDENT_IDENTITY` comparison is only a defensive check for
# isolated/demo use when real-data mode has explicitly been disabled.
STUDENT_IDENTITY_ENV = "PLUS_REQUIRE_STUDENT_IDENTITY"


def student_identity_required() -> bool:
    return os.environ.get(STUDENT_IDENTITY_ENV, "").strip().lower() in (
        "1", "true", "yes", "on")


# The legacy ID-only routes remain locked by default. Account-backed Plus11
# callers use /api/me, whose identity is derived from a verified Manus JWT.
REAL_STUDENT_DATA_ENV = "PLUS_REAL_STUDENT_DATA"


def real_student_data_mode() -> bool:
    return os.environ.get(REAL_STUDENT_DATA_ENV, "1").strip().lower() not in (
        "0", "false", "no", "off")


def _refuse_if_real_data(resource: str) -> None:
    """Fail closed on student-scoped routes when the deployment declares it
    holds real student data and no server-verified identity exists yet."""
    if real_student_data_mode():
        raise HTTPException(
            503,
            f"student data for {resource} is locked: this deployment holds "
            "real student data but no server-verified student identity is "
            "configured. Set a signed session/bearer identity (see "
            "docs/ADR-002-student-identity.md) before exposing student data.")


def _enforce_student_id(claimed: str | None, owner: str, resource: str) -> None:
    """Fail closed in real-data mode; otherwise optionally compare a legacy
    caller-supplied ID (which is not a verified identity)."""
    _refuse_if_real_data(resource)
    if not student_identity_required():
        return
    if not claimed:
        raise HTTPException(
            401, f"missing student identity header X-Student-Id for {resource}")
    if claimed != owner:
        raise HTTPException(403, f"student identity does not own {resource}")


def _enforce_session_owner(db: Session, session_id: str,
                           claimed: str | None) -> None:
    """Enforce that ``claimed`` owns the session ``session_id`` (owner is read
    from the stored session, never from the URL)."""
    _refuse_if_real_data("this session")
    if not student_identity_required():
        return
    from src.core.database import LearningStudySession
    owner = (db.query(LearningStudySession.student_id)
             .filter_by(id=session_id).scalar())
    if owner is None:
        # No such session: let the underlying handler return its 404.
        return
    _enforce_student_id(claimed, owner, "this session")


app = FastAPI(title="11+ Platform API", version="0.1.0")
from src.api.plus11 import router as plus11_router
app.include_router(plus11_router)


class AnswerIn(BaseModel):
    student_id: str
    session_id: str
    question_id: str
    chosen_answer: str
    time_taken_ms: int = 0
    action: str = "answer"
    hint_used: bool = False


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/ready")
def readiness():
    """Read-only database/schema probe for the supervisor's prepared schema."""
    try:
        with _engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        required = {
            "learning_students", "learning_study_sessions",
            "canonical_questions", "question_review_status",
        }
        if not required.issubset(set(inspect(_engine).get_table_names())):
            raise HTTPException(503, "database schema is not ready")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "database is not ready") from None


@app.get("/", response_class=HTMLResponse)
def home():
    return HOME


@app.get("/learn", response_class=HTMLResponse)
def learn():
    return LEARN


@app.get("/mocks", response_class=HTMLResponse)
def mocks():
    return MOCKS


@app.get("/progress", response_class=HTMLResponse)
def progress_page():
    return PROGRESS


@app.get("/parent", response_class=HTMLResponse)
def parent_page():
    return PARENT


@app.get("/practice", response_class=HTMLResponse)
def practice_page():
    return PRACTICE_HTML


@app.get("/review", response_class=HTMLResponse)
def review_page():
    return REVIEW


@app.get("/api/questions")
def list_questions(subject: str | None = None, topic: str | None = None,
                   limit: int = 20, db: Session = Depends(get_db)):
    q = (db.query(CanonicalQuestion)
         .join(QuestionReviewStatus,
               QuestionReviewStatus.question_id == CanonicalQuestion.id)
         .filter(QuestionReviewStatus.status == "approved"))
    if subject:
        q = q.filter(CanonicalQuestion.subject == subject)
    if topic:
        q = q.filter(CanonicalQuestion.topic == topic)
    rows = q.limit(limit).all()
    # Student-facing: NEVER expose correct_answer here. Marking happens
    # server-side via the session answer route, which reads the verified
    # answer from the stored record. Exposing it here would let a client
    # trivially cheat.
    return [{"id": r.id, "subject": r.subject, "topic": r.topic,
             "question_type": r.question_type, "question_text": r.question_text,
             "options": r.options_json, "context": r.context} for r in rows]


@app.post("/api/sessions")
def create_session(student_id: str, session_type: str = "practice",
                   subject: str | None = None, topic: str | None = None,
                   limit: int = 20, planned_duration_seconds: int = 0,
                   from_review_queue: bool = False, seed: int = 42,
                   db: Session = Depends(get_db),
                   x_student_id: str | None = Header(default=None)):
    """Start a session through the explicit state machine.

    Backwards compatible: with only ``student_id`` supplied it behaves as
    before, but the question order is now frozen so the session can be resumed.
    """
    # Ownership (P1): a caller must not create sessions attributed to another
    # student by substituting the identifier.
    _enforce_student_id(x_student_id, student_id, "session start")
    from src.learning.session import start_session
    try:
        s = start_session(
            db, student_id, session_type=session_type, subject=subject,
            topic=topic, limit=limit,
            planned_duration_seconds=planned_duration_seconds, seed=seed,
            from_review_queue=from_review_queue)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"session_id": s.id, "state": s.state,
            "session_type": s.session_type,
            "total": len(s.question_order)}


class SessionStartIn(BaseModel):
    student_id: str
    session_type: str = "practice"
    subject: str | None = None
    topic: str | None = None
    question_ids: list[str] = []
    limit: int = 20
    ordering: str = "canonical"
    seed: int = 42
    planned_duration_seconds: int = 0
    goals: dict = {}
    from_review_queue: bool = False


@app.post("/api/sessions/start")
def start_session_route(payload: SessionStartIn, db: Session = Depends(get_db),
                        x_student_id: str | None = Header(default=None)):
    """Body-based session start (frozen order, goals, review-queue support)."""
    # Ownership (P1): a caller must not create sessions attributed to another
    # student by substituting the identifier.
    _enforce_student_id(x_student_id, payload.student_id, "session start")
    from src.learning.session import start_session
    try:
        s = start_session(
            db, payload.student_id, session_type=payload.session_type,
            question_ids=payload.question_ids, subject=payload.subject,
            topic=payload.topic, limit=payload.limit,
            ordering=payload.ordering, seed=payload.seed,
            planned_duration_seconds=payload.planned_duration_seconds,
            goals=payload.goals, from_review_queue=payload.from_review_queue)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"session_id": s.id, "state": s.state,
            "total": len(s.question_order),
            "question_order": s.question_order}


@app.get("/api/sessions/{session_id}")
def get_session_state(session_id: str, x_student_id: str | None = Header(default=None),
                      db: Session = Depends(get_db)):
    """Resume payload: current question, index, progress, goals, activities."""
    _enforce_session_owner(db, session_id, x_student_id)
    from src.learning.session import session_state
    try:
        return session_state(db, session_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


class SubmitIn(BaseModel):
    question_id: str = ""
    chosen_answer: str = ""
    time_taken_ms: int = 0
    hint_used: bool = False
    action: str = "answer"  # answer | skip | retry


@app.post("/api/sessions/{session_id}/answer")
def session_answer(session_id: str, payload: SubmitIn,
                   x_student_id: str | None = Header(default=None),
                   db: Session = Depends(get_db)):
    """ASSESS + EXPLAIN: record evidence, return feedback, schedule review."""
    _enforce_session_owner(db, session_id, x_student_id)
    from src.learning.session import submit_answer
    try:
        # Retries are re-attempts on a previously-answered question, so they
        # are not required to be the session's "current" question.
        enforce = payload.action != "retry"
        return submit_answer(db, session_id, payload.question_id,
                             payload.chosen_answer, payload.time_taken_ms,
                             hint_used=payload.hint_used, action=payload.action,
                             enforce_current=enforce)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/sessions/{session_id}/skip")
def session_skip(session_id: str, payload: SubmitIn | None = None,
                 x_student_id: str | None = Header(default=None),
                 db: Session = Depends(get_db)):
    """SKIP: stored as evidence, creates a review item, never counts as wrong."""
    _enforce_session_owner(db, session_id, x_student_id)
    from src.learning.session import skip_current
    question_id = (payload.question_id if payload and payload.question_id
                   else None)
    try:
        return skip_current(db, session_id,
                            payload.time_taken_ms if payload else 0,
                            question_id=question_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/sessions/{session_id}/retry")
def session_retry(session_id: str, x_student_id: str | None = Header(default=None),
                  db: Session = Depends(get_db)):
    """RETRY: allow a re-answer of the current question (hint returned)."""
    _enforce_session_owner(db, session_id, x_student_id)
    from src.learning.session import retry_current
    try:
        return retry_current(db, session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/sessions/{session_id}/complete")
def session_complete(session_id: str, x_student_id: str | None = Header(default=None),
                     db: Session = Depends(get_db)):
    """COMPLETE: results view, mastery refresh, new recommendations."""
    _enforce_session_owner(db, session_id, x_student_id)
    from src.learning.session import complete_session
    try:
        return complete_session(db, session_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@app.post("/api/sessions/{session_id}/abandon")
def session_abandon(session_id: str, x_student_id: str | None = Header(default=None),
                    db: Session = Depends(get_db)):
    """ABANDON: close the session, keep all attempt evidence."""
    _enforce_session_owner(db, session_id, x_student_id)
    from src.learning.session import abandon_session
    try:
        return abandon_session(db, session_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@app.get("/api/sessions/{session_id}/results")
def session_results_route(session_id: str, x_student_id: str | None = Header(default=None),
                          db: Session = Depends(get_db)):
    _enforce_session_owner(db, session_id, x_student_id)
    from src.learning.session import session_results
    try:
        return session_results(db, session_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@app.post("/api/attempts")
def record_attempt(payload: AnswerIn, x_student_id: str | None = Header(default=None),
                   db: Session = Depends(get_db)):
    """Legacy evidence endpoint, kept for compatibility.

    Prefer ``POST /api/sessions/{id}/answer``. This path records evidence for
    a question that may not be the session's frozen current question, so it
    runs the same logic with ``enforce_current=False``. It never advances the
    session cursor and it still refuses non-approved questions.
    """
    _enforce_student_id(x_student_id, payload.student_id, "these attempts")
    from src.learning.session import get_session, submit_answer
    q = db.query(CanonicalQuestion).filter_by(id=payload.question_id).first()
    if q is None:
        raise HTTPException(404, "question not found")
    status = db.query(QuestionReviewStatus).filter_by(
        question_id=q.id).first()
    if status is None or status.status != "approved":
        raise HTTPException(403, "question is not approved for practice")
    try:
        session = get_session(db, payload.session_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    result = submit_answer(
        db, session.id, q.id, payload.chosen_answer,
        time_taken_ms=payload.time_taken_ms, hint_used=payload.hint_used,
        action=payload.action, enforce_current=False)
    return {"is_correct": result["is_correct"],
            "explanation": q.explanation,
            "feedback": result["feedback"],
            "review_item_id": result["review_item_id"]}


@app.get("/api/review-queue")
def review_queue(limit: int = 50, db: Session = Depends(get_db),
                 _token: str = Depends(require_reviewer)):
    from src.pipeline.review import review_queue as rq
    rows = rq(db, limit)
    return [{"id": q.id, "subject": q.subject, "topic": q.topic,
             "text": q.question_text[:300], "status": s.status} for q, s in rows]


class ReviewIn(BaseModel):
    status: str  # approved | rejected
    reason: str = ""


@app.post("/api/review/{question_id}")
def review(question_id: str, payload: ReviewIn, db: Session = Depends(get_db),
           _token: str = Depends(require_reviewer)):
    if payload.status not in ("approved", "rejected"):
        raise HTTPException(400, "status must be approved|rejected")
    from src.pipeline.review import ApprovalContractError, set_status
    try:
        set_status(db, question_id, payload.status, _token, payload.reason)
    except ApprovalContractError as exc:
        # The question exists but does not meet the trustworthy contract.
        raise HTTPException(400, str(exc))
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"ok": True, "status": payload.status}


@app.get("/api/review/{question_id}")
def review_detail(question_id: str, db: Session = Depends(get_db),
                  _token: str = Depends(require_reviewer)):
    """Reviewer workbench: the stored question, its provenance, verification
    states, extraction warnings and the precise unmet approval requirements."""
    from src.pipeline.review import (
        approval_blockers, has_provenance, provenance_level,
    )
    from src.core.database import QuestionOccurrence, QuestionReviewEvent
    q = db.query(CanonicalQuestion).filter_by(id=question_id).first()
    if q is None:
        raise HTTPException(404, "question not found")
    status = db.query(QuestionReviewStatus).filter_by(
        question_id=question_id).first()
    occs = db.query(QuestionOccurrence).filter_by(
        canonical_question_id=question_id).all()
    _files = {d.id: (d.source_path or "") for d in
              db.query(SourceDocument.source_path, SourceDocument.id).all()}
    _pages = {}
    for _d in db.query(SourcePage.page_number, SourcePage.text_content,
                       SourcePage.id).all():
        _pages[_d.id] = (_d.page_number or 0,
                         (_d.text_content or "").strip())
    provenance = []
    for o in occs:
        _pn, _pt = _pages.get(o.page_id, (0, ""))
        provenance.append({
            "document_id": o.document_id,
            "filename": _files.get(o.document_id, ""),
            "page_number": _pn,
            "page_excerpt": _pt[:240] + "...",
            "question_number": o.question_number or "",
            "linked_answer": o.linked_answer or "",
            "extraction_confidence": o.extraction_confidence,
        })
    events = db.query(QuestionReviewEvent).filter_by(
        question_id=question_id).order_by(QuestionReviewEvent.created_at).all()
    return {
        "id": q.id, "subject": q.subject, "topic": q.topic,
        "question_type": q.question_type, "question_text": q.question_text,
        "options": q.options_json, "context": q.context,
        "correct_answer": q.correct_answer,
        "answer_status": q.answer_status,
        "explanation_status": q.explanation_status,
        "answer_evidence": q.answer_evidence,
        "explanation": q.explanation,
        "extraction_warnings": q.extraction_warnings_json or [],
        "review_status": (status.status if status else None),
        "reviewer": (status.reviewer if status else ""),
        "has_provenance": has_provenance(db, question_id),
        "provenance_level": provenance_level(db, question_id),
        "provenance": provenance,
        "approval_blockers": approval_blockers(db, question_id),
        "review_history": [{
            "action": e.action, "reviewer": e.reviewer,
            "from_status": e.from_status, "to_status": e.to_status,
            "reason": e.reason, "created_at": e.created_at.isoformat(),
        } for e in events],
    }


class VerifyIn(BaseModel):
    evidence: str = ""


@app.post("/api/review/{question_id}/verify-answer")
def verify_answer_endpoint(question_id: str, payload: VerifyIn,
                           db: Session = Depends(get_db),
                           _token: str = Depends(require_reviewer)):
    from src.pipeline.review import verify_answer
    try:
        verify_answer(db, question_id, _token, payload.evidence)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "answer_status": "verified"}


@app.post("/api/review/{question_id}/verify-explanation")
def verify_explanation_endpoint(question_id: str, payload: VerifyIn,
                                db: Session = Depends(get_db),
                                _token: str = Depends(require_reviewer)):
    from src.pipeline.review import verify_explanation
    try:
        verify_explanation(db, question_id, _token, payload.evidence)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "explanation_status": "verified"}


class EditIn(BaseModel):
    question_text: str | None = None
    correct_answer: str | None = None
    explanation: str | None = None
    options_json: list | None = None


@app.post("/api/review/{question_id}/edit")
def edit_endpoint(question_id: str, payload: EditIn,
                  db: Session = Depends(get_db),
                  _token: str = Depends(require_reviewer)):
    from src.pipeline.review import edit_question
    try:
        edit_question(db, question_id, _token,
                      question_text=payload.question_text,
                      correct_answer=payload.correct_answer,
                      explanation=payload.explanation,
                      options_json=payload.options_json)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"ok": True}



@app.get("/api/progress/{student_id}")
def progress(student_id: str, x_student_id: str | None = Header(default=None),
             db: Session = Depends(get_db)):
    """Progress view: mastery refresh, weak topics (existing shape) + extras."""
    _enforce_student_id(x_student_id, student_id, "progress")
    from src.learning.review import review_summary
    from src.learning.weak_area import (
        open_recommendations, refresh_mastery, weak_skills, weak_topics,
    )
    refresh_mastery(db, student_id)
    weak = weak_topics(db, student_id)
    skills = weak_skills(db, student_id)
    return {
        "student_id": student_id,
        "weak_topics": [
            {"topic": w.topic_id, "accuracy": w.accuracy,
             "practiced": w.times_practiced} for w in weak],
        "weak_skills": [
            {"skill": s.skill_id, "topic": s.topic_id, "accuracy": s.accuracy,
             "practiced": s.times_practiced} for s in skills],
        "review": review_summary(db, student_id),
        "recommendations": open_recommendations(db, student_id),
    }


@app.get("/api/statistics/{student_id}")
def statistics_route(student_id: str, days: int = 14,
                     recent_window: int = 20,
                     x_student_id: str | None = Header(default=None),
                     db: Session = Depends(get_db)):
    """Deterministic learning statistics (subject/topic/skill/type/review)."""
    _enforce_student_id(x_student_id, student_id, "statistics")
    from src.learning.statistics import student_statistics
    from src.learning.weak_area import refresh_mastery
    refresh_mastery(db, student_id)
    return student_statistics(db, student_id, recent_window=recent_window,
                              days=days)


@app.get("/api/reviews/{student_id}")
def reviews_route(student_id: str, limit: int = 50,
                  x_student_id: str | None = Header(default=None),
                  db: Session = Depends(get_db)):
    """ReviewItem state for a student: due now, upcoming, per-state counts.

    Scheduling only - no FSRS. See src/learning/review.py.
    """
    _enforce_student_id(x_student_id, student_id, "reviews")
    from src.learning.review import due_review_items, review_summary
    due = due_review_items(db, student_id, limit=limit)
    summary = review_summary(db, student_id)
    return {
        "summary": summary,
        "due": [{"id": r.id, "source_type": r.source_type,
                 "source_id": r.source_id, "topic": r.topic_id,
                 "subject": r.subject, "state": r.state,
                 "due_at": r.due_at.isoformat() if r.due_at else "",
                 "due_reason": r.due_reason, "interval_days": r.interval_days,
                 "review_count": r.review_count,
                 "consecutive_correct": r.consecutive_correct} for r in due],
    }


@app.get("/api/recommendations/{student_id}")
def recommendations_route(student_id: str, refresh: bool = False,
                          x_student_id: str | None = Header(default=None),
                          db: Session = Depends(get_db)):
    """What the student should do next (deterministic, no LLM)."""
    _enforce_student_id(x_student_id, student_id, "recommendations")
    from src.learning.weak_area import (
        open_recommendations, refresh_recommendations,
    )
    if refresh:
        return {"recommendations": refresh_recommendations(db, student_id)}
    return {"recommendations": open_recommendations(db, student_id)}


@app.get("/api/loop/{student_id}")
def loop_route(student_id: str, x_student_id: str | None = Header(default=None),
               db: Session = Depends(get_db)):
    """The educational loop snapshot:
    LEARN -> PRACTISE -> ASSESS -> IDENTIFY ERROR -> EXPLAIN -> REVIEW ->
    RE-PRACTISE -> UPDATE MASTERY. Works without any LLM call.
    """
    _enforce_student_id(x_student_id, student_id, "loop")
    from src.learning.loop import loop_snapshot
    from src.learning.weak_area import refresh_mastery
    # UPDATE MASTERY step: recompute from fresh evidence before reading
    refresh_mastery(db, student_id)
    return loop_snapshot(db, student_id)


@app.get("/api/system/statistics")
def system_statistics_route(limit: int = 50, db: Session = Depends(get_db)):
    """Content-health view: validation status counts, hardest questions.

    Item-discrimination figures are indicative only and reported as ``None``
    until enough students have answered.
    """
    from src.learning.statistics import system_statistics
    return system_statistics(db, limit=limit)


@app.get("/api/curriculum/{topic_id}")
def curriculum(topic_id: str, db: Session = Depends(get_db)):
    from src.core.database import (
        CurriculumCommonMistake, CurriculumLesson, CurriculumStrategy,
        CurriculumWorkedExample,
    )
    return {
        "lessons": [{"title": r.title, "content": r.content_markdown}
                    for r in db.query(CurriculumLesson).filter_by(topic_id=topic_id).all()],
        "strategies": [{"title": r.title, "content": r.content_markdown}
                       for r in db.query(CurriculumStrategy).filter_by(topic_id=topic_id).all()],
        "worked_examples": [{"title": r.title, "content": r.content_markdown}
                            for r in db.query(CurriculumWorkedExample).filter_by(topic_id=topic_id).all()],
        "common_mistakes": [{"mistake": r.mistake_text, "explanation": r.explanation_markdown}
                            for r in db.query(CurriculumCommonMistake).filter_by(topic_id=topic_id).all()],
    }


@app.get("/api/parent/{student_id}")
def parent_dashboard(student_id: str, x_student_id: str | None = Header(default=None),
                     db: Session = Depends(get_db)):
    _enforce_student_id(x_student_id, student_id, "parent dashboard")
    from src.learning.parent_summary import parent_summary
    return parent_summary(db, student_id)


class ExamCreate(BaseModel):
    exam_board_id: str = "mixed"
    name: str = "Practice paper"
    region: str = ""


@app.post("/api/exams")
def create_exam(payload: ExamCreate, db: Session = Depends(get_db)):
    from src.core.database import AssessmentExam
    e = AssessmentExam(id=str(uuid.uuid4()), exam_board_id=payload.exam_board_id,
                       name=payload.name, region=payload.region)
    db.add(e)
    db.commit()
    return {"exam_id": e.id}


class AssembleIn(BaseModel):
    mode: str = "generated"  # generated | authentic
    sections: list[dict] = []
    document_id: str = ""
    seed: int = 42


@app.post("/api/exams/{exam_id}/assemble")
def assemble_exam(exam_id: str, payload: AssembleIn, db: Session = Depends(get_db)):
    from src.assessment.assembler import assemble_authentic, assemble_generated
    if payload.mode == "authentic":
        return assemble_authentic(db, exam_id, payload.document_id)
    return assemble_generated(db, exam_id, payload.sections, seed=payload.seed)


# ---------------- Knowledge / retrieval (read-only) ----------------
# Thin wrapper over the frozen ingestion foundation. Retrieval only ever
# *returns evidence* (filename + page + excerpt) for the given query; it never
# creates, promotes or approves questions/answers. If an index file is not
# configured or present, this returns HTTP 503 with a clear message so callers
# do not mistake "no index built yet" for "no evidence exists".

_KNOWLEDGE_INDEX_PATH = os.environ.get(
    "PLUS_KNOWLEDGE_INDEX", "data/knowledge/index.joblib"
)


class KnowledgeQuery(BaseModel):
    q: str
    k: int = 5


@app.post("/api/knowledge/search")
def knowledge_search(payload: KnowledgeQuery):
    from pathlib import Path

    from fastapi import HTTPException

    from src.knowledge.retriever import KnowledgeIndex
    path = Path(_KNOWLEDGE_INDEX_PATH)
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "knowledge index not built; run "
                "'python scripts/knowledge_cli.py index' first"
            ),
        )
    idx = KnowledgeIndex.load(path)
    hits = idx.search(payload.q, top_k=payload.k)
    return {
        "query": payload.q,
        "evidence": hits,
        "insufficient_evidence": len(hits) == 0,
    }


def _load_knowledge_index():
    """Load the on-disk knowledge index, or return ``None`` if none is built.

    Shared by the retrieval-only search endpoint and the source-grounded
    explain endpoint. ``None`` means "no index built yet" -- the explain path
    degrades to a no-evidence grounding note and never fabricates a citation.
    """
    from pathlib import Path

    from src.knowledge.retriever import KnowledgeIndex
    path = Path(_KNOWLEDGE_INDEX_PATH)
    if not path.exists():
        return None
    try:
        return KnowledgeIndex.load(path)
    except Exception:
        return None


@app.get("/api/explain/{question_id}")
def explain_question_endpoint(question_id: str, db: Session = Depends(get_db)):
    """EXPLAIN step: source-grounded explanation for an APPROVED question.

    Cohesive integration point between the trustworthy knowledge engine and the
    learning loop. It augments the deterministic stored explanation with
    verifiable source evidence (filename/page/excerpt/score) when a knowledge
    index is built. Keyed by ``question_id`` ONLY -- never by ``student_id`` --
    so it cannot inherit the student-ownership gap. The answer key stays
    protected: only APPROVED questions are explainable, mirroring the practice
    path, and evidence is always attributed and never presented as a quotation.
    """
    from src.learning.queries import explain_question
    q = db.query(CanonicalQuestion).filter_by(id=question_id).first()
    if q is None:
        raise HTTPException(404, "question not found")
    status = db.query(QuestionReviewStatus).filter_by(
        question_id=q.id).first()
    if status is None or status.status != "approved":
        # Never expose an answer/explanation for content that has not passed
        # the trustworthy-question contract (integrity rule: protect answer
        # keys; authoritative vs generated separation).
        raise HTTPException(403, "question is not approved for study")
    index = _load_knowledge_index()
    return explain_question(db, q, knowledge_index=index)
