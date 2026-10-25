"""Step: metadata classification. Rule-based subject/topic
suggestion for the spike; stores the suggestion on the occurrence
confidence until human/AI review."""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.core.database import QuestionOccurrence, SourceDocument
from src.core.logging import get_logger

log = get_logger("pipeline.classify")

SUBJECT_RULES = [
    ("maths", ("fraction", "percent", "algebra", "geometry", "calculate", "divide")),
    ("english", ("passage", "comprehension", "grammar", "punctuation", "spelling")),
    ("verbal_reasoning", ("synonym", "antonym", "analogy", "code", "hidden word")),
    ("non_verbal_reasoning", ("shape", "matrix", "rotate", "reflect", "cube", "fold")),
]


def suggest_subject(path: str, body: str) -> tuple[str, float]:
    hay = (path + " " + body).lower()
    for subject, keywords in SUBJECT_RULES:
        if any(k in hay for k in keywords):
            return subject, 0.6
    low = hay
    if "maths" in low or "math" in low:
        return "maths", 0.7
    if "english" in low:
        return "english", 0.7
    if "verbal" in low:
        return "verbal_reasoning", 0.7
    return "", 0.0


def run(session: Session, docs: list[SourceDocument]) -> dict:
    by_doc = {d.id: d for d in docs}
    classified = 0
    for occ in session.query(QuestionOccurrence).all():
        doc = by_doc.get(occ.document_id)
        if doc is None:
            continue
        subject, conf = suggest_subject(doc.source_path, "")
        if subject:
            occ.extraction_confidence = max(occ.extraction_confidence, conf)
            classified += 1
    session.commit()
    log.info("classify: %d occurrences given subject suggestions", classified)
    return {"classified": classified}
