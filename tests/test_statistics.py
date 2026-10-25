"""Learning statistics: mastery aggregation, weak areas, skill mastery,
question-type/difficulty breakdowns, repeated mistakes, review completion.
Only deterministic counts and ratios of stored evidence - skips excluded
from accuracy by design. No FSRS, no vanity metrics."""
from __future__ import annotations

import uuid

from src.core.database import (
    CanonicalQuestion, LearningQuestionAttempt, LearningSkillMastery,
    LearningStudent, LearningStudySession, LearningTopicMastery,
    QuestionReviewStatus,
)
from src.learning.statistics import (
    attempt_totals, filter_weak_topics, question_performance,
    repeated_mistakes, student_statistics, system_statistics,
)
from src.learning.weak_area import (
    refresh_mastery, refresh_skill_mastery, refresh_topic_mastery,
    weak_skills, weak_topics,
)


def _question(session, index, topic="maths-arithmetic", subject="maths",
              qtype="mcq", difficulty=None, skills=("sk-add",),
              approve=True):
    q = CanonicalQuestion(
        id=f"sq{index}-{uuid.uuid4().hex[:6]}", subject=subject, topic=topic,
        question_type=qtype, difficulty=difficulty,
        question_text=f"Q{index}", correct_answer="B",
        options_json=[{"letter": "A", "text": "1"},
                      {"letter": "B", "text": "2"}],
        skill_ids=list(skills) if skills else [])
    session.add(q)
    session.flush()
    if approve:
        session.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    session.commit()
    return q


def _student(session, student_id=None):
    row = LearningStudent(id=student_id or str(uuid.uuid4()), name="S")
    session.add(row)
    session.commit()
    return row.id


def _session(session, student_id, session_type="practice"):
    row = LearningStudySession(id=str(uuid.uuid4()), student_id=student_id,
                               session_type=session_type)
    session.add(row)
    session.commit()
    return row


def _attempt(session, student_id, session_id, question, *, correct,
             action="answer", time_ms=1000, attempt_number=1):
    row = LearningQuestionAttempt(
        id=str(uuid.uuid4()), student_id=student_id, session_id=session_id,
        question_id=question.id if hasattr(question, "id") else question,
        chosen_answer="B" if correct else "A", is_correct=correct,
        action=action, time_taken_ms=time_ms, attempt_number=attempt_number)
    session.add(row)
    session.commit()
    return row


def test_attempt_totals_exclude_skips_from_accuracy(session):
    student = _student(session)
    srow = _session(session, student)
    q = _question(session, 1)
    _attempt(session, student, srow.id, q, correct=True, time_ms=800)
    _attempt(session, student, srow.id, q, correct=False, action="skip")
    totals = attempt_totals(session.query(LearningQuestionAttempt).all())
    assert totals["answered"] == 1
    assert totals["skipped"] == 1
    assert totals["accuracy"] == 1.0
    assert totals["avg_time_ms"] == 800
    assert totals["correct"] == 1 and totals["incorrect"] == 0


def test_refresh_topic_mastery_ignores_skips_and_stamps_recency(session):
    student = _student(session)
    srow = _session(session, student)
    q = _question(session, 1)
    _attempt(session, student, srow.id, q, correct=True)
    _attempt(session, student, srow.id, q, correct=False, action="skip")
    touched = refresh_topic_mastery(session, student)
    assert touched == 1
    row = session.query(LearningTopicMastery).one()
    assert row.times_practiced == 1      # skip did not count
    assert row.times_correct == 1
    assert row.accuracy == 1.0
    assert row.last_practiced_at is not None


def test_refresh_skill_mastery_uses_question_skill_ids(session):
    student = _student(session)
    srow = _session(session, student)
    q = _question(session, 1, skills=("sk-add", "sk-carry"))
    _attempt(session, student, srow.id, q, correct=False)
    _attempt(session, student, srow.id, q, correct=False)
    touched = refresh_skill_mastery(session, student)
    assert touched == 2
    rows = session.query(LearningSkillMastery).all()
    assert {r.skill_id for r in rows} == {"sk-add", "sk-carry"}
    assert all(r.accuracy == 0.0 and r.times_practiced == 2 for r in rows)


def test_weak_topics_respect_min_attempts_and_threshold(session):
    student = _student(session)
    srow = _session(session, student)
    weak_q = _question(session, 1)
    for _ in range(4):
        _attempt(session, student, srow.id, weak_q, correct=False)
    refresh_mastery(session, student)
    weak = weak_topics(session, student)
    assert len(weak) == 1 and weak[0].accuracy == 0.0
    # 2 attempts is not enough evidence to call a topic weak
    fresh = _student(session)
    fresh_session = _session(session, fresh)
    _attempt(session, fresh, fresh_session.id, weak_q, correct=False)
    _attempt(session, fresh, fresh_session.id, weak_q, correct=False)
    refresh_mastery(session, fresh)
    assert weak_topics(session, fresh) == []
    assert weak_skills(session, fresh) == []


