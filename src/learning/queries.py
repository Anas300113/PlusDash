"""Read-only lookups shared by the learning engine.

Centralises two platform rules so they cannot be forgotten in one place:
  * only ``approved`` questions are ever student-facing
  * feedback/explanation is assembled from stored canonical + curriculum
    content, without calling an LLM (AI tutoring is a separate augmentation
    layer and is deliberately not on the critical path here).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.core.database import (
    CanonicalQuestion, CurriculumCommonMistake, CurriculumLesson,
    CurriculumStrategy, CurriculumWorkedExample, QuestionReviewStatus,
)

APPROVED = "approved"


def question_map(db: Session, question_ids) -> dict[str, CanonicalQuestion]:
    ids = [q for q in question_ids if q]
    if not ids:
        return {}
    rows = (db.query(CanonicalQuestion)
            .filter(CanonicalQuestion.id.in_(ids)).all())
    return {q.id: q for q in rows}


def approved_question_ids(db: Session, subject: str | None = None,
                          topic: str | None = None,
                          question_type: str | None = None,
                          skill_id: str | None = None,
                          exclude_ids=None, limit: int | None = None,
                          ) -> list[str]:
    """Ids of approved questions matching the filters, deterministic order.

    Deterministic ordering is intentional: sessions must be reproducible so an
    interrupted session can be resumed and tests are stable. Callers that want
    a shuffled paper call ``session.order_questions(..., mode="shuffled")``
    with an explicit seed.
    """
    query = (db.query(CanonicalQuestion)
             .join(QuestionReviewStatus,
                   QuestionReviewStatus.question_id == CanonicalQuestion.id)
             .filter(QuestionReviewStatus.status == APPROVED))
    if subject:
        query = query.filter(CanonicalQuestion.subject == subject)
    if topic:
        query = query.filter(CanonicalQuestion.topic == topic)
    if question_type:
        query = query.filter(CanonicalQuestion.question_type == question_type)
    rows = query.order_by(CanonicalQuestion.id).all()
    excluded = set(exclude_ids or [])
    ids = [q.id for q in rows if q.id not in excluded]
    if skill_id:
        ids = [q.id for q in (question_map(db, ids).values())
               if skill_id in (q.skill_ids or [])]
    return ids[:limit] if limit else ids


def is_approved(db: Session, question_id: str) -> bool:
    row = db.query(QuestionReviewStatus).filter_by(
        question_id=question_id).first()
    return bool(row and row.status == APPROVED)


def curriculum_payload(db: Session, topic_id: str) -> dict:
    """Learn step: stored lesson / strategy / worked example / common mistake."""
    return {
        "topic_id": topic_id,
        "lessons": [{"title": r.title, "content": r.content_markdown}
                    for r in db.query(CurriculumLesson)
                    .filter_by(topic_id=topic_id)
                    .order_by(CurriculumLesson.display_order).all()],
        "strategies": [{"title": r.title, "content": r.content_markdown}
                       for r in db.query(CurriculumStrategy)
                       .filter_by(topic_id=topic_id)
                       .order_by(CurriculumStrategy.display_order).all()],
        "worked_examples": [{"title": r.title, "content": r.content_markdown}
                            for r in db.query(CurriculumWorkedExample)
                            .filter_by(topic_id=topic_id).all()],
        "common_mistakes": [{"mistake": r.mistake_text,
                             "explanation": r.explanation_markdown}
                            for r in db.query(CurriculumCommonMistake)
                            .filter_by(topic_id=topic_id).all()],
    }


def common_mistakes(db: Session, topic_id: str) -> list[dict]:
    return [{"mistake": r.mistake_text, "explanation": r.explanation_markdown}
            for r in db.query(CurriculumCommonMistake)
            .filter_by(topic_id=topic_id).all()]


def _ground_in_sources(question: CanonicalQuestion,
                       knowledge_index, top_k: int = 3) -> tuple[list[dict], str]:
    """Ground the explanation in ingested source material via the knowledge
    engine, WITHOUT ever fabricating a citation.

    Keyed by the question text (never by ``student_id``), so it cannot inherit
    the student-ownership gap. Each hit carries verifiable provenance
    (filename, page, excerpt, score). When the index finds no lexical evidence
    it returns ``([], ...)`` and an explicit grounding note -- it never invents
    a source and never labels a retrieved chunk as a verbatim quotation.
    """
    if knowledge_index is None:
        return [], "no knowledge index available for this explanation"
    query = (question.question_text or "").strip() or question.topic
    hits = []
    try:
        hits = knowledge_index.search(query, top_k=top_k, min_score=0.05)
    except Exception:
        # A retrieval failure must never break explanation; degrade to
        # "no evidence" rather than raising on the learning path.
        return [], "source grounding unavailable (retrieval error)"
    evidence = [
        {
            "filename": h["filename"],
            "page_number": h["page_number"],
            "excerpt": h["excerpt"],
            "score": h["score"],
            # provenance ids let a reviewer open the exact source page
            "document_id": h.get("document_id"),
            "page_id": h.get("page_id"),
        }
        for h in hits
    ]
    if evidence:
        note = ("source-grounded: excerpts are retrieved from ingested "
                "material and are not verbatim quotations of the answer")
    else:
        note = "no source-backed evidence found for this question"
    return evidence, note


def explain_question(db: Session, question: CanonicalQuestion,
                     chosen_answer: str | None = None,
                     is_correct: bool | None = None,
                     knowledge_index=None) -> dict:
    """Explain step: deterministic feedback from stored content only.

    This reports what is stored (correct answer, explanation, worked solution,
    topic common mistakes). It does NOT claim to diagnose a misconception;
    misconception identification is an AI-tutor concern and is deferred.

    ``knowledge_index`` (optional) is the cohesive integration point between
    the trustworthy knowledge engine and the learning loop's EXPLAIN step:
    when provided, the explanation is augmented with verifiable source
    evidence (filename/page/excerpt/score). It is keyed by the question text
    and topic only -- never by ``student_id`` -- so it cannot inherit the
    student-ownership gap. Evidence is always attributed and never fabricated:
    with no index or no lexical overlap, ``source_evidence`` is ``[]`` and the
    ``grounding`` note records that nothing was found.
    """
    mistakes = common_mistakes(db, question.topic)
    if is_correct is None and chosen_answer is not None:
        is_correct = (chosen_answer.strip().upper()
                      == (question.correct_answer or "").strip().upper())
    review_prompt = ""
    if is_correct is False and chosen_answer:
        review_prompt = (
            f"Your answer was '{chosen_answer}'. The correct answer is "
            f"'{question.correct_answer}'. Compare each step against the "
            "worked solution before trying a similar question.")
    elif is_correct is False or chosen_answer is None:
        # Explanation view without an answer still points at the method.
        review_prompt = (
            f"The correct answer is '{question.correct_answer}'. Compare each "
            "step against the worked solution before trying a similar "
            "question.")
    source_evidence, grounding = _ground_in_sources(question, knowledge_index)
    return {
        "question_id": question.id,
        "subject": question.subject,
        "topic": question.topic,
        "question_type": question.question_type,
        "difficulty": question.difficulty,
        "correct_answer": question.correct_answer,
        "explanation": question.explanation,
        "hint": question.hint,
        "worked_solution": question.worked_solution,
        "common_mistakes": mistakes,
        "review_prompt": review_prompt,
        # source-grounded evidence (may be empty); always attributed, never
        # presented as a quotation, never fabricated.
        "source_evidence": source_evidence,
        "grounding": grounding,
    }
