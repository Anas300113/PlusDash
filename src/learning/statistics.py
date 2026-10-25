"""Deterministic learning statistics derived from existing evidence.

Uses the existing model only:
  * ``LearningQuestionAttempt`` - evidence
  * ``LearningTopicMastery`` / ``LearningSkillMastery`` - aggregates
  * ``LearningReviewItem``      - review scheduling state
  * ``LearningStudySession``    - session volume and mock results

Accuracy counts only attempts whose ``action`` is ``answer`` or ``retry``.
Skips are reported separately: a skip is a behaviour signal, not a wrong
answer, and must not distort mastery. No vanity metrics and no psychological
claims - every number here is a direct count or ratio of stored rows.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from src.core.database import (
    LearningQuestionAttempt, LearningReviewItem, LearningSkillMastery,
    LearningStudySession, LearningTopicMastery, QuestionReviewStatus, utcnow,
)
from src.learning.queries import question_map
from src.learning.review import review_summary

MEASURED_ACTIONS = ("answer", "retry")
MIN_ATTEMPTS_FOR_WEAK = 3
WEAK_THRESHOLD = 0.6


def _accuracy(correct: int, total: int) -> float:
    return (correct / total) if total else 0.0


def _aggregate(pairs) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key, correct in pairs:
        if key in (None, ""):
            continue
        bucket = out.setdefault(key, {"attempted": 0, "correct": 0,
                                      "accuracy": 0.0})
        bucket["attempted"] += 1
        bucket["correct"] += 1 if correct else 0
    for bucket in out.values():
        bucket["accuracy"] = _accuracy(bucket["correct"], bucket["attempted"])
    return out


def _attempts(db: Session, student_id: str) -> list[LearningQuestionAttempt]:
    return (db.query(LearningQuestionAttempt)
            .filter_by(student_id=student_id)
            .order_by(LearningQuestionAttempt.created_at).all())


def attempt_totals(attempts) -> dict:
    measured = [a for a in attempts if a.action in MEASURED_ACTIONS]
    skipped = [a for a in attempts if a.action == "skip"]
    total_time = sum(a.time_taken_ms or 0 for a in measured)
    return {
        "attempts": len(attempts),
        "answered": len(measured),
        "correct": sum(1 for a in measured if a.is_correct),
        "incorrect": sum(1 for a in measured if not a.is_correct),
        "skipped": len(skipped),
        "retries": sum(1 for a in attempts if a.action == "retry"),
        "hints_used": sum(1 for a in attempts if a.hint_used),
        "accuracy": _accuracy(sum(1 for a in measured if a.is_correct),
                              len(measured)),
        "total_time_ms": total_time,
        "avg_time_ms": int(total_time / len(measured)) if measured else 0,
    }


def mastery_rows(db: Session, student_id: str) -> dict:
    """Educational state, read straight from the aggregate tables."""
    topics = (db.query(LearningTopicMastery)
              .filter_by(student_id=student_id).all())
    skills = (db.query(LearningSkillMastery)
              .filter_by(student_id=student_id).all())
    return {
        "topic_mastery": [
            {"topic": m.topic_id, "accuracy": m.accuracy,
             "times_practiced": m.times_practiced,
             "times_correct": m.times_correct,
             "last_practiced_at": m.last_practiced_at.isoformat()
             if m.last_practiced_at else ""} for m in topics],
        "skill_mastery": [
            {"skill": m.skill_id, "topic": m.topic_id, "subject": m.subject,
             "accuracy": m.accuracy, "times_practiced": m.times_practiced,
             "times_correct": m.times_correct,
             "last_practiced_at": m.last_practiced_at.isoformat()
             if m.last_practiced_at else ""} for m in skills],
    }


def filter_weak_topics(mastery: list[dict],
                       min_attempts: int = MIN_ATTEMPTS_FOR_WEAK,
                       threshold: float = WEAK_THRESHOLD) -> list[dict]:
    return sorted(
        [m for m in mastery
         if m["times_practiced"] >= min_attempts and m["accuracy"] < threshold],
        key=lambda m: m["accuracy"])


def filter_weak_skills(mastery: list[dict],
                       min_attempts: int = MIN_ATTEMPTS_FOR_WEAK,
                       threshold: float = WEAK_THRESHOLD) -> list[dict]:
    return sorted(
        [m for m in mastery
         if m["times_practiced"] >= min_attempts and m["accuracy"] < threshold],
        key=lambda m: m["accuracy"])


def repeated_mistakes(db: Session, student_id: str,
                      min_wrong: int = 2) -> list[dict]:
    """Questions this student has got wrong more than once (excluding skips)."""
    attempts = _attempts(db, student_id)
    questions = question_map(db, [a.question_id for a in attempts])
    wrong: dict[str, dict] = {}
    for a in attempts:
        if a.action not in MEASURED_ACTIONS or a.is_correct:
            continue
        entry = wrong.setdefault(a.question_id, {"question_id": a.question_id,
                                                 "wrong": 0})
        entry["wrong"] += 1
    rows = []
    for question_id, entry in wrong.items():
        if entry["wrong"] < min_wrong:
            continue
        question = questions.get(question_id)
        rows.append({
            "question_id": question_id,
            "wrong": entry["wrong"],
            "topic": question.topic if question else "",
            "subject": question.subject if question else "",
            "question_text": question.question_text[:200] if question else "",
        })
    return sorted(rows, key=lambda r: (-r["wrong"], r["question_id"]))


def practice_volume(db: Session, student_id: str, days: int = 14) -> list[dict]:
    """Attempts per day - an activity count, not a mastery measure."""
    attempts = _attempts(db, student_id)
    today = utcnow().date()
    window = [today - timedelta(days=offset)
              for offset in range(days - 1, -1, -1)]
    counts = {day.isoformat(): 0 for day in window}
    for a in attempts:
        if a.created_at is None:
            continue
        key = a.created_at.date().isoformat()
        if key in counts:
            counts[key] += 1
    return [{"date": k, "attempts": v} for k, v in counts.items()]


def session_history(db: Session, student_id: str,
                    session_type: str | None = None) -> list[dict]:
    """Session-level view; mock sessions are the source of mock results."""
    query = db.query(LearningStudySession).filter_by(student_id=student_id)
    if session_type:
        query = query.filter(LearningStudySession.session_type == session_type)
    rows = query.order_by(LearningStudySession.started_at).all()
    out = []
    for s in rows:
        attempts = (db.query(LearningQuestionAttempt)
                    .filter_by(session_id=s.id).all())
        measured = [a for a in attempts if a.action in MEASURED_ACTIONS]
        out.append({
            "session_id": s.id,
            "session_type": s.session_type,
            "state": s.state,
            "started_at": s.started_at.isoformat() if s.started_at else "",
            "planned_duration_seconds": s.planned_duration_seconds,
            "actual_duration_seconds": s.actual_duration_seconds,
            "answered": len(measured),
            "correct": sum(1 for a in measured if a.is_correct),
            "accuracy": _accuracy(sum(1 for a in measured if a.is_correct),
                                  len(measured)),
        })
    return out


def student_statistics(db: Session, student_id: str, recent_window: int = 20,
                       days: int = 14) -> dict:
    """Everything the student/parent views need, from one query per table."""
    attempts = _attempts(db, student_id)
    questions = question_map(db, [a.question_id for a in attempts])
    measured = [a for a in attempts if a.action in MEASURED_ACTIONS]

    def question_of(attempt):
        return questions.get(attempt.question_id)

    pairs = [(a, question_of(a)) for a in measured]
    by_subject = _aggregate(
        (q.subject if q else "", a.is_correct) for a, q in pairs)
    by_topic = _aggregate(
        (q.topic if q else "", a.is_correct) for a, q in pairs)
    by_question_type = _aggregate(
        (q.question_type if q else "", a.is_correct) for a, q in pairs)
    by_difficulty = _aggregate(
        (str(q.difficulty) if q and q.difficulty else "", a.is_correct)
        for a, q in pairs)
    by_skill = _aggregate(
        (skill, a.is_correct)
        for a, q in pairs
        for skill in ((q.skill_ids or []) if q else []))

    mastery = mastery_rows(db, student_id)
    totals = attempt_totals(attempts)
    recent = measured[-recent_window:]
    recent_accuracy = _accuracy(sum(1 for a in recent if a.is_correct),
                                len(recent))
    return {
        "student_id": student_id,
        "totals": totals,
        "by_subject": by_subject,
        "by_topic": by_topic,
        "by_question_type": by_question_type,
        "by_difficulty": by_difficulty,
        "by_skill": by_skill,
        "recent": {
            "window": len(recent),
            "accuracy": recent_accuracy,
            "trend": round(recent_accuracy - totals["accuracy"], 4),
        },
        "repeated_mistakes": repeated_mistakes(db, student_id),
        "weak_topics": filter_weak_topics(mastery["topic_mastery"]),
        "weak_skills": filter_weak_skills(mastery["skill_mastery"]),
        "practice_volume": practice_volume(db, student_id, days=days),
        "review": review_summary(db, student_id),
        "sessions": session_history(db, student_id),
        "mock_results": session_history(db, student_id, session_type="mock"),
        "topic_mastery": mastery["topic_mastery"],
        "skill_mastery": mastery["skill_mastery"],
    }


def question_performance(db: Session, question_id: str) -> dict:
    """System view of one question. Indicative only, never student-facing."""
    attempts = (db.query(LearningQuestionAttempt)
                .filter_by(question_id=question_id).all())
    measured = [a for a in attempts if a.action in MEASURED_ACTIONS]
    status = db.query(QuestionReviewStatus).filter_by(
        question_id=question_id).first()
    times = [a.time_taken_ms or 0 for a in measured]
    return {
        "question_id": question_id,
        "validation_status": status.status if status else "unknown",
        "attempts": len(attempts),
        "answered": len(measured),
        "correct": sum(1 for a in measured if a.is_correct),
        "skipped": sum(1 for a in attempts if a.action == "skip"),
        "error_rate": round(1 - _accuracy(
            sum(1 for a in measured if a.is_correct), len(measured)), 4),
        "avg_time_ms": int(sum(times) / len(times)) if times else 0,
        "distinct_students": len({a.student_id for a in measured}),
        "discrimination_index": discrimination_index(db, question_id),
    }


def discrimination_index(db: Session, question_id: str,
                         min_students: int = 4) -> float | None:
    """Indicative upper/lower group difference - NOT a psychometric claim.

    Returns ``None`` until at least ``min_students`` students have answered,
    because below that the number is noise. Full item analysis is deferred.
    """
    attempts = (db.query(LearningQuestionAttempt)
                .filter_by(question_id=question_id).all())
    measured = [a for a in attempts if a.action in MEASURED_ACTIONS]
    students = sorted({a.student_id for a in measured})
    if len(students) < min_students:
        return None
    overall = {}
    for student_id in students:
        rows = [a for a in _attempts(db, student_id)
                if a.action in MEASURED_ACTIONS]
        overall[student_id] = _accuracy(
            sum(1 for a in rows if a.is_correct), len(rows))
    ranked = sorted(students, key=lambda s: overall[s])
    group = max(1, len(ranked) // 3)
    lower, upper = ranked[:group], ranked[-group:]

    def group_accuracy(group_ids) -> float:
        rows = [a for a in measured if a.student_id in group_ids]
        return _accuracy(sum(1 for a in rows if a.is_correct), len(rows))

    return round(group_accuracy(upper) - group_accuracy(lower), 4)


def system_statistics(db: Session, limit: int = 50) -> dict:
    """Content-health view: hardest questions, error rates, validation state."""
    rows = db.query(QuestionReviewStatus).all()
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    question_ids = [r.question_id for r in rows][:limit]
    performance = [question_performance(db, qid) for qid in question_ids]
    performance = [p for p in performance if p["answered"]]
    hardest = sorted(performance, key=lambda p: -p["error_rate"])[:10]
    most_skipped = sorted(performance, key=lambda p: -p["skipped"])[:10]
    return {
        "questions_total": len(rows),
        "validation_status_counts": by_status,
        "attempts_total": db.query(LearningQuestionAttempt).count(),
        "hardest_questions": hardest,
        "most_skipped_questions": most_skipped,
        "questions_with_attempts": len(performance),
    }