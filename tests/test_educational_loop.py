"""The educational loop: LEARN -> PRACTISE -> ASSESS -> IDENTIFY ERROR ->
EXPLAIN -> REVIEW -> RE-PRACTISE -> UPDATE MASTERY.

Verifies that every step is served from stored canonical/curriculum content
and attempt evidence, with no LLM anywhere on the path, and that ReviewItem
scheduling and mastery updates follow the loop automatically."""
from __future__ import annotations

import uuid

from src.core.database import (
    CanonicalQuestion, CurriculumCommonMistake, CurriculumLesson,
    CurriculumWorkedExample, LearningQuestionAttempt, LearningReviewItem,
    LearningRecommendation, LearningSkillMastery, LearningStudent,
    LearningStudySession, LearningTopicMastery, QuestionReviewStatus,
)
from src.learning.loop import (
    AI_REQUIRED_FOR_LOOP, LOOP_STEPS, identify_errors, loop_contract,
    loop_snapshot, re_practice,
)
from src.learning.weak_area import (
    build_recommendations, open_recommendations, refresh_mastery,
    refresh_recommendations,
)


def _question(session, index, topic="maths-arithmetic", subject="maths",
              skills=("sk-add",), approve=True):
    q = CanonicalQuestion(
        id=f"Lq{index}-{uuid.uuid4().hex[:6]}", subject=subject, topic=topic,
        question_type="mcq", question_text=f"Question {index}",
        correct_answer="B", hint="Add the numerators.",
        explanation="Common denominator first.",
        worked_solution="3/4 + 1/4 = 4/4 = 1",
        options_json=[{"letter": "A", "text": "1"},
                      {"letter": "B", "text": "2"}],
        skill_ids=list(skills))
    session.add(q)
    session.flush()
    if approve:
        session.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    session.commit()
    return q


def _student(session):
    row = LearningStudent(id=str(uuid.uuid4()), name="L")
    session.add(row)
    session.commit()
    return row.id


def _session(session, student_id, session_type="practice"):
    row = LearningStudySession(id=str(uuid.uuid4()), student_id=student_id,
                               session_type=session_type)
    session.add(row)
    session.commit()
    return row


def _attempt(session, student_id, session_id, question, correct):
    row = LearningQuestionAttempt(
        id=str(uuid.uuid4()), student_id=student_id, session_id=session_id,
        question_id=question.id, chosen_answer="A" if not correct else "B",
        is_correct=correct, action="answer")
    session.add(row)
    session.commit()
    return row


def _seed_curriculum(session, topic="maths-arithmetic"):
    session.add(CurriculumLesson(id=str(uuid.uuid4()), topic_id=topic,
                                 title="Adding fractions",
                                 content_markdown="# Adding fractions"))
    session.add(CurriculumWorkedExample(id=str(uuid.uuid4()), topic_id=topic,
                                        title="Worked: 3/4 + 1/4",
                                        content_markdown="Step by step."))
    session.add(CurriculumCommonMistake(id=str(uuid.uuid4()), topic_id=topic,
                                        mistake_text="Adding denominators",
                                        explanation_markdown="Keep it."))
    session.commit()


def test_loop_contract_declares_ai_free_loop():
    contract = loop_contract()
    assert contract["steps"] == list(LOOP_STEPS)
    assert AI_REQUIRED_FOR_LOOP is False
    assert contract["evidence_table"] == "learning_question_attempts"
    assert contract["scheduling_table"] == "learning_review_items"
    assert set(contract["mastery_tables"]) == {
        "learning_topic_mastery", "learning_skill_mastery"}


def test_loop_steps_are_ordered_and_complete():
    assert LOOP_STEPS == ("learn", "practise", "assess", "identify_error",
                          "explain", "review", "re_practise", "update_mastery")


def test_identify_errors_reports_weak_topics_and_mistakes(session):
    student = _student(session)
    srow = _session(session, student)
    _seed_curriculum(session)
    q = _question(session, 1)
    for _ in range(3):
        _attempt(session, student, srow.id, q, correct=False)
    refresh_mastery(session, student)
    errors = identify_errors(session, student)
    assert errors["weak_topics"][0]["topic"] == "maths-arithmetic"
    assert errors["weak_skills"][0]["skill"] == "sk-add"
    assert errors["repeated_mistakes"][0]["question_id"] == q.id
    suggested = errors["suggested_topics"][0]
    assert suggested["topic"] == "maths-arithmetic"
    # "likely error area" comes from the curriculum, not from an AI guess
    assert suggested["topic_common_mistakes"][0]["mistake"] == "Adding denominators"


