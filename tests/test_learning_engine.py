import uuid

from src.core.database import (
    CanonicalQuestion, LearningQuestionAttempt, LearningStudent,
    LearningStudySession, QuestionReviewStatus,
)
from src.learning.weak_area import refresh_topic_mastery, weak_topics
from src.pipeline.review import set_status


def _student_with_attempts(session, correct: int, total: int, topic="maths-arithmetic"):
    s = LearningStudent(id=str(uuid.uuid4()), name="T")
    session.add(s)
    sess = LearningStudySession(id=str(uuid.uuid4()), student_id=s.id)
    session.add(sess)
    q = CanonicalQuestion(id=str(uuid.uuid4()), subject="maths", topic=topic,
                          question_type="mcq", question_text="q", correct_answer="B",
                          options_json=[{"letter": "A", "text": "1"},
                                        {"letter": "B", "text": "2"}])
    session.add(q)
    session.flush()
    session.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    for i in range(total):
        session.add(LearningQuestionAttempt(
            id=str(uuid.uuid4()), student_id=s.id, session_id=sess.id,
            question_id=q.id, chosen_answer="B" if i < correct else "A",
            is_correct=i < correct))
    session.commit()
    return s.id


def test_weak_area_threshold(session):
    sid = _student_with_attempts(session, correct=1, total=4)
    refresh_topic_mastery(session, sid)
    weak = weak_topics(session, sid)
    assert len(weak) == 1 and weak[0].accuracy == 0.25


def test_strong_topic_not_weak(session):
    sid = _student_with_attempts(session, correct=4, total=4)
    refresh_topic_mastery(session, sid)
    assert weak_topics(session, sid) == []


def test_only_approved_questions_practiceable(session):
    sid = _student_with_attempts(session, correct=1, total=1)
    row = session.query(QuestionReviewStatus).first()
    assert row.status == "approved"
    set_status(session, row.question_id, "rejected")
    assert session.query(QuestionReviewStatus).first().status == "rejected"
