"""Parent dashboard aggregation: practice completed, subject/topic
performance, recent activity, weak areas, weekly activity, review
completion, mock results and next steps.

Deterministic queries over stored evidence only. Engagement metrics (XP,
streaks, badges) deliberately do not appear here: they are not learning state
and remain deferred behind feature flags.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.learning.statistics import student_statistics
from src.learning.weak_area import open_recommendations


def parent_summary(session: Session, student_id: str) -> dict:
    stats = student_statistics(session, student_id)
    totals = stats["totals"]
    attempts = student_attempts(session, student_id)

    by_subject = {
        subject: {"attempted": row["attempted"], "correct": row["correct"],
                  "accuracy": row["accuracy"]}
        for subject, row in stats["by_subject"].items()
    }
    weak = [{"topic": row["topic"], "accuracy": row["accuracy"],
             "practiced": row["times_practiced"]}
            for row in stats["weak_topics"]]
    recent = [{"question_id": a.question_id, "correct": a.is_correct,
               "at": a.created_at.isoformat() if a.created_at else ""}
              for a in attempts[-10:]]
    weekly = stats["practice_volume"][-7:]
    next_steps = [r["summary"]
                  for r in open_recommendations(session, student_id)]
    if not next_steps:
        next_steps = [f"Practise {w['topic']} "
                      f"({round(w['accuracy'] * 100)}% accuracy)"
                      for w in weak[:3]]
    if not next_steps:
        review = stats["review"]
        if review["total"]:
            next_steps = [
                f"Review {review['total']} item(s) - "
                f"{review['due_now']} due now, "
                f"{review['upcoming']} scheduled for later"]
    if not next_steps:
        next_steps = ["Keep practicing - no weak areas detected yet"]
    return {
        "student_id": student_id,
        "practice_completed": len(attempts),
        "questions_answered": totals["answered"],
        "practice_hours": round(totals["total_time_ms"] / 3600000, 2),
        "subject_performance": by_subject,
        "topic_performance": stats["by_topic"],
        "skill_performance": stats["by_skill"],
        "weak_areas": weak,
        "weak_skills": [{"skill": row["skill"], "topic": row["topic"],
                         "accuracy": row["accuracy"],
                         "practiced": row["times_practiced"]}
                        for row in stats["weak_skills"]],
        "recent_activity": recent,
        "weekly_activity": {"days": weekly,
                            "attempts": sum(day["attempts"] for day in weekly)},
        "review_completion": stats["review"],
        "mock_results": stats["mock_results"],
        "sessions": stats["sessions"],
        "recommended_next_steps": next_steps,
    }


def student_attempts(session: Session, student_id: str) -> list:
    """All attempt rows (including skips) for activity reporting."""
    from src.core.database import LearningQuestionAttempt
    return (session.query(LearningQuestionAttempt)
            .filter_by(student_id=student_id)
            .order_by(LearningQuestionAttempt.created_at).all())
