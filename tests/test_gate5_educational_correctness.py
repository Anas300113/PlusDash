"""Gate 5: educational correctness — corpus is safe but unverified,
nothing reaches students.

Every imported question must carry ``validation_required`` (or another
non-approved review status) and zero questions may be approved. Bulk
approval is forbidden; each question needs individual human sign-off.
"""
from __future__ import annotations

import uuid

import pytest

from src.core.database import (
    CanonicalQuestion, QuestionReviewStatus, get_engine,
    get_session_factory, init_db,
)
from src.pipeline.review import gate5_educational_correctness_check


@pytest.fixture()
def session(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'gate5.db'}")
    init_db(engine)
    S = get_session_factory(engine)
    s = S()
    yield s
    s.close()


def _add_question(session, text, status="validation_required"):
    q = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="maths", topic="arithmetic",
        question_type="mcq", question_text=text, correct_answer="B",
        options_json=[{"letter": "A", "text": "3"},
                      {"letter": "B", "text": "4"}],
        explanation="2+2=4.", fingerprint=str(uuid.uuid4()))
    session.add(q)
    session.flush()
    session.add(QuestionReviewStatus(
        question_id=q.id, status=status, source="ingestion",
        confidence=0.8))
    session.commit()
    return q.id


def test_gate5_safe_when_zero_approved(session):
    """All questions pending review -> gate5_safe True."""
    _add_question(session, "What is 2+2?")
    _add_question(session, "What is 3+3?")
    report = gate5_educational_correctness_check(session)
    assert report["total_questions"] == 2
    assert report["approved_questions"] == 0
    assert report["pending_review_questions"] == 2
    assert report["gate5_safe"] is True


def test_gate5_unsafe_when_any_approved(session):
    """One approved question -> gate5_safe False."""
    _add_question(session, "approved question", status="approved")
    _add_question(session, "pending question")
    report = gate5_educational_correctness_check(session)
    assert report["total_questions"] == 2
    assert report["approved_questions"] == 1
    assert report["pending_review_questions"] == 1
    assert report["gate5_safe"] is False


def test_gate5_empty_corpus_is_safe(session):
    """No questions at all -> gate5_safe True (vacuous)."""
    report = gate5_educational_correctness_check(session)
    assert report["total_questions"] == 0
    assert report["approved_questions"] == 0
    assert report["gate5_safe"] is True


def test_gate5_per_source_breakdown(session):
    """Per-source breakdown is empty when no SourceDocument rows exist."""
    _add_question(session, "prep q 1")
    _add_question(session, "prep q 2")
    report = gate5_educational_correctness_check(session)
    assert "per_source" in report
    # Without SourceDocument rows, the join yields no groups.
    assert report["per_source"] == {}