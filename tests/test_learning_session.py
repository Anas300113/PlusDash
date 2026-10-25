"""Session state machine: ordering, current question, answer, skip, retry,
completion, results and resume. Uses the existing evidence model only."""
from __future__ import annotations

import uuid

import pytest

from src.core.database import (
    CanonicalQuestion, LearningQuestionAttempt, LearningReviewItem,
    QuestionReviewStatus,
)
from src.learning.session import (
    SESSION_STATES, SESSION_TYPES, SessionState, abandon_session,
    complete_session, current_question_id, get_session, order_questions,
    retry_current, session_results, session_state, skip_current, start_session,
    submit_answer,
)


def _question(session, index, topic="maths-arithmetic", subject="maths",
              approve=True, skills=("sk-add",)):
    q = CanonicalQuestion(
        id=f"q{index}-{uuid.uuid4().hex[:6]}", subject=subject, topic=topic,
        question_type="mcq", question_text=f"Question {index}",
        correct_answer="B", hint="add them",
        options_json=[{"letter": "A", "text": "1"},
                      {"letter": "B", "text": "2"}],
        skill_ids=list(skills), explanation="Because 2 is correct.",
        worked_solution="1 + 1 = 2")
    session.add(q)
    session.flush()
    if approve:
        session.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    session.commit()
    return q.id


def _seed(session, count=3):
    return [_question(session, i) for i in range(count)]


def test_order_questions_is_deterministic_and_deduplicated():
    ids = ["a", "b", "c", "a"]
    assert order_questions(ids) == ["a", "b", "c"]
    shuffled = order_questions(ids, "shuffled", seed=7)
    assert shuffled == order_questions(ids, "shuffled", seed=7)
    assert sorted(shuffled) == ["a", "b", "c"]


def test_session_types_and_states_are_extensible_values():
    assert "review" in SESSION_TYPES and "mock" in SESSION_TYPES
    assert "planned" in SESSION_STATES and "abandoned" in SESSION_STATES


def test_start_session_freezes_order_and_excludes_unapproved(session):
    approved = _seed(session, 2)
    _question(session, 99, approve=False)  # pending review: not student-facing
    s = start_session(session, "s1", session_type="practice", limit=10)
    assert set(s.question_order) == set(approved)
    assert s.state == SessionState.STARTED.value
    assert s.completion_state == "in_progress"
    assert current_question_id(session, s) == s.question_order[0]
    assert s.progress == 0.0


def test_start_session_records_goals_and_planned_duration(session):
    _seed(session, 2)
    s = start_session(session, "s1", session_type="review", limit=5,
                      planned_duration_seconds=600,
                      goals={"topic": "maths-arithmetic", "min_accuracy": 0.8})
    assert s.session_type == "review"
    assert s.planned_duration_seconds == 600
    assert s.goals_json["topic"] == "maths-arithmetic"
    assert s.recommended_activities_json is not None


def test_start_session_rejects_unknown_type(session):
    with pytest.raises(ValueError):
        start_session(session, "s1", session_type="not_a_type")


def test_answer_advances_and_persists_evidence(session):
    ids = _seed(session, 2)
    s = start_session(session, "s1", question_ids=ids)
    out = submit_answer(session, s.id, ids[0], "B", time_taken_ms=1500)
    assert out["is_correct"] is True
    assert out["attempt_id"]
    assert out["session"]["index"] == 1
    assert out["session"]["current_question_id"] == ids[1]
    assert out["session"]["state"] == SessionState.IN_PROGRESS.value
    rows = session.query(LearningQuestionAttempt).all()
    assert len(rows) == 1 and rows[0].action == "answer"


def test_wrong_answer_creates_review_item(session):
    ids = _seed(session, 1)
    s = start_session(session, "s1", question_ids=ids)
    out = submit_answer(session, s.id, ids[0], "A")
    assert out["is_correct"] is False
    assert out["review_item_id"]
    item = session.query(LearningReviewItem).one()
    assert item.source_id == ids[0]
    assert item.topic_id == "maths-arithmetic"
    assert item.due_reason == "incorrect"
    assert item.interval_days == 1.0
    assert item.state == "learning"


def test_correct_answer_creates_no_review_item(session):
    ids = _seed(session, 1)
    s = start_session(session, "s1", question_ids=ids)
    submit_answer(session, s.id, ids[0], "B")
    assert session.query(LearningReviewItem).count() == 0


