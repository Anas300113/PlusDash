"""Step: duplicate detection. Fingerprints canonical-question bodies;
the spike reports collisions without deleting anything."""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.core.database import CanonicalQuestion
from src.core.hashing import content_fingerprint
from src.core.logging import get_logger

log = get_logger("pipeline.dedup")


def fingerprint_question(q: CanonicalQuestion) -> str:
    return content_fingerprint(q.question_text, q.correct_answer)


def run(session: Session, docs=None) -> dict:
    seen: dict[str, str] = {}
    dupes = 0
    for q in session.query(CanonicalQuestion).all():
        fp = content_fingerprint(q.question_text, q.correct_answer)
        if not q.fingerprint:
            q.fingerprint = fp
        if fp in seen:
            dupes += 1
        else:
            seen[fp] = q.id
    session.commit()
    log.info("dedup: %d duplicates among %d questions", dupes, len(seen) + dupes)
    return {"questions": len(seen) + dupes, "duplicates": dupes}
