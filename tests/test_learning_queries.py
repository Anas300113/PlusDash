"""Dedicated regression tests for src/learning/queries.py.

Read-only lookups shared by the learning engine:

* question_map / approved_question_ids / is_approved — only approved questions
  are ever student-facing.
* curriculum_payload / common_mistakes — stored curriculum for the LEARN step.
* explain_question — deterministic feedback from stored content, no LLM.

Follows existing conventions: conftest session fixture, synthetic approved
CanonicalQuestion rows, uuid ids, no LLM, in-memory SQLite.
"""
from __future__ import annotations

import uuid

from src.core.database import (
    CanonicalQuestion, CurriculumCommonMistake, CurriculumLesson,
    CurriculumStrategy, CurriculumWorkedExample, QuestionReviewStatus,
)
from src.learning.queries import (
    APPROVED, _ground_in_sources, approved_question_ids, common_mistakes,
    curriculum_payload, explain_question, is_approved, question_map,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _question(session, index=1, topic="maths-arithmetic", subject="maths",
              question_type="mcq", skills=("sk-add",), approve=True,
              correct_answer="B"):
    q = CanonicalQuestion(
        id=f"qy{index}-{uuid.uuid4().hex[:6]}", subject=subject, topic=topic,
        question_type=question_type, question_text=f"Q{index}",
        correct_answer=correct_answer, hint="add them",
        options_json=[{"letter": "A", "text": "1"},
                      {"letter": "B", "text": "2"}],
        skill_ids=list(skills), explanation="Because B is correct.",
        worked_solution="1 + 1 = 2", difficulty=1)
    session.add(q)
    session.flush()
    if approve:
        session.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    session.commit()
    return q


def _unapproved_question(session, index=1):
    q = CanonicalQuestion(
        id=f"qu{index}-{uuid.uuid4().hex[:6]}", subject="maths",
        topic="maths-arithmetic", question_type="mcq",
        question_text=f"Unapproved Q{index}", correct_answer="B",
        options_json=[{"letter": "A", "text": "1"},
                      {"letter": "B", "text": "2"}],
        skill_ids=["sk-add"], explanation="x", worked_solution="y")
    session.add(q)
    session.commit()
    return q


# --------------------------------------------------------------------------- #
# question_map
# --------------------------------------------------------------------------- #

def test_question_map_empty_list(session):
    assert question_map(session, []) == {}


def test_question_map_returns_found_questions(session):
    q1 = _question(session, 1)
    q2 = _question(session, 2)
    out = question_map(session, [q1.id, q2.id, "does-not-exist"])
    assert set(out) == {q1.id, q2.id}
    assert out[q1.id] is q1
    assert out[q2.id] is q2


# --------------------------------------------------------------------------- #
# approved_question_ids
# --------------------------------------------------------------------------- #

def test_approved_question_ids_only_approved(session):
    _question(session, 1)
    _unapproved_question(session, 1)
    ids = approved_question_ids(session)
    assert len(ids) == 1


def test_approved_question_ids_filters_subject_topic_type(session):
    _question(session, 1, subject="maths", topic="maths-arithmetic",
              question_type="mcq")
    _question(session, 2, subject="english", topic="english-vocab",
              question_type="short_answer")
    assert len(approved_question_ids(session, subject="maths")) == 1
    assert len(approved_question_ids(session, topic="english-vocab")) == 1
    assert len(approved_question_ids(session, question_type="mcq")) == 1


def test_approved_question_ids_skill_filter(session):
    _question(session, 1, skills=("sk-add",))
    _question(session, 2, skills=("sk-fractions",))
    assert len(approved_question_ids(session, skill_id="sk-add")) == 1
    assert len(approved_question_ids(session, skill_id="sk-fractions")) == 1
    assert approved_question_ids(session, skill_id="sk-none") == []


def test_approved_question_ids_exclude_ids(session):
    q1 = _question(session, 1)
    _question(session, 2)
    ids = approved_question_ids(session, exclude_ids=[q1.id])
    assert q1.id not in ids


def test_approved_question_ids_limit(session):
    _question(session, 1)
    _question(session, 2)
    ids = approved_question_ids(session, limit=1)
    assert len(ids) == 1


def test_approved_question_ids_deterministic_ordering(session):
    _question(session, 1)
    _question(session, 2)
    first = approved_question_ids(session)
    second = approved_question_ids(session)
    assert first == second  # stable across calls


# --------------------------------------------------------------------------- #
# is_approved
# --------------------------------------------------------------------------- #

def test_is_approved_approved(session):
    q = _question(session)
    assert is_approved(session, q.id) is True


def test_is_approved_rejected(session):
    q = _question(session, approve=False)
    session.add(QuestionReviewStatus(question_id=q.id, status="rejected"))
    session.commit()
    assert is_approved(session, q.id) is False


def test_is_approved_unknown_question(session):
    assert is_approved(session, "no-such-id") is False



# --------------------------------------------------------------------------- #
# curriculum_payload
# --------------------------------------------------------------------------- #

def test_curriculum_payload_empty_without_curriculum(session):
    out = curriculum_payload(session, "maths-arithmetic")
    assert out == {
        "topic_id": "maths-arithmetic",
        "lessons": [],
        "strategies": [],
        "worked_examples": [],
        "common_mistakes": [],
    }


def test_curriculum_payload_shape(session):
    session.add(CurriculumLesson(
        id=str(uuid.uuid4()), topic_id="maths-arithmetic",
        title="Adding fractions", content_markdown="# Adding fractions",
        display_order=1))
    session.add(CurriculumStrategy(
        id=str(uuid.uuid4()), topic_id="maths-arithmetic",
        title="Common denominator", content_markdown="Use LCM.",
        display_order=1))
    session.add(CurriculumWorkedExample(
        id=str(uuid.uuid4()), topic_id="maths-arithmetic",
        title="Worked: 3/4 + 1/4", content_markdown="Step by step."))
    session.add(CurriculumCommonMistake(
        id=str(uuid.uuid4()), topic_id="maths-arithmetic",
        mistake_text="Adding denominators",
        explanation_markdown="Keep the denominator."))
    session.commit()
    out = curriculum_payload(session, "maths-arithmetic")
    assert out["topic_id"] == "maths-arithmetic"
    assert out["lessons"][0]["title"] == "Adding fractions"
    assert out["strategies"][0]["title"] == "Common denominator"
    assert out["worked_examples"][0]["title"] == "Worked: 3/4 + 1/4"
    assert out["common_mistakes"][0]["mistake"] == "Adding denominators"


# --------------------------------------------------------------------------- #
# common_mistakes
# --------------------------------------------------------------------------- #

def test_common_mistakes_empty_when_none(session):
    assert common_mistakes(session, "maths-arithmetic") == []


def test_common_mistakes_returns_rows(session):
    session.add(CurriculumCommonMistake(
        id=str(uuid.uuid4()), topic_id="maths-arithmetic",
        mistake_text="Adding denominators",
        explanation_markdown="Keep the denominator."))
    session.commit()
    mistakes = common_mistakes(session, "maths-arithmetic")
    assert len(mistakes) == 1
    assert mistakes[0]["mistake"] == "Adding denominators"


# --------------------------------------------------------------------------- #
# explain_question
# --------------------------------------------------------------------------- #

def test_explain_question_full_shape(session):
    q = _question(session)
    out = explain_question(session, q)
    assert out["question_id"] == q.id
    assert out["subject"] == q.subject
    assert out["topic"] == q.topic
    assert out["question_type"] == q.question_type
    assert out["difficulty"] == q.difficulty
    assert out["correct_answer"] == q.correct_answer
    assert out["explanation"] == q.explanation
    assert out["hint"] == q.hint
    assert out["worked_solution"] == q.worked_solution
    assert out["common_mistakes"] == []
    assert out["source_evidence"] == []
    assert out["grounding"] == "no knowledge index available for this explanation"


def test_explain_question_review_prompt_correct(session):
    q = _question(session)
    out = explain_question(session, q, chosen_answer="B", is_correct=True)
    assert out["review_prompt"] == ""  # correct answers need no correction


def test_explain_question_review_prompt_wrong(session):
    q = _question(session)
    out = explain_question(session, q, chosen_answer="A", is_correct=False)
    assert "Your answer was 'A'" in out["review_prompt"]
    assert "The correct answer is 'B'" in out["review_prompt"]


def test_explain_question_review_prompt_no_answer(session):
    q = _question(session)
    out = explain_question(session, q)
    assert "The correct answer is 'B'" in out["review_prompt"]


def test_explain_question_derives_correctness_from_chosen_answer(session):
    q = _question(session)
    out = explain_question(session, q, chosen_answer="B")
    assert out["review_prompt"] == ""  # derived correct: no correction
    out2 = explain_question(session, q, chosen_answer="A")
    assert "Your answer was 'A'" in out2["review_prompt"]
    assert "The correct answer is 'B'" in out2["review_prompt"]


def test_explain_question_includes_common_mistakes(session):
    q = _question(session)
    session.add(CurriculumCommonMistake(
        id=str(uuid.uuid4()), topic_id=q.topic,
        mistake_text="Adding denominators",
        explanation_markdown="Keep the denominator."))
    session.commit()
    out = explain_question(session, q)
    assert out["common_mistakes"][0]["mistake"] == "Adding denominators"


def test_explain_question_no_llm_used(session):
    """explain_question must not import/openai or anthropic."""
    import src.learning.queries as m
    src = open(m.__file__).read()
    assert "openai" not in src.lower()
    assert "anthropic" not in src.lower()


# --------------------------------------------------------------------------- #
# _ground_in_sources (degradation paths)
# --------------------------------------------------------------------------- #

def test_ground_in_sources_no_index(session):
    q = _question(session)
    evidence, note = _ground_in_sources(q, knowledge_index=None)
    assert evidence == []
    assert note == "no knowledge index available for this explanation"


def test_ground_in_sources_retrieval_error(session):
    q = _question(session)
    class BadIndex:
        def search(self, *args, **kwargs):
            raise RuntimeError("index down")
    evidence, note = _ground_in_sources(q, knowledge_index=BadIndex())
    assert evidence == []
    assert note == "source grounding unavailable (retrieval error)"