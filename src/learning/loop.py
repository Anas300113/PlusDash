"""The educational loop, assembled from existing pieces.

    LEARN -> PRACTISE -> ASSESS -> IDENTIFY ERROR -> EXPLAIN
          -> REVIEW -> RE-PRACTISE -> UPDATE MASTERY

Every step is a deterministic query over content that already exists
(canonical questions, curriculum, attempt evidence, review items). No LLM is
required at any step: the AI tutor and generator layers augment this loop,
they are not the loop.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.learning.queries import (
    approved_question_ids, curriculum_payload, explain_question, question_map,
)
from src.learning.review import due_review_items, review_summary
from src.learning.statistics import (
    MEASURED_ACTIONS, repeated_mistakes, session_history, student_statistics,
)
from src.learning.weak_area import (
    refresh_recommendations, weak_skills, weak_topics,
)

LOOP_STEPS = ("learn", "practise", "assess", "identify_error", "explain",
              "review", "re_practise", "update_mastery")

# The loop must remain useful without any model call; AI is augmentation.
AI_REQUIRED_FOR_LOOP = False


def explain(db: Session, question_id: str,
            chosen_answer: str | None = None) -> dict:
    """EXPLAIN step: stored explanation, hint, worked solution, mistakes."""
    question = question_map(db, [question_id]).get(question_id)
    if question is None:
        raise ValueError(f"unknown question {question_id}")
    return explain_question(db, question, chosen_answer=chosen_answer)


def identify_errors(db: Session, student_id: str) -> dict:
    """IDENTIFY ERROR step: repeated mistakes, weak topics and weak skills.

    Reports what the evidence shows. It does not claim to diagnose a
    misconception - misconception inference is AI-tutor territory (deferred).
    """
    weak_topic_rows = weak_topics(db, student_id)
    weak_skill_rows = weak_skills(db, student_id)
    repeated = repeated_mistakes(db, student_id)
    suggested_topics = []
    for row in weak_topic_rows[:3]:
        payload = curriculum_payload(db, row.topic_id)
        suggested_topics.append({
            "topic": row.topic_id,
            "accuracy": row.accuracy,
            "times_practiced": row.times_practiced,
            "topic_common_mistakes": payload["common_mistakes"],
        })
    return {
        "student_id": student_id,
        "repeated_mistakes": repeated,
        "weak_topics": [{"topic": r.topic_id, "accuracy": r.accuracy,
                         "times_practiced": r.times_practiced}
                        for r in weak_topic_rows],
        "weak_skills": [{"skill": r.skill_id, "topic": r.topic_id,
                         "accuracy": r.accuracy,
                         "times_practiced": r.times_practiced}
                        for r in weak_skill_rows],
        "suggested_topics": suggested_topics,
    }


def re_practice(db: Session, student_id: str, limit: int = 10,
                exclude_ids=None) -> dict:
    """RE-PRACTISE step: fresh approved questions for the weakest areas.

    Prefers different questions from the ones already missed so the student
    transfers the skill instead of memorising the item.
    """
    weak_topic_rows = weak_topics(db, student_id)
    topic_ids = [r.topic_id for r in weak_topic_rows[:3]]
    excluded = set(exclude_ids or [])
    if not excluded:
        excluded = {m["question_id"] for m in repeated_mistakes(db, student_id)}
    all_ids = approved_question_ids(db, limit=None)
    questions = question_map(db, all_ids)
    picked = [qid for qid in all_ids
              if qid not in excluded
              and (not topic_ids or questions[qid].topic in topic_ids)]
    if not picked:
        picked = [qid for qid in all_ids if qid not in excluded]
    return {"topic_ids": topic_ids, "question_ids": picked[:limit],
            "excluded_question_ids": sorted(excluded)}


def loop_snapshot(db: Session, student_id: str) -> dict:
    """The full LEARN -> ... -> UPDATE MASTERY view for one student."""
    stats = student_statistics(db, student_id)
    evidence = stats["totals"]
    errors = identify_errors(db, student_id)
    review = review_summary(db, student_id)

    learn_topics: list[dict] = []
    for entry in errors["weak_topics"][:2]:
        payload = curriculum_payload(db, entry["topic"])
        if payload["lessons"] or payload["worked_examples"]:
            learn_topics.append({"topic": entry["topic"],
                                 "accuracy": entry["accuracy"],
                                 "payload": payload})

    explain_ids = [m["question_id"] for m in errors["repeated_mistakes"][:5]]
    due = due_review_items(db, student_id, limit=10)

    return {
        "student_id": student_id,
        "loop": list(LOOP_STEPS),
        "learn": {"topics": learn_topics},
        "practise": {"question_ids": approved_question_ids(db, limit=10),
                     "completed_attempts": evidence["answered"]},
        "assess": {"accuracy": evidence["accuracy"],
                   "recent_accuracy": stats["recent"]["accuracy"],
                   "by_topic": stats["by_topic"],
                   "totals": evidence},
        "identify_error": errors,
        "explain": [explain(db, question_id) for question_id in explain_ids],
        "review": {"due_count": review["due_now"],
                   "due_question_ids": review["due_question_ids"],
                   "review_item_ids": [r.id for r in due],
                   "summary": review},
        "re_practise": re_practice(db, student_id, limit=10),
        "update_mastery": {"topic_mastery": stats["topic_mastery"],
                           "skill_mastery": stats["skill_mastery"],
                           "sessions": session_history(db, student_id)[-5:]},
        # Refreshed (not just read) so the stored recommendations stay in
        # step with current evidence; superseded history is preserved.
        "recommended_activities": refresh_recommendations(db, student_id),
    }


def loop_contract() -> dict:
    """Declares the loop's guarantees; used by tests and documentation."""
    return {
        "steps": list(LOOP_STEPS),
        "ai_required": AI_REQUIRED_FOR_LOOP,
        "measured_actions": list(MEASURED_ACTIONS),
        "evidence_table": "learning_question_attempts",
        "scheduling_table": "learning_review_items",
        "mastery_tables": ["learning_topic_mastery", "learning_skill_mastery"],
    }