def test_loop_snapshot_covers_every_step_without_an_llm(session):
    from src.learning.review import ensure_review_item
    student = _student(session)
    srow = _session(session, student)
    _seed_curriculum(session)
    q1 = _question(session, 1)
    q2 = _question(session, 2, skills=("sk-carry",))
    _attempt(session, student, srow.id, q1, correct=False)
    _attempt(session, student, srow.id, q1, correct=False)
    _attempt(session, student, srow.id, q2, correct=True)
    refresh_mastery(session, student)
    # The session state machine creates this automatically; created here
    # because these attempts are raw evidence rows.
    ensure_review_item(session, student, q1.id, topic_id=q1.topic,
                       subject=q1.subject, due_reason="incorrect")
    snap = loop_snapshot(session, student)
    assert snap["loop"] == list(LOOP_STEPS)
    # LEARN: curriculum for the weak topic
    assert snap["learn"]["topics"][0]["topic"] == "maths-arithmetic"
    assert snap["learn"]["topics"][0]["payload"]["lessons"]
    # PRACTISE: approved questions only
    assert set(snap["practise"]["question_ids"]) <= {q1.id, q2.id}
    # ASSESS
    assert snap["assess"]["accuracy"] == 1 / 3
    # IDENTIFY ERROR
    assert snap["identify_error"]["repeated_mistakes"][0]["question_id"] == q1.id
    # EXPLAIN: built from stored content
    explanation = snap["explain"][0]
    assert explanation["question_id"] == q1.id
    assert explanation["correct_answer"] == "B"
    assert explanation["hint"] == "Add the numerators."
    assert explanation["worked_solution"] == "3/4 + 1/4 = 4/4 = 1"
    assert explanation["common_mistakes"][0]["mistake"] == "Adding denominators"
    assert explanation["review_prompt"]
    # REVIEW: the wrong answers created a scheduled review item (due tomorrow)
    assert snap["review"]["due_count"] == 0
    assert snap["review"]["summary"]["upcoming"] == 1
    # RE-PRACTISE: excludes the questions already missed
    assert q1.id not in snap["re_practise"]["question_ids"]
    assert q1.id in snap["re_practise"]["excluded_question_ids"]
    # UPDATE MASTERY: topic and skill aggregates refreshed
    assert snap["update_mastery"]["topic_mastery"][0]["accuracy"] == 1 / 3
    assert {m["skill"] for m in snap["update_mastery"]["skill_mastery"]} == {
        "sk-add", "sk-carry"}
    assert snap["recommended_activities"]


def test_explain_serves_stored_content_only(session):
    from src.learning.loop import explain
    student = _student(session)
    q = _question(session, 1)
    out = explain(session, q.id, chosen_answer="A")
    assert out["review_prompt"].startswith("Your answer was 'A'")
    assert out["explanation"] == "Common denominator first."
    assert out["common_mistakes"] == []   # no curriculum seeded for this topic


def test_re_practice_prefers_weak_topics_and_new_questions(session):
    student = _student(session)
    srow = _session(session, student)
    missed = _question(session, 1)
    other = _question(session, 2)
    for _ in range(3):
        _attempt(session, student, srow.id, missed, correct=False)
    refresh_mastery(session, student)
    out = re_practice(session, student, limit=10)
    assert out["topic_ids"] == ["maths-arithmetic"]
    assert missed.id not in out["question_ids"]
    assert other.id in out["question_ids"]


