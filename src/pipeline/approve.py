"""Approval helper (delegates to review.set_status)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.pipeline.review import set_status


def approve(session: Session, question_id: str, reviewer: str = "cli") -> None:
    set_status(session, question_id, "approved", reviewer)


def reject(session: Session, question_id: str, reviewer: str = "cli") -> None:
    set_status(session, question_id, "rejected", reviewer)
