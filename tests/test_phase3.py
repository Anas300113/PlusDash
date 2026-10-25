"""Reference-import + assembler + curriculum + parent-summary tests."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from src.assessment.assembler import assemble_authentic, assemble_generated
from src.core.database import (
    AssessmentExam, CanonicalQuestion, QuestionReviewStatus,
    SourceDocument,
)
from src.curriculum.seed import seed_curriculum
from src.learning.parent_summary import parent_summary
from src.source.adapters.prep_adapter import PrepAdapter
from src.source.adapters.tutor_adapter import TutorAdapter


def _approve(session, **kw):
    q = CanonicalQuestion(id=str(uuid.uuid4()), subject="maths",
                          topic="maths-arithmetic", question_type="mcq",
                          question_text=kw.get("text", "q"),
                          correct_answer="B",
                          options_json=[{"letter": "A", "text": "1"},
                                        {"letter": "B", "text": "2"}],
                          fingerprint=kw.get("fp", str(uuid.uuid4())))
    session.add(q)
    session.flush()
    session.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    session.commit()
    return q


def test_reference_import_script(session, tmp_path):
    from scripts.import_reference import import_file
    tutor = tmp_path / "t.json"
    tutor.write_text(json.dumps([{
        "id": "t1", "subject": "mathematics", "topic": "arithmetic",
        "format": "multiple_choice", "question_text": "2+2?",
        "options": ["3", "4"], "correct_answer": "4",
        "correct_index": 1, "worked_solution": "2+2=4"}]), encoding="utf-8")
    stats = import_file(session, tutor, TutorAdapter(), "11plus-tutor",
                        "https://github.com/jhammant/11plus-tutor", "b")
    assert stats["imported"] == 1
    # re-import is a dupe, not a duplicate row
    stats2 = import_file(session, tutor, TutorAdapter(), "11plus-tutor",
                         "https://github.com/jhammant/11plus-tutor", "b")
    assert stats2["dupes"] == 1 and stats2["imported"] == 0


def test_prep_import_preserves_region(session, tmp_path):
    from scripts.import_reference import import_file
    prep = tmp_path / "kent.json"
    prep.write_text(json.dumps([{
        "id": "kent-maths-001", "subject": "maths", "topic": "arithmetic",
        "difficulty": 1, "type": "mcq", "question": "347 + 256?",
        "options": ["A) 593", "B) 603"], "answer": "B",
        "explanation": "ok", "region": "kent", "examBoard": "GL"}]),
        encoding="utf-8")
    stats = import_file(session, prep, PrepAdapter(), "11plus-prep",
                        "https://github.com/SahirVhora/11plus-prep", "b")
    assert stats["imported"] == 1
    q = session.query(CanonicalQuestion).first()
    assert (q.region, q.exam_board) == ("kent", "GL")
    assert session.query(QuestionReviewStatus).first().status == "validation_required"


def test_generated_assembly_only_approved(session):
    _approve(session, text="q1", fp="fp1")
    pending = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="maths", topic="maths-arithmetic",
        question_type="mcq", question_text="q2", correct_answer="B",
        fingerprint="fp2")
    session.add(pending)
    session.flush()
    session.add(QuestionReviewStatus(question_id=pending.id, status="extracted"))
    session.commit()
    exam = AssessmentExam(id=str(uuid.uuid4()), exam_board_id="gl", name="E")
    session.add(exam)
    session.commit()
    out = assemble_generated(session, exam.id, [{"subject": "maths", "count": 5}])
    assert len(out["questions"]) == 1  # pending question excluded


def test_authentic_assembly_preserves_order(session):
    doc = SourceDocument(id=str(uuid.uuid4()), repo_name="spike",
                         source_path="p.pdf", file_sha256="s", file_size=1,
                         file_type="pdf")
    session.add(doc)
    session.commit()
    exam = AssessmentExam(id=str(uuid.uuid4()), exam_board_id="gl", name="E")
    session.add(exam)
    session.commit()
    out = assemble_authentic(session, exam.id, doc.id)
    assert out["sections"] == 1 and out["questions"] == []


def test_curriculum_seed(session):
    assert seed_curriculum(session) == 16
    assert seed_curriculum(session) == 0  # idempotent


def test_parent_summary(session):
    from src.core.database import (
        LearningQuestionAttempt, LearningStudent, LearningStudySession,
    )
    s = LearningStudent(id=str(uuid.uuid4()), name="K")
    session.add(s)
    sess = LearningStudySession(id=str(uuid.uuid4()), student_id=s.id)
    session.add(sess)
    q = _approve(session, text="qq", fp="fp-qq")
    session.add(LearningQuestionAttempt(
        id=str(uuid.uuid4()), student_id=s.id, session_id=sess.id,
        question_id=q.id, chosen_answer="A", is_correct=False))
    session.commit()
    summary = parent_summary(session, s.id)
    assert summary["practice_completed"] == 1
    assert summary["subject_performance"]["maths"]["attempted"] == 1
