"""Step: inventory. Thin wrapper so the orchestrator has one call style."""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.source.inventory import inventory_directory


def run(session: Session, source_root, repo_name: str, batch: str,
        version: str = "0.1.0"):
    return len(inventory_directory(session, source_root, repo_name, batch=batch,
                                   version=version))