def test_weak_skills_surface_skill_level_gaps(session):
    student = _student(session)
    srow = _session(session, student)
    q = _question(session, 1, skills=("sk-rotation",))
    for _ in range(3):
        _attempt(session, student, srow.id, q, correct=False)
    refresh_mastery(session, student)
    weak = weak_skills(session, student)
    assert len(weak) == 1
    assert weak[0].skill_id == "sk-rotation"
    assert weak[0].topic_id == "maths-arithmetic"


def test_student_statistics_breakdowns(session):
    student = _student(session)
    srow = _session(session, student)
    maths = _question(session, 1, subject="maths", topic="maths-arithmetic",
                      qtype="mcq", difficulty=2, skills=("sk-add",))
    vr = _question(session, 2, subject="vr", topic="vr-synonyms",
                   qtype="synonyms", difficulty=3, skills=("sk-vocab",))
    _attempt(session, student, srow.id, maths, correct=True)
    _attempt(session, student, srow.id, maths, correct=False)
    _attempt(session, student, srow.id, maths, correct=False)  # 1/3 -> weak
    _attempt(session, student, srow.id, vr, correct=True)
    refresh_mastery(session, student)
    stats = student_statistics(session, student)
    assert stats["totals"]["answered"] == 4
    assert abs(stats["by_subject"]["maths"]["accuracy"] - 1 / 3) < 1e-9
    assert stats["by_subject"]["vr"]["accuracy"] == 1.0
    assert stats["by_topic"]["maths-arithmetic"]["attempted"] == 3
    assert stats["by_question_type"]["synonyms"]["correct"] == 1
    assert stats["by_difficulty"]["3"]["accuracy"] == 1.0
    assert stats["by_skill"]["sk-add"]["attempted"] == 3
    assert stats["recent"]["window"] == 4
    assert stats["weak_topics"][0]["topic"] == "maths-arithmetic"


def test_repeated_mistakes_flag_questions_wrong_more_than_once(session):
    student = _student(session)
    srow = _session(session, student)
    flaky = _question(session, 1)
    other = _question(session, 2)
    _attempt(session, student, srow.id, flaky, correct=False)
    _attempt(session, student, srow.id, flaky, correct=False)
    _attempt(session, student, srow.id, other, correct=False)
    rows = repeated_mistakes(session, student, min_wrong=2)
    assert len(rows) == 1
    assert rows[0]["question_id"] == flaky.id
    assert rows[0]["wrong"] == 2
    assert rows[0]["topic"] == "maths-arithmetic"


def test_session_history_separates_mocks(session):
    student = _student(session)
    practice = _session(session, student, session_type="practice")
    mock = _session(session, student, session_type="mock")
    q = _question(session, 1)
    _attempt(session, student, practice.id, q, correct=True)
    _attempt(session, student, mock.id, q, correct=False)
    stats = student_statistics(session, student)
    assert len(stats["sessions"]) == 2
    assert len(stats["mock_results"]) == 1
    assert stats["mock_results"][0]["session_type"] == "mock"
    assert stats["mock_results"][0]["accuracy"] == 0.0


def test_question_performance_reports_error_rate_and_discrimination(session):
    student = _student(session)
    srow = _session(session, student)
    q = _question(session, 1)
    _attempt(session, student, srow.id, q, correct=True)
    _attempt(session, student, srow.id, q, correct=False)
    perf = question_performance(session, q.id)
    assert perf["answered"] == 2
    assert perf["error_rate"] == 0.5
    assert perf["validation_status"] == "approved"
    # One student is not enough for a discrimination index: honest None.
    assert perf["discrimination_index"] is None


def test_system_statistics_reports_content_health(session):
    student = _student(session)
    srow = _session(session, student)
    q = _question(session, 1)
    _attempt(session, student, srow.id, q, correct=False)
    # a question still in the human-review queue carries a status row
    pending = _question(session, 2, approve=False)
    session.add(QuestionReviewStatus(question_id=pending.id,
                                     status="discovered", source="ingestion"))
    session.commit()
    stats = system_statistics(session)
    assert stats["questions_total"] == 2
    assert stats["validation_status_counts"]["approved"] == 1
    assert stats["validation_status_counts"]["discovered"] == 1
    assert stats["attempts_total"] == 1
    assert stats["hardest_questions"][0]["question_id"] == q.id


def test_filter_weak_topics_pure_function(session):
    rows = [{"topic": "a", "accuracy": 0.2, "times_practiced": 5},
            {"topic": "b", "accuracy": 0.9, "times_practiced": 5},
            {"topic": "c", "accuracy": 0.1, "times_practiced": 2}]
    assert [w["topic"] for w in filter_weak_topics(rows)] == ["a"]


def test_statistics_never_require_an_llm(session):
    import src.learning.statistics as module
    source = open(module.__file__, encoding="utf-8").read()
    assert "openai" not in source.lower()
    assert "anthropic" not in source.lower()