"""Authenticated Plus11 learner API, derived solely from a verified Manus JWT."""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.manus_identity import LearnerIdentity, get_current_learner
from src.core.database import (
    CanonicalQuestion, CanonicalSubject, CanonicalTopic,
    LearningQuestionAttempt, LearningRecommendation, LearningReviewItem,
    LearningStudent, LearningStudySession, QuestionReviewStatus, utcnow,
)

router = APIRouter(prefix="/api/me", tags=["Plus11 learner account"])

DEFAULT_SUBJECTS = (
    ("maths", "Maths"),
    ("english", "English"),
    ("verbal-reasoning", "Verbal reasoning"),
    ("non-verbal-reasoning", "Non-verbal reasoning"),
)
MEASURED_ACTIONS = ("answer", "retry")


def get_db():
    # Delayed import avoids a module cycle: main registers this router, while
    # the dependency uses the single process-wide SQLAlchemy session factory.
    from src.api.main import _Session
    db = _Session()
    try:
        yield db
    finally:
        db.close()


def _profile(db: Session, identity: LearnerIdentity) -> LearningStudent:
    row = db.query(LearningStudent).filter_by(id=identity.student_id).first()
    if row:
        return row
    row = LearningStudent(id=identity.student_id, name=identity.display_name)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.query(LearningStudent).filter_by(id=identity.student_id).first()
        if row is None:
            raise
    return row


def _display_name(db: Session, identity: LearnerIdentity) -> str:
    """Read the saved profile without creating a row as a GET side effect."""
    row = db.query(LearningStudent).filter_by(id=identity.student_id).first()
    return row.name if row else identity.display_name


def _attempt_rows(db: Session, student_id: str) -> list[LearningQuestionAttempt]:
    return (db.query(LearningQuestionAttempt)
            .filter_by(student_id=student_id)
            .order_by(LearningQuestionAttempt.created_at).all())


def _streak_days(attempts: list[LearningQuestionAttempt]) -> int:
    active_dates = {
        attempt.created_at.date()
        for attempt in attempts
        if attempt.created_at and attempt.action in MEASURED_ACTIONS
    }
    today = utcnow().date()
    day = today if today in active_dates else today - timedelta(days=1)
    streak = 0
    while day in active_dates:
        streak += 1
        day -= timedelta(days=1)
    return streak


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")


def _subject_id(value: str) -> str:
    slug = _slug(value)
    aliases = {
        "math": "maths", "mathematics": "maths", "maths": "maths",
        "verbal-reasoning": "verbal-reasoning", "vr": "verbal-reasoning",
        "non-verbal-reasoning": "non-verbal-reasoning",
        "nonverbal-reasoning": "non-verbal-reasoning", "nvr": "non-verbal-reasoning",
    }
    return aliases.get(slug, slug)


def _humanise(value: str) -> str:
    words = (value or "").replace("_", "-").split("-")
    known = {"maths": "Maths", "nvr": "NVR", "vr": "VR"}
    return " ".join(known.get(word.lower(), word.capitalize()) for word in words if word)