def test_recommendations_prioritise_review_then_practice(session):
    student = _student(session)
    srow = _session(session, student)
    _seed_curriculum(session)
    q1 = _question(session, 1)
    q2 = _question(session, 2, skills=("sk-carry",))
    for _ in range(3):
        _attempt(session, student, srow.id, q1, correct=False)
    _attempt(session, student, srow.id, q2, correct=True)
    refresh_mastery(session, student)
    from src.learning.review import ensure_review_item
    ensure_review_item(session, student, q1.id, topic_id=q1.topic,
                       subject=q1.subject, due_reason="incorrect")
    built = build_recommendations(session, student)
    kinds = [r["kind"] for r in built]
    # Nothing is due yet (the review item is due tomorrow), so weak-topic
    # practice leads; review takes over once the item is actually due.
    assert kinds[0] == "practice"
    assert set(built[0]["question_ids"]) <= {q1.id, q2.id}
    assert "review" not in kinds

    from src.learning.review import ensure_review_item, get_review_item
    ensure_review_item(session, student, q1.id, topic_id=q1.topic,
                       subject=q1.subject, due_reason="incorrect")
    built = build_recommendations(session, student)
    kinds = [r["kind"] for r in built]
    # Nothing is due yet (the review item is due tomorrow), so weak-topic
    # practice leads; review takes over once the item is actually due.
    assert kinds[0] == "practice"
    assert set(built[0]["question_ids"]) <= {q1.id, q2.id}
    assert "review" not in kinds

    item = get_review_item(session, student, "question", q1.id)
    item.due_at = item.created_at        # force due now
    session.commit()
    built2 = build_recommendations(session, student)
    assert built2[0]["kind"] == "review"
    assert built2[0]["question_ids"] == [q1.id]
    assert built2[0]["review_item_ids"] == [item.id]
    assert [r["kind"] for r in built2[1:]] != []  # practice follows review


def test_learn_recommendation_when_curriculum_exists(session):
    student = _student(session)
    srow = _session(session, student)
    _seed_curriculum(session)
    q = _question(session, 1)
    for _ in range(3):
        _attempt(session, student, srow.id, q, correct=False)
    refresh_mastery(session, student)
    built = build_recommendations(session, student)
    learn = [r for r in built if r["kind"] == "learn"]
    assert learn and learn[0]["topic_ids"] == ["maths-arithmetic"]
    assert learn[0]["reason"] == "curriculum_available"


def test_refresh_recommendations_is_idempotent_and_auditable(session):
    student = _student(session)
    srow = _session(session, student)
    q = _question(session, 1)
    for _ in range(3):
        _attempt(session, student, srow.id, q, correct=False)
    refresh_mastery(session, student)
    first = refresh_recommendations(session, student)
    assert first
    rows_first = session.query(LearningRecommendation).all()
    assert all(r.status == "open" for r in rows_first)
    second = refresh_recommendations(session, student)
    rows_after = session.query(LearningRecommendation).all()
    superseded = [r for r in rows_after if r.status == "superseded"]
    open_rows = [r for r in rows_after if r.status == "open"]
    assert superseded          # history kept, not deleted
    assert len(open_rows) == len(second)
    assert len(rows_after) == len(rows_first) + len(second)
    assert [r["kind"] for r in second] == [r["kind"] for r in first]


def test_no_evidence_means_no_recommendations(session):
    student = _student(session)
    assert build_recommendations(session, student) == []
    assert open_recommendations(session, student) == []
    assert session.query(LearningRecommendation).count() == 0


def test_review_cycle_updates_mastery_and_ladder_together(session):
    """The loop end-to-end: wrong now, correct review later, mastery moves."""
    from src.learning.review import (
        apply_review_result, due_question_ids, ensure_review_item,
        get_review_item,
    )
    student = _student(session)
    srow = _session(session, student)
    q = _question(session, 1)
    _attempt(session, student, srow.id, q, correct=False)
    refresh_mastery(session, student)
    assert session.query(LearningTopicMastery).one().accuracy == 0.0
    item, _ = ensure_review_item(session, student, q.id)
    assert due_question_ids(session, student) == []   # due tomorrow
    apply_review_result(session, item, True, now=item.due_at)
    assert get_review_item(session, student, "question", q.id).state == "learning"
    assert item.interval_days == 3.0
    # A second correct review promotes the item to the stable review state.
    apply_review_result(session, item, True, now=item.due_at)
    assert item.state == "review"
    # Re-practise the same question correctly -> mastery recovers.
    srow2 = _session(session, student)
    _attempt(session, student, srow2.id, q, correct=True)
    refresh_mastery(session, student)
    assert session.query(LearningTopicMastery).one().accuracy == 0.5
    assert session.query(LearningReviewItem).count() == 1