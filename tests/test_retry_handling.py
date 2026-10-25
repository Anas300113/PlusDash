"""Retry handling: failed pipeline runs preserve checkpoint for resume."""
from __future__ import annotations

import uuid

from src.core.database import PipelineRun


def test_failed_run_keeps_checkpoint(session):
    run = PipelineRun(id=str(uuid.uuid4()), pipeline_version="0.1.0",
                      status="failed", checkpoint="text_extract",
                      error_message="boom")
    session.add(run)
    session.commit()
    row = session.query(PipelineRun).filter_by(id=run.id).first()
    assert row.status == "failed" and row.checkpoint == "text_extract"