def _catalog(db: Session, student_id: str) -> list[dict]:
    approved_rows = (db.query(
            CanonicalQuestion.subject, CanonicalQuestion.topic,
            __import__("sqlalchemy").func.count(CanonicalQuestion.id))
        .join(QuestionReviewStatus,
              QuestionReviewStatus.question_id == CanonicalQuestion.id)
        .filter(QuestionReviewStatus.status == "approved")
        .group_by(CanonicalQuestion.subject, CanonicalQuestion.topic)
        .all())
    subject_names = {row.id: row.name for row in db.query(CanonicalSubject).all()}
    topic_names = {row.id: row.name for row in db.query(CanonicalTopic).all()}

    attempts: dict[tuple[str, str], list[bool]] = {}
    attempt_rows = (db.query(
            CanonicalQuestion.subject, CanonicalQuestion.topic,
            LearningQuestionAttempt.is_correct)
        .join(LearningQuestionAttempt,
              LearningQuestionAttempt.question_id == CanonicalQuestion.id)
        .join(QuestionReviewStatus,
              QuestionReviewStatus.question_id == CanonicalQuestion.id)
        .filter(
            LearningQuestionAttempt.student_id == student_id,
            LearningQuestionAttempt.action.in_(MEASURED_ACTIONS),
            QuestionReviewStatus.status == "approved")
        .all())
    for subject, topic, correct in attempt_rows:
        attempts.setdefault((subject, topic), []).append(bool(correct))

    grouped: dict[str, dict] = {}
    for subject, topic, question_count in approved_rows:
        group = grouped.setdefault(subject, {
            "id": subject,
            "name": subject_names.get(subject, _humanise(subject)),
            "topics": [],
            "_attempts": 0,
            "_correct": 0,
        })
        evidence = attempts.get((subject, topic), [])
        group["_attempts"] += len(evidence)
        group["_correct"] += sum(evidence)
        group["topics"].append({
            "id": topic,
            "name": topic_names.get(topic, _humanise(topic)),
            "approved_question_count": int(question_count),
            "attempts": len(evidence),
            "mastery": round(100 * sum(evidence) / len(evidence)) if evidence else 0,
        })

    result = []
    for subject in sorted(grouped.values(), key=lambda item: item["name"].casefold()):
        subject["topics"].sort(key=lambda item: item["name"].casefold())
        attempts_count = subject.pop("_attempts")
        correct_count = subject.pop("_correct")
        subject["subject_id"] = _subject_id(subject["id"])
        subject["topic_count"] = len(subject["topics"])
        subject["attempts"] = attempts_count
        subject["mastery"] = round(100 * correct_count / attempts_count) if attempts_count else 0
        result.append(subject)
    return result


def _week_activity(attempts: list[LearningQuestionAttempt]) -> tuple[list[dict], int, int]:
    today = utcnow().date()
    monday = today - timedelta(days=today.weekday())
    dates = [monday + timedelta(days=index) for index in range(7)]
    by_date: dict[date, list[LearningQuestionAttempt]] = {day: [] for day in dates}
    for attempt in attempts:
        if attempt.created_at:
            day = attempt.created_at.date()
            if day in by_date:
                by_date[day].append(attempt)
    output = []
    for day in dates:
        rows = by_date[day]
        if day == today:
            state = "today"
        elif day < today:
            state = "complete" if rows else "missed"
        else:
            state = "upcoming"
        millis = sum(row.time_taken_ms or 0 for row in rows if row.action in MEASURED_ACTIONS)
        output.append({
            "date": day.isoformat(),
            "label": day.strftime("%a"),
            "state": state,
            "minutes": millis // 60_000,
        })
    practice_days = sum(1 for day in dates if day <= today and by_date[day])
    today_minutes = sum(
        row.time_taken_ms or 0 for row in by_date[today]
        if row.action in MEASURED_ACTIONS
    ) // 60_000
    return output, practice_days, today_minutes


def _display_for_raw_subject(db: Session, value: str) -> str:
    row = db.query(CanonicalSubject).filter_by(id=value).first()
    if row:
        return row.name
    known = dict(DEFAULT_SUBJECTS)
    return known.get(_subject_id(value), _humanise(value))


def _owned_session(db: Session, student_id: str, session_id: str) -> LearningStudySession:
    row = db.query(LearningStudySession).filter_by(id=session_id).first()
    if row is None or row.student_id != student_id:
        raise HTTPException(404, "We couldn’t find that practice session.")
    return row


def _session_view(db: Session, session_id: str) -> dict:
    from src.learning.session import session_state
    try:
        state = session_state(db, session_id)
    except ValueError:
        raise HTTPException(404, "We couldn’t find that practice session.") from None
    return {
        "session_id": state["session_id"],
        "state": state["state"],
        "index": state["index"],
        "total": state["total"],
        "progress": state["progress"],
        "current_question_id": state["current_question_id"],
        "current_question": state["current_question"],
        "goals": state["goals"],
        "resumable": state["resumable"],
        "actual_duration_seconds": state["actual_duration_seconds"],
        "attempt_count": state["attempt_count"],
    }


@router.get("/profile")
def get_profile(
    identity: LearnerIdentity = Depends(get_current_learner),
    db: Session = Depends(get_db),
):
    display_name = _display_name(db, identity)
    attempts = _attempt_rows(db, identity.student_id)
    return {
        "student_id": identity.student_id,
        "display_name": display_name,
        "streak_days": _streak_days(attempts),
    }


