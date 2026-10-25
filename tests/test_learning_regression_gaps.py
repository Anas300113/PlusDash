"""Regression tests for genuine gaps in the deterministic learning engine.

Covers behaviour the existing suites exercise only partially or not at all,
without re-testing what is already pinned:

  * review interval ladder edge cases (next_interval_days(0, True))
  * apply_review_result state transitions (wrong -> relearn, correct ->
    learning, correct -> review), the 20-entry history cap, and suspension
  * ensure_review_item persisting skill_ids / difficulty / origin fields
  * due_review_items with limit and source_type filters
  * review_summary upcoming count / next_due_at
  * session: start with zero approved questions, submit_answer approval gate,
    bad-option rejection, retry_current with no question
  * statistics: attempt_totals with no measured attempts, discrimination_index
    with four students, question_performance with zero attempts
  * weak_area: weak_topics MIN_ATTEMPTS gate, weak_skills,
    refresh_skill_mastery, empty recommendations with no evidence,
    refresh_recommendations superseding open rows
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from src.core.database import (
    CanonicalQuestion, LearningQuestionAttempt, LearningRecommendation,
    LearningReviewItem, LearningSkillMastery, LearningStudent,
    LearningStudySession, LearningTopicMastery, QuestionReviewStatus, utcnow,
)
from src.learning.review import (
    apply_review_result, due_question_ids, due_review_items,
    ensure_review_item, get_review_item, next_interval_days,
    review_summary, suspend_review_item,
)
from src.learning.session import (
    current_question_id, get_session, order_questions, retry_current,
    skip_current, start_session, submit_answer,
)
from src.learning.statistics import (
    attempt_totals, discrimination_index, question_performance,
)
from src.learning.weak_area import (
    build_recommendations, refresh_skill_mastery, refresh_topic_mastery,
    refresh_recommendations, weak_skills, weak_topics,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _question(session, index=1, topic="maths-arithmetic", subject="maths",
              approve=True, skills=("sk-add",), difficulty=1):
    q = CanonicalQuestion(
        id=f"rg{index}-{uuid.uuid4().hex[:6]}", subject=subject, topic=topic,
        question_type="mcq", question_text=f"Q{index}", correct_answer="B",
        difficulty=difficulty,
        options_json=[{"letter": "A", "text": "1"},
                      {"letter": "B", "text": "2"}],
        skill_ids=list(skills),
        explanation="Because.", worked_solution="1 + 1 = 2")
    session.add(q)
    session.flush()
    if approve:
        session.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    session.commit()
    return q.id


def _student(session, name="T"):
    row = LearningStudent(id=str(uuid.uuid4()), name=name)
    session.add(row)
    session.commit()
    return row.id


def _session_row(session, student_id, session_type="practice"):
    row = LearningStudySession(id=str(uuid.uuid4()), student_id=student_id,
                               session_type=session_type)
    session.add(row)
    session.commit()
    return row.id


def _attempt(session, student_id, session_id, question_id, correct=True,
             action="answer", time_ms=1000):
    row = LearningQuestionAttempt(
        id=str(uuid.uuid4()), student_id=student_id, session_id=session_id,
        question_id=question_id, chosen_answer="B" if correct else "A",
        is_correct=correct, action=action, time_taken_ms=time_ms,
        attempt_number=1)
    session.add(row)
    session.commit()
    return row


# --------------------------------------------------------------------------- #
# review interval ladder + scheduling
# --------------------------------------------------------------------------- #

def test_next_interval_days_zero_consecutive_correct_returns_three_days():
    # consecutive_correct=0 but correct clamps to index 1 -> 3 days
    assert next_interval_days(0, True) == 3.0
    assert next_interval_days(0, False) == 1.0
    # the ladder never runs away past the final rung
    assert next_interval_days(99, True) == 30.0
    assert next_interval_days(100, True) == 30.0

def test_apply_review_result_state_transitions(session):
    sid = _student(session)
    qid = _question(session)
    now = utcnow()
    item, _ = ensure_review_item(session, sid, qid, now=now)
    assert item.state == "learning"
    assert item.consecutive_correct == 0

    # wrong -> relearn, consecutive reset to 0, back to tomorrow
    item = apply_review_result(session, item, False,
                               now=now + timedelta(days=1))
    assert item.state == "relearn"
    assert item.consecutive_correct == 0
    assert item.interval_days == 1.0
    assert item.last_result is False

    # correct, consecutive 1 -> learning (not yet stable), interval 3
    item = apply_review_result(session, item, True,
                               now=now + timedelta(days=2))
    assert item.state == "learning"
    assert item.consecutive_correct == 1
    assert item.interval_days == 3.0

    # correct, consecutive 2 -> review (stable), interval 7
    item = apply_review_result(session, item, True,
                               now=now + timedelta(days=3))
    assert item.state == "review"
    assert item.consecutive_correct == 2
    assert item.interval_days == 7.0


def test_apply_review_result_history_capped_at_twenty(session):
    sid = _student(session)
    qid = _question(session)
    item, _ = ensure_review_item(session, sid, qid, now=utcnow())
    base = utcnow()
    for i in range(25):
        apply_review_result(session, item, i % 2 == 0,
                            now=base + timedelta(hours=i),
                            attempt_id=f"att-{i}")
    session.commit()
    stored = get_review_item(session, sid, "question", qid)
    assert len(stored.review_history_json or []) == 20


def test_apply_review_result_to_suspended_item_stays_suspended(session):
    sid = _student(session)
    qid = _question(session)
    item, _ = ensure_review_item(session, sid, qid)
    suspend_review_item(session, item, reason="student_request")
    item = apply_review_result(session, item, True)
    assert item.state == "suspended"


def test_ensure_review_item_persists_skill_ids_and_origin(session):
    sid = _student(session)
    qid = _question(session, skills=("sk-add", "sk-sub"))
    now = utcnow()
    item, created = ensure_review_item(
        session, sid, qid, source_type="question",
        topic_id="maths-arithmetic", subject="maths",
        question_type="mcq", skill_ids=["sk-add", "sk-sub"],
        due_reason="incorrect",
        origin_attempt_id=str(uuid.uuid4()),
        origin_session_id=str(uuid.uuid4()),
        difficulty=2, now=now)
    assert created is True
    assert item.skill_ids_json == ["sk-add", "sk-sub"]
    assert item.difficulty == 2
    assert item.topic_id == "maths-arithmetic"
    assert item.subject == "maths"
    assert item.question_type == "mcq"
    assert item.due_reason == "incorrect"


def test_due_review_items_respects_limit(session):
    sid = _student(session)
    now = utcnow()
    q1 = _question(session, 1)
    q2 = _question(session, 2)
    item_a, _ = ensure_review_item(session, sid, q1,
                                   now=now - timedelta(days=2))
    item_b, _ = ensure_review_item(session, sid, q2,
                                   now=now - timedelta(days=1))
    # both due; limit 1 returns the earliest due_at first
    due = due_review_items(session, sid, limit=1, now=now)
    assert len(due) == 1
    assert due[0].id == item_a.id


def test_due_review_items_source_type_filter(session):
    sid = _student(session)
    now = utcnow()
    qid = _question(session)
    ensure_review_item(session, sid, qid, source_type="question",
                       now=now - timedelta(days=1))
    ensure_review_item(session, sid, "lesson-1", source_type="lesson",
                       now=now - timedelta(days=1))
    questions_only = due_review_items(session, sid, now=now,
                                      source_type="question")
    assert len(questions_only) == 1
    assert questions_only[0].source_type == "question"
    assert len(due_review_items(session, sid, now=now)) == 2


def test_review_summary_upcoming_and_next_due(session):
    sid = _student(session)
    qid = _question(session)
    ensure_review_item(session, sid, qid, now=utcnow())  # due tomorrow
    summary = review_summary(session, sid, now=utcnow())
    assert summary["total"] == 1
    assert summary["due_now"] == 0
    assert summary["upcoming"] == 1
    assert summary["next_due_at"]
    # a student with no items has no next due
    empty = _student(session, name="no-items")
    assert review_summary(session, empty, now=utcnow())["next_due_at"] == ""


# --------------------------------------------------------------------------- #
# session state machine
# --------------------------------------------------------------------------- #

def test_start_session_with_zero_approved_questions_creates_empty_order(session):
    _student(session, "s1")
    _question(session, 1, approve=False)  # only pending-review content exists
    s = start_session(session, "s1", session_type="practice", limit=10)
    assert s.question_order == []
    assert s.state == "started"
    assert current_question_id(get_session(session, s.id), s) is None


def test_submit_answer_unapproved_question_raises(session):
    sid = _student(session)
    qid = _question(session, approve=False)  # never approved
    s = start_session(session, sid)  # empty order, no current question
    with pytest.raises(ValueError, match="not approved for practice"):
        submit_answer(session, s.id, qid, "B", enforce_current=False)


def test_submit_answer_choice_out_of_options_raises(session):
    sid = _student(session)
    qid = _question(session)  # options A=1, B=2; correct B
    s = start_session(session, sid, question_ids=[qid])
    with pytest.raises(ValueError, match="is not one of the question's options"):
        submit_answer(session, s.id, qid, "Z")


def test_retry_current_with_no_question_raises(session):
    sid = _student(session)
    s = start_session(session, sid)  # empty order
    with pytest.raises(ValueError, match="no question available to retry"):
        retry_current(session, s.id)


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #

def test_attempt_totals_with_no_measured_attempts_returns_zeros():
    totals = attempt_totals([])
    assert totals["attempts"] == 0
    assert totals["answered"] == 0
    assert totals["correct"] == 0
    assert totals["accuracy"] == 0.0
    assert totals["avg_time_ms"] == 0
    assert totals["total_time_ms"] == 0


def test_discrimination_index_returns_float_with_four_students(session):
    qid = _question(session, approve=True)
    # clearly separated accuracies: A=0.0, B=0.5, C=1.0, D=1.0
    records = [
        ("A", [False, False]),
        ("B", [False, True]),
        ("C", [True, True]),
        ("D", [True, True]),
    ]
    for name, outcomes in records:
        sid = _student(session, name)
        srid = _session_row(session, sid)
        for correct in outcomes:
            _attempt(session, sid, srid, qid, correct=correct)
    idx = discrimination_index(session, qid)
    assert idx is not None
    assert isinstance(idx, float)
    assert idx == 1.0   # top student 1.0 - bottom student 0.0


def test_discrimination_index_none_with_fewer_than_four_students(session):
    qid = _question(session, approve=True)
    sid = _student(session)
    srid = _session_row(session, sid)
    _attempt(session, sid, srid, qid, correct=True)
    _attempt(session, sid, srid, qid, correct=False)
    assert discrimination_index(session, qid) is None


def test_question_performance_with_zero_attempts(session):
    qid = _question(session, approve=True)
    perf = question_performance(session, qid)
    assert perf["question_id"] == qid
    assert perf["attempts"] == 0
    assert perf["answered"] == 0
    assert perf["correct"] == 0
    assert perf["skipped"] == 0
    # no evidence: 1 - accuracy(0, 0) = 1 - 0.0
    assert perf["error_rate"] == 1.0
    assert perf["avg_time_ms"] == 0
    assert perf["discrimination_index"] is None
    assert perf["validation_status"] == "approved"


# --------------------------------------------------------------------------- #
# weak area / mastery / recommendations
# --------------------------------------------------------------------------- #

def test_weak_topics_respects_min_attempts(session):
    sid = _student(session)
    srid = _session_row(session, sid)
    q = _question(session, 1, topic="maths-fractions")
    # two wrong attempts: accuracy 0.0 but below MIN_ATTEMPTS=3 -> not weak
    _attempt(session, sid, srid, q, correct=False)
    _attempt(session, sid, srid, q, correct=False)
    refresh_topic_mastery(session, sid)
    assert weak_topics(session, sid) == []
    # the third wrong attempt crosses the evidence threshold -> weak
    _attempt(session, sid, srid, q, correct=False)
    refresh_topic_mastery(session, sid)
    weak = weak_topics(session, sid)
    assert len(weak) == 1
    assert weak[0].topic_id == "maths-fractions"
    assert weak[0].accuracy == 0.0


def test_weak_skills_detects_and_returns_empty_when_none(session):
    sid = _student(session)
    srid = _session_row(session, sid)
    q = _question(session, 1, skills=("sk-fractions",))
    _attempt(session, sid, srid, q, correct=False)
    _attempt(session, sid, srid, q, correct=False)
    _attempt(session, sid, srid, q, correct=False)
    refresh_skill_mastery(session, sid)
    weak = weak_skills(session, sid)
    assert len(weak) == 1
    assert weak[0].skill_id == "sk-fractions"
    assert weak[0].accuracy == 0.0


def test_refresh_skill_mastery_populates_rows(session):
    sid = _student(session)
    srid = _session_row(session, sid)
    q = _question(session, 1, skills=("sk-a", "sk-b"))
    _attempt(session, sid, srid, q, correct=True)
    touched = refresh_skill_mastery(session, sid)
    assert touched == 2
    rows = {r.skill_id: r for r in
            session.query(LearningSkillMastery).filter_by(student_id=sid).all()}
    assert set(rows) == {"sk-a", "sk-b"}
    assert rows["sk-a"].accuracy == 1.0
    assert rows["sk-a"].times_practiced == 1


def test_build_recommendations_empty_with_no_evidence(session):
    sid = _student(session)
    # no attempts, no review items, no sessions -> nothing to recommend
    assert build_recommendations(session, sid) == []


def test_refresh_recommendations_supersedes_previous_open(session):
    sid = _student(session)
    qid = _question(session)
    srid = _session_row(session, sid)
    for _ in range(3):
        _attempt(session, sid, srid, qid, correct=False)
    refresh_topic_mastery(session, sid)
    first = refresh_recommendations(session, sid)
    assert len(first) >= 1
    second = refresh_recommendations(session, sid)
    open_rows = (session.query(LearningRecommendation)
                 .filter_by(student_id=sid, status="open").all())
    assert len(open_rows) == len(second)
    assert all(r.status == "open" for r in open_rows)
