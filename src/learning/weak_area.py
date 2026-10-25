"""Mastery aggregation, weak-area detection and deterministic recommendations.

Owns three learning-layer responsibilities:
  * ``refresh_topic_mastery`` / ``refresh_skill_mastery`` - UPDATE MASTERY
  * ``weak_topics`` / ``weak_skills``                      - IDENTIFY WEAKNESS
  * ``refresh_recommendations``                            - WHAT TO DO NEXT

Deliberately transparent: accuracies are ratios of stored attempt evidence.
No forgetting-curve, confidence or item-response modelling yet - those need
real student data before they can be justified. Nothing here calls an LLM.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from src.core.database import (
    CanonicalQuestion, CurriculumLesson, LearningQuestionAttempt,
    LearningRecommendation, LearningSkillMastery, LearningStudySession,
    LearningTopicMastery, QuestionReviewStatus,
)

MEASURED_ACTIONS = ("answer", "retry")
WEAK_THRESHOLD = 0.6
MIN_ATTEMPTS = 3


def _measured_attempts(session: Session, student_id: str):
    """Evidence only: skips are behaviour, not answers, so they are excluded."""
    return [a for a in session.query(LearningQuestionAttempt)
            .filter_by(student_id=student_id).all()
            if a.action in MEASURED_ACTIONS]


def _questions(session: Session, question_ids) -> dict:
    ids = [q for q in question_ids if q]
    if not ids:
        return {}
    return {q.id: q for q in session.query(CanonicalQuestion)
            .filter(CanonicalQuestion.id.in_(ids)).all()}


def refresh_topic_mastery(session: Session, student_id: str) -> int:
    """Recompute topic mastery from attempt evidence. Returns topics touched."""
    attempts = _measured_attempts(session, student_id)
    if not attempts:
        return 0
    questions = _questions(session, {a.question_id for a in attempts})
    buckets: dict[str, dict] = {}
    for a in attempts:
        question = questions.get(a.question_id)
        if question is None:
            continue
        bucket = buckets.setdefault(question.topic,
                                    {"n": 0, "c": 0, "at": None})
        bucket["n"] += 1
        bucket["c"] += 1 if a.is_correct else 0
        if a.created_at and (bucket["at"] is None
                             or a.created_at > bucket["at"]):
            bucket["at"] = a.created_at
    for topic, bucket in buckets.items():
        row = session.query(LearningTopicMastery).filter_by(
            student_id=student_id, topic_id=topic).first()
        if row is None:
            row = LearningTopicMastery(student_id=student_id, topic_id=topic)
            session.add(row)
        row.accuracy = (bucket["c"] / bucket["n"]) if bucket["n"] else 0.0
        row.times_practiced = bucket["n"]
        row.times_correct = bucket["c"]
        row.last_practiced_at = bucket["at"]
    session.commit()
    return len(buckets)


def refresh_skill_mastery(session: Session, student_id: str) -> int:
    """Recompute skill mastery from question ``skill_ids``. Returns skills."""
    attempts = _measured_attempts(session, student_id)
    if not attempts:
        return 0
    questions = _questions(session, {a.question_id for a in attempts})
    buckets: dict[str, dict] = {}
    for a in attempts:
        question = questions.get(a.question_id)
        if question is None:
            continue
        for skill_id in (question.skill_ids or []):
            bucket = buckets.setdefault(skill_id, {
                "n": 0, "c": 0, "topic": question.topic,
                "subject": question.subject, "at": None})
            bucket["n"] += 1
            bucket["c"] += 1 if a.is_correct else 0
            if a.created_at and (bucket["at"] is None
                                 or a.created_at > bucket["at"]):
                bucket["at"] = a.created_at
    for skill_id, bucket in buckets.items():
        row = session.query(LearningSkillMastery).filter_by(
            student_id=student_id, skill_id=skill_id).first()
        if row is None:
            row = LearningSkillMastery(student_id=student_id,
                                       skill_id=skill_id)
            session.add(row)
        row.topic_id = bucket["topic"]
        row.subject = bucket["subject"]
        row.accuracy = (bucket["c"] / bucket["n"]) if bucket["n"] else 0.0
        row.times_practiced = bucket["n"]
        row.times_correct = bucket["c"]
        row.last_practiced_at = bucket["at"]
    session.commit()
    return len(buckets)


def refresh_mastery(session: Session, student_id: str) -> dict:
    """The loop's UPDATE MASTERY step: topics and skills, from evidence."""
    return {"topics": refresh_topic_mastery(session, student_id),
            "skills": refresh_skill_mastery(session, student_id)}