class ProfilePatch(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)


@router.patch("/profile")
def update_profile(
    payload: ProfilePatch,
    identity: LearnerIdentity = Depends(get_current_learner),
    db: Session = Depends(get_db),
):
    normalized = " ".join(payload.display_name.split())
    if len(normalized) < 2 or len(normalized) > 40 or re.search(r"[\x00-\x1f\x7f]", normalized):
        raise HTTPException(400, "Use a name between 2 and 40 characters.")
    profile = _profile(db, identity)
    profile.name = normalized
    db.commit()
    db.refresh(profile)
    return {
        "student_id": identity.student_id,
        "display_name": profile.name,
        "streak_days": _streak_days(_attempt_rows(db, identity.student_id)),
    }


@router.get("/catalog")
def get_catalog(
    identity: LearnerIdentity = Depends(get_current_learner),
    db: Session = Depends(get_db),
):
    return {"subjects": _catalog(db, identity.student_id)}


@router.get("/dashboard")
def get_dashboard(
    identity: LearnerIdentity = Depends(get_current_learner),
    db: Session = Depends(get_db),
):
    from src.learning.review import due_review_items
    from src.learning.statistics import student_statistics

    display_name = _display_name(db, identity)
    attempts = _attempt_rows(db, identity.student_id)
    week, _, today_minutes = _week_activity(attempts)
    stats = student_statistics(db, identity.student_id, days=7)
    due_count = len(due_review_items(db, identity.student_id, limit=50))
    active_sessions = (db.query(LearningStudySession)
        .filter(
            LearningStudySession.student_id == identity.student_id,
            LearningStudySession.state.in_(("started", "in_progress", "reviewing")),
        )
        .order_by(LearningStudySession.started_at.desc()).limit(20).all())
    active = next((row for row in active_sessions
                   if row.current_index < len(row.question_order)), None)
    today = utcnow().date()
    completed_today = [row for row in db.query(LearningStudySession)
        .filter_by(student_id=identity.student_id, state="complete").all()
        if row.started_at and row.started_at.date() == today]

    if active:
        goals = active.goals_json or {}
        subject_id = str(goals.get("plus11_subject_id", ""))
        topic_id = str(goals.get("plus11_topic_id", ""))
        href = "/practice?" + urlencode({
            "sessionId": active.id, "subject": subject_id, "topic": topic_id,
        })
        subject_label = _display_for_raw_subject(db, subject_id) if subject_id else "practice"
        question_number = min(active.current_index + 1, len(active.question_order))
        first_item = {
            "id": "continue-practice",
            "title": f"Continue {subject_label} practice",
            "detail": f"Question {question_number} of {len(active.question_order)}",
            "href": href,
            "done": False,
            "in_progress": True,
        }
        continue_href = href
    elif completed_today:
        row = completed_today[-1]
        goals = row.goals_json or {}
        subject_id = str(goals.get("plus11_subject_id", ""))
        topic_id = str(goals.get("plus11_topic_id", ""))
        label = _display_for_raw_subject(db, subject_id) if subject_id else "Practice"
        first_item = {
            "id": "practice-complete",
            "title": f"{label} practice",
            "detail": f"{stats['totals']['answered']} saved answers to date",
            "href": "/learn",
            "done": True,
            "in_progress": False,
        }
        continue_href = "/learn"
    else:
        first_item = {
            "id": "choose-topic",
            "title": "Choose a topic to begin",
            "detail": "Start with a question from the reviewed bank.",
            "href": "/learn",
            "done": False,
            "in_progress": False,
        }
        continue_href = "/learn"

    review_minutes = max(1, round(due_count * 40 / 60)) if due_count else 0
    plan = [
        first_item,
        {
            "id": "review",
            "title": (f"Review: {due_count} "
                      f"{'card' if due_count == 1 else 'cards'} due"),
            "detail": (f"About {review_minutes} minute"
                       f"{'s' if review_minutes != 1 else ''}"
                       if due_count else "No review cards due just now"),
            "href": "/review",
            "done": False,
            "in_progress": False,
        },
        {
            "id": "progress",
            "title": "See your progress",
            "detail": f"{stats['totals']['answered']} saved answers so far",
            "href": "/progress",
            "done": False,
            "in_progress": False,
        },
    ]
    return {
        "display_name": display_name,
        "streak_days": _streak_days(attempts),
        "daily_minutes": today_minutes,
        "daily_target_minutes": 30,
        "plan": plan,
        "completed_count": sum(1 for item in plan if item["done"]),
        "due_count": due_count,
        "continue_href": continue_href,
        "has_active_session": active is not None,
        "minutes_by_day": week,
    }


