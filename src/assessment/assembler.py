"""Mock exam assembly: two modes.
Authentic mode preserves source ordering (occurrences in document
order). Generated mode assembles APPROVED questions by
subject/topic/difficulty filters with deterministic seeding."""
from __future__ import annotations

import random
import uuid

from sqlalchemy.orm import Session

from src.core.database import (
    AssessmentExam, AssessmentExamSection, CanonicalQuestion,
    QuestionOccurrence, QuestionReviewStatus,
)


def assemble_generated(session: Session, exam_id: str, sections: list[dict],
                       seed: int = 42) -> dict:
    rng = random.Random(seed)
    picked: list[str] = []
    for sec in sections:
        q = (session.query(CanonicalQuestion)
             .join(QuestionReviewStatus, QuestionReviewStatus.question_id == CanonicalQuestion.id)
             .filter(QuestionReviewStatus.status == "approved"))
        if sec.get("subject"):
            q = q.filter(CanonicalQuestion.subject == sec["subject"])
        if sec.get("topic"):
            q = q.filter(CanonicalQuestion.topic == sec["topic"])
        if sec.get("difficulty"):
            q = q.filter(CanonicalQuestion.difficulty == sec["difficulty"])
        rows = q.all()
        rng.shuffle(rows)
        chosen = rows[: int(sec.get("count", 10))]
        s = AssessmentExamSection(
            id=str(uuid.uuid4()), exam_id=exam_id,
            section_number=int(sec.get("section_number", 1)),
            name=sec.get("name", "Section"),
            subject=sec.get("subject", ""),
            question_count=len(chosen),
            time_minutes=int(sec.get("time_minutes", 30)),
            marks_available=len(chosen),
            instructions=sec.get("instructions", ""))
        session.add(s)
        picked.extend([c.id for c in chosen])
    session.commit()
    return {"sections": len(sections), "questions": picked}


def assemble_authentic(session: Session, exam_id: str, document_id: str,
                       section_name: str = "Paper") -> dict:
    occs = (session.query(QuestionOccurrence)
            .filter_by(document_id=document_id)
            .order_by(QuestionOccurrence.question_number).all())
    qids = [o.canonical_question_id for o in occs if o.canonical_question_id]
    s = AssessmentExamSection(
        id=str(uuid.uuid4()), exam_id=exam_id, section_number=1,
        name=section_name, question_count=len(qids),
        marks_available=len(qids),
        instructions="Authentic source-paper mode: original ordering preserved.")
    session.add(s)
    session.commit()
    return {"sections": 1, "questions": qids}