def weak_topics(session: Session, student_id: str,
                threshold: float = WEAK_THRESHOLD,
                min_attempts: int = MIN_ATTEMPTS) -> list:
    return (session.query(LearningTopicMastery)
            .filter_by(student_id=student_id)
            .filter(LearningTopicMastery.times_practiced >= min_attempts,
                    LearningTopicMastery.accuracy < threshold)
            .order_by(LearningTopicMastery.accuracy).all())


def weak_skills(session: Session, student_id: str,
                threshold: float = WEAK_THRESHOLD,
                min_attempts: int = MIN_ATTEMPTS) -> list:
    return (session.query(LearningSkillMastery)
            .filter_by(student_id=student_id)
            .filter(LearningSkillMastery.times_practiced >= min_attempts,
                    LearningSkillMastery.accuracy < threshold)
            .order_by(LearningSkillMastery.accuracy).all())


def _approved_question_ids(session: Session, topic_ids=None, limit=None):
    query = (session.query(CanonicalQuestion)
             .join(QuestionReviewStatus,
                   QuestionReviewStatus.question_id == CanonicalQuestion.id)
             .filter(QuestionReviewStatus.status == "approved"))
    if topic_ids:
        query = query.filter(CanonicalQuestion.topic.in_(topic_ids))
    rows = query.order_by(CanonicalQuestion.id).all()
    ids = [q.id for q in rows]
    return ids[:limit] if limit else ids