@router.get("/progress")
def get_progress(
    identity: LearnerIdentity = Depends(get_current_learner),
    db: Session = Depends(get_db),
):
    from src.learning.review import due_review_items
    from src.learning.statistics import student_statistics
    from src.learning.weak_area import open_recommendations

    attempts = _attempt_rows(db, identity.student_id)
    week, practice_days, _ = _week_activity(attempts)
    stats = student_statistics(db, identity.student_id, days=7)
    by_subject = stats["by_subject"]
    mastery_by_id: dict[str, dict] = {}
    for raw_subject, row in by_subject.items():
        slug = _subject_id(raw_subject)
        existing = mastery_by_id.setdefault(slug, {
            "attempts": 0, "correct": 0, "name": _display_for_raw_subject(db, raw_subject),
        })
        existing["attempts"] += row["attempted"]
        existing["correct"] += row["correct"]
    mastery = []
    for subject_id, name in DEFAULT_SUBJECTS:
        value = mastery_by_id.pop(subject_id, {"attempts": 0, "correct": 0, "name": name})
        mastery.append({
            "id": subject_id,
            "name": name,
            "mastery": round(100 * value["correct"] / value["attempts"]) if value["attempts"] else 0,
            "attempts": value["attempts"],
        })
    for subject_id, value in sorted(mastery_by_id.items()):
        mastery.append({
            "id": subject_id,
            "name": value["name"],
            "mastery": round(100 * value["correct"] / value["attempts"]) if value["attempts"] else 0,
            "attempts": value["attempts"],
        })

    due_count = len(due_review_items(db, identity.student_id, limit=50))
    recommendations = open_recommendations(db, identity.student_id)
    if due_count:
        next_step = {
            "subject_id": "", "topic_id": "",
            "title": f"Review {due_count} card{'s' if due_count != 1 else ''} due",
            "detail": "A short look back can help the ideas stick.",
            "href": "/review",
        }
    elif recommendations:
        recommendation = recommendations[0]
        next_step = {
            "subject_id": "", "topic_id": "",
            "title": recommendation.get("summary") or recommendation.get("reason") or "Continue your learning",
            "detail": recommendation.get("reason") or "Choose a reviewed topic to practise.",
            "href": "/learn",
        }
    elif stats["weak_topics"]:
        weakest = stats["weak_topics"][0]
        question = db.query(CanonicalQuestion).filter_by(topic=weakest["topic"]).first()
        href = ("/practice?" + urlencode({"subject": question.subject, "topic": question.topic})
                if question else "/learn")
        next_step = {
            "subject_id": _subject_id(question.subject) if question else "",
            "topic_id": question.topic if question else "",
            "title": f"Try {_humanise(weakest['topic']).lower()} again",
            "detail": "A short practice can help this topic feel clearer.",
            "href": href,
        }
    else:
        next_step = {
            "subject_id": "", "topic_id": "",
            "title": "Choose a topic to begin",
            "detail": "Your progress will take shape as you practise reviewed questions.",
            "href": "/learn",
        }
    totals = stats["totals"]
    return {
        "overall": round(100 * totals["accuracy"]),
        "total_attempts": totals["answered"],
        "has_history": totals["answered"] > 0,
        "mastery": mastery,
        "minutes_by_day": week,
        "practice_days": practice_days,
        "next_step": next_step,
    }


@router.get("/reviews")
def get_reviews(
    identity: LearnerIdentity = Depends(get_current_learner),
    db: Session = Depends(get_db),
):
    from src.learning.review import due_review_items

    items = due_review_items(db, identity.student_id, limit=50)
    question_ids = [item.source_id for item in items if item.source_type == "question"]
    questions = (db.query(CanonicalQuestion)
        .join(QuestionReviewStatus,
              QuestionReviewStatus.question_id == CanonicalQuestion.id)
        .filter(CanonicalQuestion.id.in_(question_ids),
                QuestionReviewStatus.status == "approved").all()) if question_ids else []
    by_id = {question.id: question for question in questions}
    cards = []
    for item in items:
        question = by_id.get(item.source_id)
        if item.source_type != "question" or not question:
            continue
        cards.append({
            "card_id": item.id,
            "subject_id": _subject_id(question.subject),
            "topic_id": question.topic,
            "topic": _humanise(question.topic),
            "prompt": question.question_text,
        })
    return {"cards": cards, "due_count": len(cards)}


