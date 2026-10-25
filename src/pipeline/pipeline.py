"""Ingestion pipeline orchestrator. Steps are deterministic,
idempotent, resumable and versioned. Each step records a
checkpoint on the PipelineRun row."""
from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from src.core.database import (
    CanonicalQuestion, PipelineRun, QuestionReviewStatus, SourcePage,
)
from src.core.logging import get_logger
from src.pipeline import classify as classify_step
from src.pipeline import dedup as dedup_step
from src.pipeline import detect as detect_step
from src.pipeline import extract as extract_step
from src.pipeline import ingest as ingest_step
from src.pipeline import inventory as inventory_step
from src.pipeline import link as link_step
from src.pipeline import ocr as ocr_step
from src.pipeline import offices as offices_step
from src.pipeline import approve as approve_step
from src.pipeline import validate as validate_step
from src.pipeline import vision as vision_step
from src.source.inventory import inventory_directory

log = get_logger("pipeline")

STEPS = [
    "inventory", "ingest", "page_extract", "text_extract",
    "image_extract", "ocr", "vision", "detect", "link", "classify",
    "dedup", "validate", "approve",
]

# Pipeline needs source_root available to page_extract and image_extract.
# Pass it through the docs list via a temporary attribute on the session
# or as a module-level context. Simpler: add source_root param to steps
# that need it.


def run_pipeline(
    session: Session,
    source_root: str | Path,
    repo_name: str,
    batch: str,
    version: str = "0.1.0",
    resume_from: str | None = None,
    commit_sha: str = "",
    assets_dir: str | Path = "data/assets",
) -> PipelineRun:
    run = PipelineRun(id=str(uuid.uuid4()), pipeline_version=version, status="running")
    session.add(run)
    session.commit()
    stats: dict = {}
    try:
        start = STEPS.index(resume_from) if resume_from in STEPS else 0
        docs = []
        if start <= 0:
            docs = inventory_directory(session, source_root, repo_name, batch=batch,
                                       version=version, commit_sha=commit_sha)
            stats["inventory"] = len(docs)
            run.checkpoint = "inventory"
            session.commit()
        for step in STEPS[1:]:
            if STEPS.index(step) < start:
                continue
            if step == "ingest":
                stats[step] = ingest_step.run(session, docs, batch, source_root=source_root)
            elif step == "page_extract":
                stats[step] = extract_step.run_page_extract(session, docs, source_root)
            elif step == "text_extract":
                stats[step] = extract_step.run_text_extract(session, docs, source_root)
                office = offices_step.run_office_extract(session, docs, source_root)
                stats[step] = {"pdf_pages": stats[step].get("pages", 0),
                               "office_pages": office.get("pages", 0)}
            elif step == "image_extract":
                stats[step] = extract_step.run_image_extract(session, docs, source_root, assets_dir)
            elif step == "ocr":
                stats[step] = ocr_step.run_ocr(
                    session, docs,
                    source_root=source_root,
                    assets_dir=assets_dir)
            elif step == "vision":
                stats[step] = {"job_id": vision_step.run(session,
                                       [p.id for d in docs
                                        for p in session.query(SourcePage)
                                        .filter_by(document_id=d.id).all()])}
            elif step == "detect":
                stats[step] = detect_step.run(session, docs)
            elif step == "link":
                stats[step] = link_step.run(session, docs)
            elif step == "classify":
                stats[step] = classify_step.run(session, docs)
            elif step == "dedup":
                stats[step] = dedup_step.run(session, docs)
            elif step == "validate":
                stats[step] = validate_step.run(session, docs)
            elif step == "approve":
                # Questions that passed validation are now in the review queue
                # (status extracted/validation_required). This step records the
                # checkpoint; actual approve/reject happens via approve.approve()
                # or the review UI, never auto-published by the pipeline.
                ready = session.query(CanonicalQuestion).join(
                    QuestionReviewStatus,
                    QuestionReviewStatus.question_id == CanonicalQuestion.id
                ).filter(QuestionReviewStatus.status.in_(
                    ["extracted", "validation_required"]
                )).count()
                stats[step] = {"ready_for_review": ready}
            run.checkpoint = step
            session.commit()
        run.status = "completed"
        run.stats_json = stats
        session.commit()
    except Exception as exc:  # retryable: checkpoint preserved
        run.status = "failed"
        run.error_message = str(exc)
        session.commit()
        raise
    log.info("pipeline run %s completed: %s", run.id, stats)
    return run