def build_recommendations(session: Session, student_id: str,
                          review_limit: int = 10,
                          practice_limit: int = 10) -> list[dict]:
    """Transparent, deterministic recommendations. No LLM, no psychology.

    Priority order:
      1. review   - due ReviewItems (retention of known-weak material)
      2. practice - weak topics / weak skills, approved questions only
      3. learn    - a weak topic that has curriculum but little practice
      4. catch_up - questions skipped in recent sessions
    Returns [] when there is no evidence yet - the platform never guesses.
    """
    from src.learning.review import due_review_items
    from src.core.database import LearningReviewItem

    out: list[dict] = []

    # 1. Due review items (scheduled for now or earlier)
    due = due_review_items(session, student_id, limit=review_limit)
    if due:
        topics = sorted({r.topic_id for r in due if r.topic_id})
        out.append({
            "kind": "review", "reason": "due_review_items",
            "summary": f"Review {len(due)} item(s) that are due today",
            "topic_ids": topics,
            "question_ids": [r.source_id for r in due
                             if r.source_type == "question"],
            "review_item_ids": [r.id for r in due],
        })

    # 2. Weak topics (need min_attempts evidence)
    weak = weak_topics(session, student_id)
    if weak:
        topic_ids = [w.topic_id for w in weak[:3]]
        out.append({
            "kind": "practice", "reason": "weak_topic",
            "summary": ("Practise " + ", ".join(
                f"{w.topic_id} ({round(w.accuracy * 100)}%)"
                for w in weak[:3])),
            "topic_ids": topic_ids,
            "question_ids": _approved_question_ids(
                session, topic_ids, practice_limit),
            "review_item_ids": [],
        })
        fresh = [w for w in weak if w.times_practiced < 5]
        if fresh:
            has_lesson = session.query(CurriculumLesson).filter(
                CurriculumLesson.topic_id == fresh[0].topic_id).first()
            if has_lesson is not None:
                out.append({
                    "kind": "learn", "reason": "curriculum_available",
                    "summary": (f"Study the {fresh[0].topic_id} lesson and "
                                "worked examples before more practice"),
                    "topic_ids": [fresh[0].topic_id],
                    "question_ids": [], "review_item_ids": [],
                })

    weak_skill_rows = weak_skills(session, student_id)
    if weak_skill_rows:
        skill = weak_skill_rows[0]
        out.append({
            "kind": "practice", "reason": "weak_skill",
            "summary": (f"Target skill {skill.skill_id} in {skill.topic_id} "
                        f"({round(skill.accuracy * 100)}% accuracy)"),
            "topic_ids": [skill.topic_id] if skill.topic_id else [],
            "question_ids": [], "review_item_ids": [],
        })

    recent_sessions = (session.query(LearningStudySession)
                       .filter_by(student_id=student_id)
                       .order_by(LearningStudySession.started_at.desc())
                       .limit(5).all())
    skipped = sorted({q for s in recent_sessions
                      for q in (s.skipped_ids_json or [])})
    if skipped:
        out.append({
            "kind": "catch_up", "reason": "skipped_questions",
            "summary": f"Return to {len(skipped)} skipped question(s)",
            "topic_ids": [], "question_ids": skipped[:practice_limit],
            "review_item_ids": [],
        })

    # 6. Recently-missed items not yet due (only when nothing else is
    # suggested - these are retention risks, not strong evidence of weakness)
    if not out:
        pending = (session.query(LearningReviewItem)
                   .filter_by(student_id=student_id)
                   .filter(LearningReviewItem.state.in_(("learning", "relearn")))
                   .order_by(LearningReviewItem.created_at.desc())
                   .limit(review_limit).all())
        if pending:
            topics = sorted({r.topic_id for r in pending if r.topic_id})
            out.append({
                "kind": "review", "reason": "recent_errors",
                "summary": (f"Follow up on {len(pending)} recently-missed "
                            "question(s) before they drift"),
                "topic_ids": topics,
                "question_ids": [r.source_id for r in pending
                                 if r.source_type == "question"],
                "review_item_ids": [r.id for r in pending],
            })
    return out


def refresh_recommendations(session: Session, student_id: str) -> list[dict]:
    """Replace open recommendations with the current deterministic set.

    Superseded recommendations are marked ``superseded`` rather than deleted so
    the history of what the platform suggested stays auditable.
    """
    for row in (session.query(LearningRecommendation)
                .filter_by(student_id=student_id, status="open").all()):
        row.status = "superseded"
    session.flush()

    built = build_recommendations(session, student_id)
    for item in built:
        session.add(LearningRecommendation(
            id=str(uuid.uuid4()), student_id=student_id,
            kind=item["kind"], reason=item["reason"], summary=item["summary"],
            status="open", question_ids_json=item["question_ids"],
            topic_ids_json=item["topic_ids"],
            review_item_ids_json=item["review_item_ids"]))
    session.commit()
    return built


def recommend(session: Session, student_id: str, limit: int = 10):
    """Backwards-compatible single recommendation (open, else freshly built)."""
    existing = (session.query(LearningRecommendation)
                .filter_by(student_id=student_id, status="open")
                .order_by(LearningRecommendation.created_at.desc()).first())
    if existing is not None:
        return existing
    built = refresh_recommendations(session, student_id)
    if not built:
        return None
    return (session.query(LearningRecommendation)
            .filter_by(student_id=student_id, status="open")
            .order_by(LearningRecommendation.created_at.desc()).first())


def open_recommendations(session: Session, student_id: str) -> list[dict]:
    """Open recommendations in the UI-facing shape used by session payloads."""
    rows = (session.query(LearningRecommendation)
            .filter_by(student_id=student_id, status="open")
            .order_by(LearningRecommendation.created_at.desc()).all())
    return [{"id": r.id, "kind": r.kind, "reason": r.reason,
             "summary": r.summary or r.reason,
             "question_ids": r.question_ids_json or [],
             "topic_ids": r.topic_ids_json or [],
             "review_item_ids": r.review_item_ids_json or []} for r in rows]