"""ReviewItem scheduling: deterministic ladder, idempotency, approved-only
due queue, suspension. FSRS is deliberately absent from these tests."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from src.core.database import (
    CanonicalQuestion, LearningQuestionAttempt, LearningReviewItem,
    LearningStudent, LearningStudySession, QuestionReviewStatus,
)
from src.learning.review import (
    FIRST_INTERVAL_DAYS, INTERVAL_LADDER_DAYS, STABLE_AFTER_CORRECT,
    apply_review_result, due_question_ids, due_review_items,
    ensure_review_item, get_review_item, next_interval_days, review_summary,
    suspend_review_item,
)


def _question(session, index=1, topic="maths-arithmetic", approve=True):
    q = CanonicalQuestion(
        id=f"rq{index}-{uuid.uuid4().hex[:6]}", subject="maths", topic=topic,
        question_type="mcq", question_text=f"Q{index}", correct_answer="B",
        options_json=[{"letter": "A", "text": "1"},
                      {"letter": "B", "text": "2"}], skill_ids=["sk-add"])
    session.add(q)
    session.flush()
    if approve:
        session.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    session.commit()
    return q.id


def _student(session, name="Tutorless Tim"):
    row = LearningStudent(id=str(uuid.uuid4()), name=name)
    session.add(row)
    session.commit()
    return row.id


def _student_with_session(session, student_id):
    row = LearningStudySession(id=str(uuid.uuid4()), student_id=student_id)
    session.add(row)
    session.commit()
    return row.id


def _attempt(session, student_id, session_id, question_id, correct=False):
    attempt = LearningQuestionAttempt(
        id=str(uuid.uuid4()), student_id=student_id, session_id=session_id,
        question_id=question_id, chosen_answer="A", is_correct=correct,
        action="answer")
    session.add(attempt)
    session.commit()
    return attempt


def test_interval_ladder_is_deterministic():
    assert FIRST_INTERVAL_DAYS == 1.0
    assert INTERVAL_LADDER_DAYS == (1.0, 3.0, 7.0, 14.0, 30.0)
    assert next_interval_days(0, False) == 1.0
    assert next_interval_days(1, True) == 3.0
    assert next_interval_days(2, True) == 7.0
    assert next_interval_days(3, True) == 14.0
    assert next_interval_days(99, True) == 30.0   # capped, never runaway
    assert next_interval_days(4, False) == 1.0    # wrong -> tomorrow again


def test_ensure_review_item_is_idempotent(session):
    sid = _student(session)
    qid = _question(session)
    item, created = ensure_review_item(
        session, sid, qid, topic_id="maths-arithmetic", due_reason="incorrect")
    assert created is True and item.state == "learning"
    again, created_again = ensure_review_item(session, sid, qid,
                                              due_reason="incorrect")
    assert created_again is False
    assert again.id == item.id
    assert session.query(LearningReviewItem).count() == 1
    assert again.consecutive_correct == 0
    assert again.interval_days == 1.0


def test_ensure_review_item_reschedules_after_previous_success(session):
    sid = _student(session)
    qid = _question(session)
    item, _ = ensure_review_item(session, sid, qid)
    apply_review_result(session, item, True)   # -> 3 days, consecutive 1
    apply_review_result(session, item, True)   # -> 7 days, stable/review
    item, created = ensure_review_item(session, sid, qid)
    assert created is False
    assert item.state == "relearn"
    assert item.consecutive_correct == 0
    assert item.interval_days == 1.0


def test_apply_review_result_promotes_to_review_state(session):
    sid = _student(session)
    qid = _question(session)
    item, _ = ensure_review_item(session, sid, qid)
    for _ in range(STABLE_AFTER_CORRECT):
        apply_review_result(session, item, True)
    assert item.state == "review"
    assert item.review_count == 2
    assert item.correct_count == 2
    assert item.due_at > item.last_reviewed_at
    assert len(item.review_history_json) == 2
    assert item.review_history_json[-1]["correct"] is True
    assert "interval_days" in item.review_history_json[-1]


def test_due_items_respect_due_date_and_ordering(session):
    sid = _student(session)
    now = session.query(LearningStudent).filter_by(id=sid).one().created_at
    first = _question(session, 1)
    second = _question(session, 2)
    item_a, _ = ensure_review_item(session, sid, first, now=now)
    item_b, _ = ensure_review_item(
        session, sid, second, now=now - timedelta(days=1))
    # item_b is due (created a day earlier, so due_at is in the past);
    # item_a is due tomorrow and must not appear.
    due = due_review_items(session, sid, now=now)
    assert [r.id for r in due] == [item_b.id]
    assert due_question_ids(session, sid, now=now) == [second]
    # Once item_a passes its due date it joins the queue, still ordered.
    due_later = due_review_items(session, sid, now=now + timedelta(days=2))
    assert [r.id for r in due_later] == [item_b.id, item_a.id]


def test_due_queue_excludes_not_yet_due(session):
    sid = _student(session)
    qid = _question(session)
    ensure_review_item(session, sid, qid)  # due tomorrow by design
    assert due_review_items(session, sid) == []
    summary = review_summary(session, sid)
    assert summary["due_now"] == 0
    assert summary["upcoming"] == 1
    assert summary["next_due_at"]


def test_due_queue_never_serves_rejected_questions(session):
    """A question rejected during human review must leave the review queue."""
    sid = _student(session)
    qid = _question(session)
    ensure_review_item(session, sid, qid)
    item = get_review_item(session, sid, "question", qid)
    item.due_at = datetime(2000, 1, 1)   # force due in the past
    session.commit()
    assert due_question_ids(session, sid) == [qid]
    row = session.query(QuestionReviewStatus).filter_by(question_id=qid).one()
    row.status = "rejected"
    session.commit()
    assert due_question_ids(session, sid) == []
    assert review_summary(session, sid)["due_now"] == 0


def test_suspend_review_item_removes_it_from_queue(session):
    sid = _student(session)
    qid = _question(session)
    item, _ = ensure_review_item(session, sid, qid)
    suspend_review_item(session, item, reason="student_request")
    assert item.state == "suspended"
    assert item not in due_review_items(session, sid)
    assert review_summary(session, sid)["by_state"]["suspended"] == 1


def test_review_summary_counts_states_and_completed_reviews(session):
    sid = _student(session)
    qid = _question(session)
    item, _ = ensure_review_item(session, sid, qid)
    apply_review_result(session, item, True)
    summary = review_summary(session, sid)
    assert summary["total"] == 1
    assert summary["completed_reviews"] == 1
    assert summary["by_state"] == {"learning": 1}


def test_review_items_for_different_students_are_independent(session):
    qid = _question(session)
    sid_a, sid_b = _student(session), _student(session)
    ensure_review_item(session, sid_a, qid)
    assert get_review_item(session, sid_b, "question", qid) is None
    assert session.query(LearningReviewItem).count() == 1


def test_review_items_never_store_question_content(session):
    sid = _student(session)
    qid = _question(session)
    item, _ = ensure_review_item(session, sid, qid)
    columns = {c.name for c in LearningReviewItem.__table__.columns}
    assert not {"question_text", "correct_answer", "explanation"} & columns
    assert item.source_type == "question"
    assert item.source_id == qid