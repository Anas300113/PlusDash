"""Explicit, DB-backed practice / study-session state machine.

Shared by normal practice, review practice and mock exams so neither the UI
nor the delivery mode owns the session lifecycle.

    planned -> started -> in_progress <-> reviewing -> complete
                                      \\-> abandoned

Design rules:
  * ``LearningQuestionAttempt`` stays the evidence record.
  * mastery is refreshed *from* attempts (never stored here).
  * review scheduling lives in src/learning/review.py.
  * a question must be ``approved`` before it can be answered or skipped.
  * sessions freeze their question order so they can be resumed exactly.

All functions take a SQLAlchemy ``Session`` and commit explicitly.
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy.orm import Session

from src.core.database import (
    LearningQuestionAttempt, LearningReviewItem, LearningStudent,
    LearningStudySession, QuestionReviewStatus, utcnow,
)
from src.learning.queries import (
    approved_question_ids, explain_question, question_map,
)
from src.learning.review import apply_review_result, ensure_review_item

ANSWER_ACTIONS = ("answer", "skip", "retry")


class SessionState(str, Enum):
    PLANNED = "planned"
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    REVIEWING = "reviewing"
    COMPLETE = "complete"
    ABANDONED = "abandoned"


class SessionType(str, Enum):
    LEARN = "learn"
    PRACTICE = "practice"
    REVIEW = "review"
    MOCK = "mock"
    DIAGNOSTIC = "diagnostic"
    CATCH_UP = "catch_up"


SESSION_TYPES = tuple(t.value for t in SessionType)
SESSION_STATES = tuple(s.value for s in SessionState)

# Allowed transitions. Terminal states accept nothing further.
SESSION_TRANSITIONS: dict[str, set[str]] = {
    SessionState.PLANNED.value: {SessionState.STARTED.value,
                                SessionState.ABANDONED.value},
    SessionState.STARTED.value: {SessionState.IN_PROGRESS.value,
                                SessionState.REVIEWING.value,
                                SessionState.COMPLETE.value,
                                SessionState.ABANDONED.value},
    SessionState.IN_PROGRESS.value: {SessionState.REVIEWING.value,
                                    SessionState.COMPLETE.value,
                                    SessionState.ABANDONED.value},
    SessionState.REVIEWING.value: {SessionState.IN_PROGRESS.value,
                                  SessionState.COMPLETE.value,
                                  SessionState.ABANDONED.value},
    SessionState.COMPLETE.value: set(),
    SessionState.ABANDONED.value: set(),
}


def order_questions(question_ids, mode: str = "canonical",
                    seed: int = 42) -> list[str]:
    """Deterministic question ordering (deduplicated, order preserved).

    ``mode='shuffled'`` uses a seeded RNG so a generated paper is reproducible
    from its seed - important for mocks and for test stability.
    """
    ids = list(dict.fromkeys(q for q in question_ids if q))
    if mode == "shuffled":
        random.Random(seed).shuffle(ids)
    return ids


def ensure_student(db: Session, student_id: str, name: str = "") -> LearningStudent:
    student = db.query(LearningStudent).filter_by(id=student_id).first()
    if student is None:
        student = LearningStudent(id=student_id, name=name or student_id)
        db.add(student)
        db.flush()
    return student


def get_session(db: Session, session_id: str) -> LearningStudySession:
    row = db.query(LearningStudySession).filter_by(id=session_id).first()
    if row is None:
        raise ValueError(f"unknown session {session_id}")
    return row


def _transition(session: LearningStudySession, new_state: str) -> None:
    """Enforce the state machine; illegal transitions raise ValueError."""
    if new_state not in SESSION_STATES:
        raise ValueError(f"unknown session state {new_state}")
    if new_state == session.state:
        return
    allowed = SESSION_TRANSITIONS.get(session.state, set())
    if new_state not in allowed:
        raise ValueError(
            f"illegal session transition {session.state} -> {new_state}")
    session.state = new_state


def start_session(db: Session, student_id: str, session_type: str = "practice",
                  question_ids=None, subject: str | None = None,
                  topic: str | None = None, question_type: str | None = None,
                  skill_id: str | None = None, limit: int | None = None,
                  ordering: str = "canonical", seed: int = 42,
                  planned_duration_seconds: int = 0,
                  goals: dict | None = None,
                  from_review_queue: bool = False,
                  session_id: str | None = None,
                  ) -> LearningStudySession:
    """Create a session and freeze its question order.

    ``from_review_queue=True`` builds the order from this student's due
    ReviewItems instead of a fresh topic selection - that is the difference
    between practice and review, without a second session model.
    """
    if session_type not in SESSION_TYPES:
        raise ValueError(f"unknown session type {session_type}")
    if session_id:
        existing = db.query(LearningStudySession).filter_by(
            id=session_id).first()
        if existing:
            if existing.student_id != student_id:
                raise ValueError("session id is already owned by another learner")
            if existing.session_type != session_type or (existing.goals_json or {}) != (goals or {}):
                raise ValueError("session request id was reused with different details")
            return existing
    ensure_student(db, student_id)

    if from_review_queue:
        from src.learning.review import due_question_ids
        selected = due_question_ids(db, student_id, limit=limit)
    elif question_ids:
        # Approve-filter explicit ids so a caller can never hand the UI a
        # non-approved question.
        allowed = set(approved_question_ids(db, limit=None))
        selected = [q for q in dict.fromkeys(question_ids) if q in allowed]
    else:
        selected = approved_question_ids(
            db, subject=subject, topic=topic, question_type=question_type,
            skill_id=skill_id, limit=limit)

    session = LearningStudySession(
        id=session_id or str(uuid.uuid4()), student_id=student_id,
        session_type=session_type,
        state=SessionState.STARTED.value,
        question_order_json=order_questions(selected, ordering, seed),
        current_index=0, planned_duration_seconds=planned_duration_seconds,
        goals_json=goals or {}, skipped_ids_json=[],
        recommended_activities_json=open_activities(db, student_id),
        started_at=utcnow())
    db.add(session)
    db.commit()
    return session


def open_activities(db: Session, student_id: str) -> list[dict]:
    """Open recommendations, copied onto the session for the UI to show."""
    from src.core.database import LearningRecommendation
    rows = (db.query(LearningRecommendation)
            .filter_by(student_id=student_id, status="open")
            .order_by(LearningRecommendation.created_at.desc())
            .limit(5).all())
    return [{"kind": r.kind, "reason": r.reason,
             "summary": r.summary or r.reason} for r in rows]


def current_index(session: LearningStudySession) -> int:
    return max(0, session.current_index or 0)


def current_question_id(db: Session, session: LearningStudySession) -> str | None:
    order = session.question_order
    index = current_index(session)
    return order[index] if index < len(order) else None


def question_payload(db: Session, question_id: str) -> dict:
    """Student-facing question shape (answers are only revealed via feedback)."""
    question = question_map(db, [question_id]).get(question_id)
    if question is None:
        raise ValueError(f"unknown question {question_id}")
    return {
        "id": question.id, "subject": question.subject, "topic": question.topic,
        "subtopic": question.subtopic, "question_type": question.question_type,
        "difficulty": question.difficulty,
        "instructions": question.instructions, "context": question.context,
        "question_text": question.question_text, "hint": question.hint or "",
        "options": question.options_json or [],
    }


def attempts_for_session(db: Session,
                         session_id: str) -> list[LearningQuestionAttempt]:
    return (db.query(LearningQuestionAttempt)
            .filter_by(session_id=session_id)
            .order_by(LearningQuestionAttempt.created_at).all())


def session_state(db: Session, session_id: str) -> dict:
    """Resume payload: everything the UI needs to continue a session."""
    session = get_session(db, session_id)
    order = session.question_order
    index = current_index(session)
    next_id = order[index] if index < len(order) else None
    attempts = attempts_for_session(db, session_id)
    return {
        "session_id": session.id,
        "student_id": session.student_id,
        "session_type": session.session_type,
        "state": session.state,
        "completion_state": session.completion_state,
        "progress": session.progress,
        "index": index,
        "total": len(order),
        "questions_remaining": session.questions_remaining,
        "question_order": order,
        "skipped_ids": list(session.skipped_ids_json or []),
        "current_question_id": next_id,
        "current_question": (question_payload(db, next_id) if next_id else None),
        "planned_duration_seconds": session.planned_duration_seconds,
        "actual_duration_seconds": session.actual_duration_seconds,
        "goals": session.goals_json or {},
        "recommended_activities": session.recommended_activities_json or [],
        "accuracy": session.accuracy,
        "attempt_count": len(attempts),
        "review_items_created": db.query(LearningReviewItem)
        .filter_by(origin_session_id=session.id).count(),
        "resumable": session.state in (SessionState.STARTED.value,
                                       SessionState.IN_PROGRESS.value,
                                       SessionState.REVIEWING.value),
        "started_at": session.started_at.isoformat() if session.started_at else "",
        "ended_at": session.ended_at.isoformat() if session.ended_at else "",
    }


def _attempt_number(db: Session, session_id: str, question_id: str) -> int:
    return db.query(LearningQuestionAttempt).filter_by(
        session_id=session_id, question_id=question_id).count() + 1


def _normalise(value: str) -> str:
    return (value or "").strip().upper()


def _advance(db: Session, session: LearningStudySession) -> None:
    order = session.question_order
    index = current_index(session) + 1
    session.current_index = index
    if index >= len(order):
        session.state = SessionState.REVIEWING.value
    elif session.state == SessionState.STARTED.value:
        session.state = SessionState.IN_PROGRESS.value
    session.ended_at = None


def _sync_session_progress(db: Session, session: LearningStudySession) -> None:
    """Mirror attempt evidence onto the session row (duration + accuracy)."""
    if session.started_at:
        session.actual_duration_seconds = int(
            (utcnow() - session.started_at).total_seconds())
    answered = [a for a in attempts_for_session(db, session.id)
                if a.action in ("answer", "retry")]
    # the current attempt may not be flushed into the query yet
    pending = [a for a in db.new
               if isinstance(a, LearningQuestionAttempt)
               and a.session_id == session.id and a.action in ("answer", "retry")]
    answered.extend(pending)
    if answered:
        session.accuracy = sum(
            1 for a in answered if a.is_correct) / len(answered)


def submit_answer(db: Session, session_id: str, question_id: str,
                  chosen_answer: str, time_taken_ms: int = 0,
                  hint_used: bool = False, action: str = "answer",
                  now: datetime | None = None,
                  enforce_current: bool = True,
                  attempt_id: str | None = None) -> dict:
    """Answer, skip or retry a question in a session.

    Educational loop position: PRACTISE -> ASSESS -> IDENTIFY ERROR ->
    EXPLAIN -> (create REVIEW item) -> UPDATE MASTERY.

    Evidence is never destroyed: skips and retries are stored as additional
    ``LearningQuestionAttempt`` rows, and accuracy statistics ignore skips.

    ``enforce_current=False`` records evidence for a question that is not the
    session's current question and does not advance the cursor (used by the
    legacy ``POST /api/attempts`` endpoint, which has no frozen order).
    """
    if action not in ANSWER_ACTIONS:
        raise ValueError(f"unknown action {action}")
    session = get_session(db, session_id)
    if session.state in (SessionState.COMPLETE.value,
                         SessionState.ABANDONED.value):
        raise ValueError(f"session is {session.state}")

    expected = current_question_id(db, session)
    is_current = expected == question_id
    if enforce_current:
        if expected is None:
            raise ValueError("session has no current question")
        if not is_current:
            raise ValueError(
                f"question {question_id} is not the current question "
                f"({expected})")

    status = db.query(QuestionReviewStatus).filter_by(
        question_id=question_id).first()
    if status is None or status.status != "approved":
        raise ValueError("question is not approved for practice")

    question = question_map(db, [question_id])[question_id]
    # A submitted option must belong to the actual question. For MCQs that
    # carry an option set, reject an out-of-set choice server-side (a client
    # must not be able to submit an arbitrary value and have it marked).
    if action == "answer" and chosen_answer:
        from src.pipeline.review import option_labels, _looks_mcq
        if _looks_mcq(question):
            allowed = {l.upper() for l in option_labels(question)}
            # Also accept a chosen option's literal text (some clients post
            # the text, not the letter) by matching against option text.
            texts = {str((o or {}).get("text", "")).strip().upper()
                     for o in (question.options_json or []) if isinstance(o, dict)}
            if allowed and chosen_answer.strip().upper() not in allowed \
                    and chosen_answer.strip().upper() not in texts:
                raise ValueError(
                    f"answer '{chosen_answer}' is not one of the question's "
                    f"options")
    is_correct = (_normalise(chosen_answer)
                  == _normalise(question.correct_answer))
    if action == "skip":
        is_correct = False

    attempt = LearningQuestionAttempt(
        id=attempt_id or str(uuid.uuid4()), student_id=session.student_id,
        session_id=session_id, question_id=question_id,
        chosen_answer=chosen_answer, is_correct=is_correct,
        time_taken_ms=time_taken_ms, action=action,
        attempt_number=_attempt_number(db, session_id, question_id),
        hint_used=hint_used)
    db.add(attempt)

    review_item = None
    skipped = list(session.skipped_ids_json or [])
    if action == "skip":
        # A skip is a knowledge gap: record it and revisit it via review.
        if question_id not in skipped:
            skipped.append(question_id)
        session.skipped_ids_json = skipped
    if is_current:
        _advance(db, session)

    if is_correct is False:
        # EDUCATIONAL LOOP: an error (or skip) becomes a scheduled review item.
        review_item, _ = ensure_review_item(
            db, session.student_id, question_id, source_type="question",
            topic_id=question.topic, subject=question.subject,
            question_type=question.question_type,
            skill_ids=question.skill_ids,
            due_reason="skipped" if action == "skip" else "incorrect",
            origin_attempt_id=attempt.id, origin_session_id=session.id,
            difficulty=question.difficulty, now=now)
    elif attempt.attempt_number > 1:
        # Retry that succeeded inside the same session: the first failure is
        # what created the item, so this recovery just advances its schedule.
        from src.learning.review import get_review_item
        review_item = get_review_item(db, session.student_id, "question",
                                      question_id)
        if review_item is not None:
            apply_review_result(db, review_item, True, attempt_id=attempt.id,
                                now=now)

    _sync_session_progress(db, session)
    db.commit()

    return {
        "attempt_id": attempt.id,
        "action": action,
        "is_correct": is_correct,
        "explanation": question.explanation,
        "feedback": explain_question(db, question, chosen_answer=chosen_answer,
                                     is_correct=is_correct),
        "review_item_id": review_item.id if review_item else "",
        "session": session_state(db, session_id),
    }


def retry_current(db: Session, session_id: str,
                  question_id: str | None = None) -> dict:
    """RETRY step: reopen a question for a second attempt.

    With no ``question_id`` this reopens the question the student just
    answered (moving the cursor back), which is the useful behaviour after a
    wrong answer that auto-advanced. No evidence row is written here: the
    retry is recorded as an attempt with ``action='retry'`` when the student
    submits again, so mastery/accuracy can distinguish it from a first try.
    """
    session = get_session(db, session_id)
    if session.state in (SessionState.COMPLETE.value,
                         SessionState.ABANDONED.value):
        raise ValueError(f"session is {session.state}")
    order = session.question_order
    if question_id is None:
        attempts = attempts_for_session(db, session_id)
        if attempts:
            question_id = attempts[-1].question_id
        else:
            question_id = current_question_id(db, session)
    if not question_id or question_id not in order:
        raise ValueError("no question available to retry")
    session.current_index = order.index(question_id)
    if session.state == SessionState.STARTED.value:
        session.state = SessionState.IN_PROGRESS.value
    db.commit()
    question = question_map(db, [question_id])[question_id]
    return {
        "session_id": session_id,
        "question_id": question_id,
        "retry_number": _attempt_number(db, session_id, question_id),
        "hint": question.hint,
        "session": session_state(db, session_id),
    }


def skip_current(db: Session, session_id: str, time_taken_ms: int = 0,
                 now: datetime | None = None,
                 question_id: str | None = None) -> dict:
    """Convenience wrapper: skip without inventing an answer string.

    If ``question_id`` is provided, that question is skipped (must be in the
    session's frozen order). If omitted, the session's current question is
    skipped. If the cursor has already advanced past all questions, the last
    question in the order is skipped instead - this lets a "skip" be recorded
    as evidence even when the session is in reviewing state.
    """
    session = get_session(db, session_id)
    if question_id is None:
        question_id = current_question_id(db, session)
    if question_id is None:
        order = session.question_order
        if order:
            question_id = order[-1]
    if question_id is None or question_id not in session.question_order:
        raise ValueError("no question available to skip")
    # When skipping via explicit question_id or a past-the-cursor question,
    # enforce_current must be False so submit_answer records the evidence.
    enforce = (question_id == current_question_id(db, session))
    return submit_answer(db, session_id, question_id, chosen_answer="",
                         time_taken_ms=time_taken_ms, action="skip",
                         now=now, enforce_current=enforce)


def complete_session(db: Session, session_id: str) -> dict:
    """Close a session, refresh mastery, and hand back a results view.

    This is the loop's UPDATE MASTERY step: mastery is recomputed from attempt
    evidence, then recommendations are regenerated from the new mastery.
    """
    from src.learning.weak_area import refresh_mastery, refresh_recommendations

    session = get_session(db, session_id)
    if session.state not in (SessionState.COMPLETE.value,
                             SessionState.ABANDONED.value):
        _transition(session, SessionState.COMPLETE.value)
    session.current_index = len(session.question_order)
    session.ended_at = utcnow()
    if session.started_at:
        session.actual_duration_seconds = int(
            (session.ended_at - session.started_at).total_seconds())
    db.commit()

    refresh_mastery(db, session.student_id)
    results = session_results(db, session_id)
    results["recommendations"] = refresh_recommendations(db,
                                                         session.student_id)
    activities = open_activities(db, session.student_id)
    results["recommended_activities"] = activities
    session.recommended_activities_json = activities
    db.commit()
    return results


def abandon_session(db: Session, session_id: str) -> dict:
    """Abandon a session without deleting any attempt evidence."""
    from src.learning.weak_area import refresh_mastery

    session = get_session(db, session_id)
    if session.state not in (SessionState.COMPLETE.value,
                             SessionState.ABANDONED.value):
        _transition(session, SessionState.ABANDONED.value)
    session.ended_at = utcnow()
    if session.started_at:
        session.actual_duration_seconds = int(
            (session.ended_at - session.started_at).total_seconds())
    db.commit()
    refresh_mastery(db, session.student_id)
    return session_state(db, session_id)


def session_results(db: Session, session_id: str) -> dict:
    """Results view shared by practice, review and mock sessions."""
    session = get_session(db, session_id)
    attempts = attempts_for_session(db, session_id)
    answered = [a for a in attempts if a.action in ("answer", "retry")]
    skipped = [a for a in attempts if a.action == "skip"]
    questions = question_map(db, [a.question_id for a in attempts])
    by_topic: dict[str, dict] = {}
    by_subject: dict[str, dict] = {}
    for a in answered:
        question = questions.get(a.question_id)
        if question is None:
            continue
        for bucket, key in ((by_topic, question.topic),
                            (by_subject, question.subject)):
            entry = bucket.setdefault(key, {"attempted": 0, "correct": 0})
            entry["attempted"] += 1
            entry["correct"] += 1 if a.is_correct else 0
    mistakes = [{"question_id": a.question_id,
                 "chosen_answer": a.chosen_answer,
                 "correct_answer": questions[a.question_id].correct_answer
                 if a.question_id in questions else "",
                 "topic": questions[a.question_id].topic
                 if a.question_id in questions else "",
                 "attempt_number": a.attempt_number}
                for a in answered if not a.is_correct]
    return {
        "session_id": session.id,
        "session_type": session.session_type,
        "state": session.state,
        "total_questions": len(session.question_order),
        "answered": len(answered),
        "skipped": len(skipped),
        "correct": sum(1 for a in answered if a.is_correct),
        "accuracy": (sum(1 for a in answered if a.is_correct) / len(answered))
        if answered else 0.0,
        "planned_duration_seconds": session.planned_duration_seconds,
        "actual_duration_seconds": session.actual_duration_seconds,
        "by_topic": by_topic,
        "by_subject": by_subject,
        "mistakes": mistakes,
        "retries": sum(1 for a in attempts if a.action == "retry"),
        "hints_used": sum(1 for a in attempts if a.hint_used),
        "review_items_created": db.query(LearningReviewItem)
        .filter_by(origin_session_id=session.id).count(),
    }