def _owned_review(db: Session, student_id: str, card_id: str):
    item = db.query(LearningReviewItem).filter_by(
        id=card_id, student_id=student_id, source_type="question").first()
    if not item or item.state == "suspended":
        raise HTTPException(404, "This review card is no longer available.")
    question = (db.query(CanonicalQuestion)
        .join(QuestionReviewStatus,
              QuestionReviewStatus.question_id == CanonicalQuestion.id)
        .filter(CanonicalQuestion.id == item.source_id,
                QuestionReviewStatus.status == "approved").first())
    if not question:
        raise HTTPException(404, "This review card is no longer available.")
    return item, question


@router.post("/reviews/{card_id}/reveal")
def reveal_review_answer(
    card_id: str,
    identity: LearnerIdentity = Depends(get_current_learner),
    db: Session = Depends(get_db),
):
    _owned_review(db, identity.student_id, card_id)
    item, question = _owned_review(db, identity.student_id, card_id)
    return {
        "answer": question.correct_answer,
        "explanation": question.explanation,
        "topic": _humanise(item.topic_id or question.topic),
    }


class ReviewAnswerIn(BaseModel):
    outcome: Literal["got-it", "again"]
    event_id: str = Field(min_length=36, max_length=36)


@router.post("/reviews/{card_id}/answer")
def answer_review(
    card_id: str,
    payload: ReviewAnswerIn,
    identity: LearnerIdentity = Depends(get_current_learner),
    db: Session = Depends(get_db),
):
    from src.learning.review import apply_review_result, review_summary

    try:
        uuid.UUID(payload.event_id)
    except ValueError:
        raise HTTPException(400, "This review action couldn’t be saved.") from None
    item, _ = _owned_review(db, identity.student_id, card_id)
    history = list(item.review_history_json or [])
    if not any(entry.get("attempt_id") == payload.event_id for entry in history):
        apply_review_result(db, item, payload.outcome == "got-it",
                            attempt_id=payload.event_id)
        db.commit()
    summary = review_summary(db, identity.student_id)
    return {"due_count": summary["due_now"], "saved": True}


class PracticeStartIn(BaseModel):
    subject_id: str = Field(min_length=1, max_length=100)
    topic_id: str = Field(min_length=1, max_length=140)
    idempotency_key: str = Field(min_length=36, max_length=36)


@router.post("/practice/sessions")
def create_practice_session(
    payload: PracticeStartIn,
    identity: LearnerIdentity = Depends(get_current_learner),
    db: Session = Depends(get_db),
):
    from src.learning.queries import approved_question_ids
    from src.learning.session import start_session

    try:
        request_uuid = uuid.UUID(payload.idempotency_key)
    except ValueError:
        raise HTTPException(400, "Choose a valid subject and topic before starting practice.") from None
    questions = approved_question_ids(
        db, subject=payload.subject_id, topic=payload.topic_id, limit=8)
    if not questions:
        raise HTTPException(409, "There aren’t any reviewed questions for this topic yet. Try another topic or use guest practice.")
    _profile(db, identity)

    session_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"plus11:practice:{identity.student_id}:{request_uuid}"))
    goals = {
        "plus11_subject_id": payload.subject_id,
        "plus11_topic_id": payload.topic_id,
    }
    existing = db.query(LearningStudySession).filter_by(id=session_id).first()
    if existing:
        if existing.student_id != identity.student_id or (existing.goals_json or {}) != goals:
            raise HTTPException(409, "This practice request has already been used.")
        return _session_view(db, existing.id)
    try:
        session = start_session(
            db, identity.student_id, session_type="practice",
            question_ids=questions, subject=payload.subject_id,
            topic=payload.topic_id, limit=8, goals=goals,
            session_id=session_id)
    except IntegrityError:
        db.rollback()
        existing = db.query(LearningStudySession).filter_by(id=session_id).first()
        if not existing or existing.student_id != identity.student_id or (existing.goals_json or {}) != goals:
            raise HTTPException(409, "We couldn’t start this practice set. Please try again.") from None
        session = existing
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return _session_view(db, session.id)


