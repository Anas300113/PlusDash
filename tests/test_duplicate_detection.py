import uuid

from src.core.database import CanonicalQuestion
from src.pipeline.dedup import run as dedup_run


def _add(session, text, ans):
    q = CanonicalQuestion(id=str(uuid.uuid4()), subject="maths", topic="t",
                          question_type="mcq", question_text=text,
                          correct_answer=ans)
    session.add(q)
    session.commit()
    return q


def test_dedup_detects_identical(session):
    _add(session, "What is 2+2?", "4")
    _add(session, "What is 2+2?", "4")
    stats = dedup_run(session)
    assert stats["duplicates"] == 1


def test_dedup_ignores_different(session):
    _add(session, "What is 2+2?", "4")
    _add(session, "What is 3+3?", "6")
    stats = dedup_run(session)
    assert stats["duplicates"] == 0
