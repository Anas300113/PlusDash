"""Step: vision analysis (stub for deterministic spike).
Records a placeholder AIJob so vision work is auditable even
before a model is wired in."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from src.core.database import AIJob
from src.core.logging import get_logger

log = get_logger("pipeline.vision")


def run(session: Session, page_ids: list[str], model: str = "not-configured") -> str:
    job = AIJob(id=str(uuid.uuid4()), job_type="vision",
                source_input=f"{len(page_ids)} pages",
                model=model, status="completed")
    session.add(job)
    session.commit()
    log.info("vision job %s recorded (%d pages)", job.id, len(page_ids))
    return job.id
