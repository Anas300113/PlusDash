"""ReviewItem scheduling: what should be reviewed, and when.

This is a *deterministic interval ladder*, not FSRS. FSRS is deliberately
deferred until there is enough honest review data to justify it, and would be
swapped in behind :func:`next_interval_days` without touching any other table.

Division of responsibility (kept deliberately separate):
  * ``LearningQuestionAttempt``  - evidence: what the student actually did
  * ``LearningReviewItem``       - scheduling: what to review and when
  * ``LearningSkillMastery`` /
    ``LearningTopicMastery``     - learning state aggregates
  * ``LearningRecommendation``   - what to do next

Review items are created from evidence (a wrong answer or a skip) and are
rescheduled when the student practises them again. They never store content.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.core.database import LearningReviewItem, utcnow
from src.learning.queries import is_approved

# Transparent, deterministic and reviewable: index = consecutive correct
# reviews. FSRS would replace this function, not the schema.
INTERVAL_LADDER_DAYS: tuple[float, ...] = (1.0, 3.0, 7.0, 14.0, 30.0)
FIRST_INTERVAL_DAYS = INTERVAL_LADDER_DAYS[0]
STABLE_AFTER_CORRECT = 2

REVIEW_STATES = ("learning", "review", "relearn", "suspended")
SOURCE_TYPES = ("question", "lesson", "strategy", "worked_example",
                "common_mistake")


def next_interval_days(consecutive_correct: int, is_correct: bool) -> float:
    """Interval after a review event. Wrong answers always come back tomorrow."""
    if not is_correct:
        return FIRST_INTERVAL_DAYS
    index = min(max(consecutive_correct, 1), len(INTERVAL_LADDER_DAYS) - 1)
    return INTERVAL_LADDER_DAYS[index]


def get_review_item(db: Session, student_id: str, source_type: str,
                    source_id: str) -> LearningReviewItem | None:
    return (db.query(LearningReviewItem)
            .filter_by(student_id=student_id, source_type=source_type,
                       source_id=source_id).first())


def ensure_review_item(db: Session, student_id: str, source_id: str,
                       source_type: str = "question", topic_id: str = "",
                       subject: str = "", question_type: str = "",
                       skill_ids=None, due_reason: str = "incorrect",
                       origin_attempt_id: str = "", origin_session_id: str = "",
                       difficulty: int | None = None,
                       now: datetime | None = None,
                       ) -> tuple[LearningReviewItem, bool]:
    """Idempotently create (or reschedule) the review item for a source.

    Returns ``(item, created)``. Re-running for the same student+source never
    creates a duplicate row because of the unique constraint; it reschedules
    instead, which is what makes the attempt path retry-safe.
    """
    now = now or utcnow()
    item = get_review_item(db, student_id, source_type, source_id)
    created = item is None
    due_at = now + timedelta(days=FIRST_INTERVAL_DAYS)
    if created:
        item = LearningReviewItem(
            id=str(uuid.uuid4()), student_id=student_id,
            source_type=source_type, source_id=source_id, subject=subject,
            topic_id=topic_id, question_type=question_type,
            skill_ids_json=list(skill_ids or []), state="learning",
            due_at=due_at, interval_days=FIRST_INTERVAL_DAYS,
            due_reason=due_reason, difficulty=difficulty,
            origin_attempt_id=origin_attempt_id,
            origin_session_id=origin_session_id, review_history_json=[])
        db.add(item)
    else:
        # A fresh failure resets the ladder: it is not yet stable knowledge.
        item.state = "learning" if item.consecutive_correct == 0 else "relearn"
        item.consecutive_correct = 0
        item.interval_days = FIRST_INTERVAL_DAYS
        item.due_at = due_at
        item.due_reason = due_reason
        item.last_result = False
        if origin_attempt_id:
            item.origin_attempt_id = origin_attempt_id
        if origin_session_id:
            item.origin_session_id = origin_session_id
        item.updated_at = now
    db.flush()
    return item, created



def apply_review_result(db: Session, item: LearningReviewItem, is_correct: bool,
                        attempt_id: str = "", now: datetime | None = None,
                        ) -> LearningReviewItem:
    """Reschedule a review item after the student attempts it again."""
    now = now or utcnow()
    item.review_count = (item.review_count or 0) + 1
    item.correct_count = (item.correct_count or 0) + (1 if is_correct else 0)
    if is_correct:
        item.consecutive_correct = (item.consecutive_correct or 0) + 1
    else:
        item.consecutive_correct = 0
    item.interval_days = next_interval_days(item.consecutive_correct, is_correct)
    item.due_at = now + timedelta(days=item.interval_days)
    item.last_reviewed_at = now
    item.last_result = is_correct
    if item.state != "suspended":
        item.state = ("review"
                      if item.consecutive_correct >= STABLE_AFTER_CORRECT
                      else "relearn" if not is_correct else "learning")
    item.due_reason = "review_schedule"
    history = list(item.review_history_json or [])
    history.append({"at": now.isoformat(), "correct": bool(is_correct),
                    "interval_days": item.interval_days,
                    "attempt_id": attempt_id})
    item.review_history_json = history[-20:]
    item.updated_at = now
    db.flush()
    return item


def suspend_review_item(db: Session, item: LearningReviewItem,
                        reason: str = "") -> LearningReviewItem:
    item.state = "suspended"
    item.due_reason = reason or "suspended"
    item.updated_at = utcnow()
    db.flush()
    return item


def due_review_items(db: Session, student_id: str, limit: int | None = None,
                     now: datetime | None = None,
                     source_type: str | None = None) -> list[LearningReviewItem]:
    """Due items, soonest first.

    Question items are filtered against ``QuestionReviewStatus == approved``:
    a question rejected during human review must never stay in a
    student-facing review queue.
    """
    now = now or utcnow()
    query = (db.query(LearningReviewItem)
             .filter(LearningReviewItem.student_id == student_id,
                     LearningReviewItem.state != "suspended",
                     LearningReviewItem.due_at.isnot(None),
                     LearningReviewItem.due_at <= now))
    if source_type:
        query = query.filter(LearningReviewItem.source_type == source_type)
    rows = query.order_by(LearningReviewItem.due_at).all()
    approved = [r for r in rows
                if r.source_type != "question" or is_approved(db, r.source_id)]
    return approved[:limit] if limit else approved


def due_question_ids(db: Session, student_id: str, limit: int | None = None,
                     now: datetime | None = None) -> list[str]:
    return [r.source_id for r in due_review_items(
        db, student_id, limit=limit, now=now, source_type="question")]


def review_summary(db: Session, student_id: str,
                   now: datetime | None = None) -> dict:
    now = now or utcnow()
    rows = db.query(LearningReviewItem).filter_by(student_id=student_id).all()
    by_state: dict[str, int] = {}
    for r in rows:
        by_state[r.state] = by_state.get(r.state, 0) + 1
    due = due_review_items(db, student_id, now=now)
    upcoming = [r for r in rows if r.due_at and r.due_at > now
                and r.state != "suspended"]
    next_due = min((r.due_at for r in upcoming), default=None)
    return {
        "total": len(rows),
        "by_state": by_state,
        "due_now": len(due),
        "due_question_ids": [r.source_id for r in due
                             if r.source_type == "question"],
        "upcoming": len(upcoming),
        "next_due_at": next_due.isoformat() if next_due else "",
        "completed_reviews": sum(r.review_count or 0 for r in rows),
    }