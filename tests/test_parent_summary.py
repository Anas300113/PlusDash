"""Parent dashboard aggregation (`src/learning/parent_summary.py`).

Every number here is a direct count or ratio of stored evidence - no LLM, no
vanity metrics, no psychological claims. These are the first dedicated tests
for this module: previously it had zero test coverage.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from src.core.database import (
    CanonicalQuestion,
    LearningQuestionAttempt,
    LearningRecommendation,
    LearningReviewItem,
    LearningStudent,
    LearningStudySession,
    QuestionReviewStatus,
    utcnow,
)
from src.learning.parent_summary import parent_summary
from src.learning.weak_area import refresh_skill_mastery, refresh_topic_mastery


def _question(session, index=1, topic="maths-arithmetic", subject="maths",
              skills=("sk-add",), approve=True):
    q = CanonicalQuestion(
        id=f"ps{index}-{uuid.uuid4().hex[:6]}", subject=subject, topic=topic,
        question_type="mcq", question_text=f"Question {index}",
        correct_answer="B", hint="add them",
        options_json=[{"letter": "A", "text": "1"},
                      {"letter": "B", "text": "2"}],
        skill_ids=list(skills), explanation="Because B is correct.",
        worked_solution="1 + 1 = 2")
    session.add(q)
    session.flush()
    if approve:
        session.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    session.commit()
    return q


def _student(session, student_id=None):
    row = LearningStudent(id=student_id or str(uuid.uuid4()), name="Pupil")
    session.add(row)
    session.commit()
    return row.id


def _study_session(session, student_id, session_type="practice"):
    row = LearningStudySession(id=str(uuid.uuid4()), student_id=student_id,
                               session_type=session_type)
    session.add(row)
    session.commit()
    return row


def _attempt(session, student_id, session_id, question, *, correct,
             action="answer", time_ms=1000, created_at=None):
    row = LearningQuestionAttempt(
        id=str(uuid.uuid4()), student_id=student_id, session_id=session_id,
        question_id=(question.id if hasattr(question, "id") else question),
        chosen_answer="B" if correct else "A", is_correct=correct,
        action=action, time_taken_ms=time_ms, attempt_number=1,
        created_at=created_at)
    session.add(row)
    session.commit()
    return row


def _review_item(session, student_id, source_id=None,
                 topic_id="maths-arithmetic", state="learning", due_at=None):
    row = LearningReviewItem(id=str(uuid.uuid4()), student_id=student_id,
                             source_type="question", source_id=source_id,
                             topic_id=topic_id, state=state, due_at=due_at)
    session.add(row)
    session.commit()
    return row


def _recommendation(session, student_id, kind="practice", reason="r",
                    summary="summary", status="open"):
    row = LearningRecommendation(id=str(uuid.uuid4()), student_id=student_id,
                                 kind=kind, reason=reason, summary=summary,
                                 status=status)
    session.add(row)
    session.commit()
    return row


def test_parent_summary_returns_complete_payload_shape(session):
    student = _student(session)
    srow = _study_session(session, student)
    q = _question(session, 1)
    _attempt(session, student, srow.id, q, correct=True)
    out = parent_summary(session, student)
    assert set(out) == {
        "student_id", "practice_completed", "questions_answered",
        "practice_hours", "subject_performance", "topic_performance",
        "skill_performance", "weak_areas", "weak_skills",
        "recent_activity", "weekly_activity", "review_completion",
        "mock_results", "sessions", "recommended_next_steps",
    }
    assert out["student_id"] == student


def test_parent_summary_practice_completed_includes_skips(session):
    """practice_completed counts every attempt; questions_answered excludes skips."""
    student = _student(session)
    srow = _study_session(session, student)
    q = _question(session, 1)
    _attempt(session, student, srow.id, q, correct=True)
    _attempt(session, student, srow.id, q, correct=False, action="skip")
    _attempt(session, student, srow.id, q, correct=False)
    out = parent_summary(session, student)
    assert out["practice_completed"] == 3
    assert out["questions_answered"] == 2


def test_parent_summary_practice_hours_from_total_time_ms(session):
    student = _student(session)
    srow = _study_session(session, student)
    q = _question(session, 1)
    _attempt(session, student, srow.id, q, correct=True, time_ms=1800000)  # 0.5 h
    out = parent_summary(session, student)
    assert out["practice_hours"] == 0.5


def test_parent_summary_subject_performance_from_stats(session):
    student = _student(session)
    srow = _study_session(session, student)
    q = _question(session, 1, subject="maths", topic="maths-arithmetic")
    _attempt(session, student, srow.id, q, correct=True)
    out = parent_summary(session, student)
    assert out["subject_performance"] == {
        "maths": {"attempted": 1, "correct": 1, "accuracy": 1.0}}


def test_parent_summary_topic_and_skill_performance_pass_through(session):
    student = _student(session)
    srow = _study_session(session, student)
    q = _question(session, 1, skills=("sk-add", "sk-mult"))
    _attempt(session, student, srow.id, q, correct=True)
    out = parent_summary(session, student)
    assert out["topic_performance"]["maths-arithmetic"]["attempted"] == 1
    assert out["skill_performance"]["sk-add"]["attempted"] == 1
    assert out["skill_performance"]["sk-mult"]["attempted"] == 1


def test_parent_summary_weak_areas_from_weak_topics(session):
    student = _student(session)
    srow = _study_session(session, student)
    q = _question(session, 1)
    for _ in range(3):
        _attempt(session, student, srow.id, q, correct=False)
    refresh_topic_mastery(session, student)
    out = parent_summary(session, student)
    assert out["weak_areas"] == [
        {"topic": "maths-arithmetic", "accuracy": 0.0, "practiced": 3}]


def test_parent_summary_weak_skills_from_weak_skills(session):
    student = _student(session)
    srow = _study_session(session, student)
    q = _question(session, 1, skills=("sk-add",))
    for _ in range(3):
        _attempt(session, student, srow.id, q, correct=False)
    refresh_skill_mastery(session, student)
    out = parent_summary(session, student)
    assert out["weak_skills"] == [
        {"skill": "sk-add", "topic": "maths-arithmetic",
         "accuracy": 0.0, "practiced": 3}]


def test_parent_summary_recent_activity_last_ten_attempts(session):
    student = _student(session)
    srow = _study_session(session, student)
    q = _question(session, 1)
    now = utcnow()
    for i in range(12):
        _attempt(session, student, srow.id, q, correct=(i % 2 == 0),
                 created_at=now + timedelta(seconds=i))
    out = parent_summary(session, student)
    assert len(out["recent_activity"]) == 10
    assert out["recent_activity"][0]["correct"] is True   # attempt i=2
    assert out["recent_activity"][-1]["correct"] is False  # attempt i=11
    assert all(set(a) == {"question_id", "correct", "at"}
               for a in out["recent_activity"])


def test_parent_summary_recent_activity_includes_skips(session):
    """student_attempts reports every attempt, skips included."""
    student = _student(session)
    srow = _study_session(session, student)
    q = _question(session, 1)
    now = utcnow()
    _attempt(session, student, srow.id, q, correct=True, created_at=now)
    _attempt(session, student, srow.id, q, correct=False, action="skip",
             created_at=now + timedelta(seconds=1))
    out = parent_summary(session, student)
    assert len(out["recent_activity"]) == 2
    assert out["recent_activity"][0]["correct"] is True
    assert out["recent_activity"][-1]["correct"] is False


def test_parent_summary_weekly_activity_covers_last_seven_days(session):
    student = _student(session)
    srow = _study_session(session, student)
    q = _question(session, 1)
    _attempt(session, student, srow.id, q, correct=True)
    out = parent_summary(session, student)
    weekly = out["weekly_activity"]
    assert len(weekly["days"]) == 7
    assert weekly["attempts"] == 1
    assert all(set(d) == {"date", "attempts"} for d in weekly["days"])


def test_parent_summary_review_completion_from_review_stats(session):
    student = _student(session)
    q = _question(session, 1)
    _review_item(session, student, source_id=q.id,
                 due_at=utcnow() - timedelta(days=1))  # due now
    out = parent_summary(session, student)
    rc = out["review_completion"]
    assert rc["total"] == 1
    assert rc["due_now"] == 1
    assert "upcoming" in rc


def test_parent_summary_mock_results_and_sessions_from_stats(session):
    student = _student(session)
    practice = _study_session(session, student, session_type="practice")
    mock = _study_session(session, student, session_type="mock")
    q = _question(session, 1)
    _attempt(session, student, practice.id, q, correct=True)
    _attempt(session, student, mock.id, q, correct=False)
    out = parent_summary(session, student)
    assert len(out["sessions"]) == 2
    assert len(out["mock_results"]) == 1
    assert out["mock_results"][0]["session_type"] == "mock"


def test_parent_summary_next_steps_from_open_recommendations(session):
    student = _student(session)
    _recommendation(session, student, kind="practice", reason="weak_topic",
                    summary="Practise fractions now")
    out = parent_summary(session, student)
    assert out["recommended_next_steps"] == ["Practise fractions now"]


def test_parent_summary_next_steps_falls_back_to_weak_topics(session):
    student = _student(session)
    srow = _study_session(session, student)
    q = _question(session, 1)
    for _ in range(3):
        _attempt(session, student, srow.id, q, correct=False)
    refresh_topic_mastery(session, student)
    out = parent_summary(session, student)
    assert out["recommended_next_steps"] == [
        "Practise maths-arithmetic (0% accuracy)"]


def test_parent_summary_next_steps_falls_back_to_review(session):
    student = _student(session)
    q = _question(session, 1)
    _review_item(session, student, source_id=q.id,
                 due_at=utcnow() - timedelta(days=1))  # due now
    out = parent_summary(session, student)
    assert out["recommended_next_steps"] == [
        "Review 1 item(s) - 1 due now, 0 scheduled for later"]


def test_parent_summary_next_steps_default_when_no_evidence(session):
    student = _student(session)
    out = parent_summary(session, student)
    assert out["recommended_next_steps"] == [
        "Keep practicing - no weak areas detected yet"]


def test_parent_summary_empty_student_sensible_defaults(session):
    student = _student(session)
    out = parent_summary(session, student)
    assert out["practice_completed"] == 0
    assert out["questions_answered"] == 0
    assert out["practice_hours"] == 0.0
    assert out["subject_performance"] == {}
    assert out["topic_performance"] == {}
    assert out["skill_performance"] == {}
    assert out["weak_areas"] == []
    assert out["weak_skills"] == []
    assert out["recent_activity"] == []
    assert out["weekly_activity"]["attempts"] == 0
    assert out["review_completion"]["total"] == 0
    assert out["mock_results"] == []
    assert out["sessions"] == []


def test_parent_summary_students_are_isolated(session):
    a = _student(session, "student-a")
    b = _student(session, "student-b")
    srow = _study_session(session, a)
    q = _question(session, 1)
    _attempt(session, a, srow.id, q, correct=True)
    out_a = parent_summary(session, a)
    out_b = parent_summary(session, b)
    assert out_a["questions_answered"] == 1
    assert out_b["questions_answered"] == 0
    assert out_b["recommended_next_steps"] == [
        "Keep practicing - no weak areas detected yet"]


def test_parent_summary_requires_no_llm():
    import src.learning.parent_summary as module
    source = open(module.__file__, encoding="utf-8").read()
    assert "openai" not in source.lower()
    assert "anthropic" not in source.lower()