def test_answer_out_of_order_is_rejected(session):
    ids = _seed(session, 2)
    s = start_session(session, "s1", question_ids=ids)
    with pytest.raises(ValueError):
        submit_answer(session, s.id, ids[1], "B")


def test_non_approved_question_cannot_be_answered(session):
    pending = _question(session, 5, approve=False)
    s = start_session(session, "s1", question_ids=[pending])
    assert s.question_order == []  # filtered at session start
    with pytest.raises(ValueError):
        submit_answer(session, s.id, pending, "B")


def test_skip_records_evidence_and_schedules_review(session):
    ids = _seed(session, 1)
    s = start_session(session, "s1", question_ids=ids)
    out = skip_current(session, s.id, time_taken_ms=400)
    assert out["action"] == "skip"
    row = session.query(LearningQuestionAttempt).one()
    assert row.action == "skip" and row.chosen_answer == ""
    item = session.query(LearningReviewItem).one()
    assert item.due_reason == "skipped"
    assert get_session(session, s.id).skipped_ids_json == [ids[0]]


def test_retry_reopens_last_question_and_records_recovery(session):
    ids = _seed(session, 1)
    s = start_session(session, "s1", question_ids=ids)
    submit_answer(session, s.id, ids[0], "A")          # wrong -> review item
    reopened = retry_current(session, s.id)
    assert reopened["question_id"] == ids[0]
    assert reopened["hint"] == "add them"
    out = submit_answer(session, s.id, ids[0], "B", action="retry")
    assert out["is_correct"] is True
    rows = (session.query(LearningQuestionAttempt)
            .order_by(LearningQuestionAttempt.attempt_number).all())
    assert [r.attempt_number for r in rows] == [1, 2]
    assert rows[1].action == "retry"
    item = session.query(LearningReviewItem).one()
    assert item.consecutive_correct == 1
    assert item.interval_days == 3.0   # ladder step after a recovery


def test_complete_session_returns_results_and_refreshes_mastery(session):
    ids = _seed(session, 2)
    s = start_session(session, "s1", question_ids=ids,
                      planned_duration_seconds=300)
    submit_answer(session, s.id, ids[0], "B")
    submit_answer(session, s.id, ids[1], "A")
    results = complete_session(session, s.id)
    assert results["answered"] == 2
    assert results["correct"] == 1
    assert results["accuracy"] == 0.5
    assert results["by_topic"]["maths-arithmetic"]["attempted"] == 2
    assert results["mistakes"][0]["question_id"] == ids[1]
    assert results["planned_duration_seconds"] == 300
    assert "recommended_activities" in results
    assert get_session(session, s.id).state == SessionState.COMPLETE.value


def test_completed_session_rejects_further_answers(session):
    ids = _seed(session, 1)
    s = start_session(session, "s1", question_ids=ids)
    submit_answer(session, s.id, ids[0], "B")
    complete_session(session, s.id)
    with pytest.raises(ValueError):
        submit_answer(session, s.id, ids[0], "B")


def test_abandon_keeps_evidence(session):
    ids = _seed(session, 2)
    s = start_session(session, "s1", question_ids=ids)
    submit_answer(session, s.id, ids[0], "A")
    state = abandon_session(session, s.id)
    assert state["state"] == SessionState.ABANDONED.value
    assert state["resumable"] is False
    assert session.query(LearningQuestionAttempt).count() == 1


def test_session_state_supports_resume(session):
    ids = _seed(session, 3)
    s = start_session(session, "s1", question_ids=ids)
    submit_answer(session, s.id, ids[0], "B")
    resumed = session_state(session, s.id)
    assert resumed["index"] == 1
    assert resumed["total"] == 3
    assert resumed["questions_remaining"] == 2
    assert resumed["current_question_id"] == ids[1]
    assert resumed["current_question"]["id"] == ids[1]
    assert resumed["resumable"] is True
    assert resumed["attempt_count"] == 1


def test_skips_do_not_distort_accuracy(session):
    ids = _seed(session, 3)
    s = start_session(session, "s1", question_ids=ids)
    submit_answer(session, s.id, ids[0], "B")     # correct
    skip_current(session, s.id)
    skip_current(session, s.id)
    results = session_results(session, s.id)
    assert results["answered"] == 1 and results["skipped"] == 2
    assert results["accuracy"] == 1.0
    assert get_session(session, s.id).accuracy == 1.0


def test_unknown_session_raises(session):
    with pytest.raises(ValueError):
        get_session(session, "nope")