@router.get("/practice/sessions/{session_id}")
def get_practice_session(
    session_id: str,
    identity: LearnerIdentity = Depends(get_current_learner),
    db: Session = Depends(get_db),
):
    _owned_session(db, identity.student_id, session_id)
    return _session_view(db, session_id)


class PracticeAnswerIn(BaseModel):
    question_id: str = Field(min_length=1, max_length=255)
    chosen_answer: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=36, max_length=36)
    time_taken_ms: int = Field(default=0, ge=0, le=7_200_000)
    hint_used: bool = False
    action: Literal["answer", "retry"] = "answer"


def _answer_response(db: Session, attempt: LearningQuestionAttempt) -> dict:
    question = db.query(CanonicalQuestion).filter_by(id=attempt.question_id).first()
    return {
        "is_correct": bool(attempt.is_correct),
        "explanation": question.explanation if question else "",
        "review_item_id": attempt.review_item_id,
    }


@router.post("/practice/sessions/{session_id}/answers")
def answer_practice_question(
    session_id: str,
    payload: PracticeAnswerIn,
    identity: LearnerIdentity = Depends(get_current_learner),
    db: Session = Depends(get_db),
):
    from src.learning.session import session_state, submit_answer

    session = _owned_session(db, identity.student_id, session_id)
    try:
        event_uuid = uuid.UUID(payload.idempotency_key)
    except ValueError:
        raise HTTPException(400, "This practice answer could not be checked. Please try again.") from None
    attempt_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"plus11:answer:{identity.student_id}:{session_id}:{event_uuid}"))
    existing = db.query(LearningQuestionAttempt).filter_by(id=attempt_id).first()
    if existing:
        if (existing.student_id != identity.student_id
                or existing.session_id != session_id
                or existing.question_id != payload.question_id
                or existing.chosen_answer != payload.chosen_answer):
            raise HTTPException(409, "This answer request id was already used.")
        result = _answer_response(db, existing)
        result["session"] = _session_view(db, session_id)
        return result

    try:
        result = submit_answer(
            db, session_id, payload.question_id, payload.chosen_answer,
            time_taken_ms=payload.time_taken_ms,
            hint_used=payload.hint_used, action=payload.action,
            enforce_current=(payload.action != "retry"),
            attempt_id=attempt_id)
    except IntegrityError:
        db.rollback()
        existing = db.query(LearningQuestionAttempt).filter_by(id=attempt_id).first()
        if (not existing or existing.student_id != identity.student_id
                or existing.session_id != session_id
                or existing.question_id != payload.question_id
                or existing.chosen_answer != payload.chosen_answer):
            raise HTTPException(409, "We couldn’t record that answer. Please try again.") from None
        result = _answer_response(db, existing)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    result["session"] = _session_view(db, session_id)
    return result


@router.post("/practice/sessions/{session_id}/retry")
def retry_practice_question(
    session_id: str,
    identity: LearnerIdentity = Depends(get_current_learner),
    db: Session = Depends(get_db),
):
    from src.learning.session import retry_current

    _owned_session(db, identity.student_id, session_id)
    try:
        result = retry_current(db, session_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"hint": result.get("hint", ""), "session": _session_view(db, session_id)}


@router.post("/practice/sessions/{session_id}/complete")
def complete_practice_session(
    session_id: str,
    identity: LearnerIdentity = Depends(get_current_learner),
    db: Session = Depends(get_db),
):
    from src.learning.session import complete_session, session_results

    session = _owned_session(db, identity.student_id, session_id)
    try:
        if session.state == "complete":
            return session_results(db, session_id)
        return complete_session(db, session_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/practice/sessions/{session_id}/abandon")
def abandon_practice_session(
    session_id: str,
    identity: LearnerIdentity = Depends(get_current_learner),
    db: Session = Depends(get_db),
):
    from src.learning.session import abandon_session

    _owned_session(db, identity.student_id, session_id)
    try:
        return abandon_session(db, session_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
