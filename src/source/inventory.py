"""Source inventory: scan a directory tree, hash files, classify type.
Deterministic and idempotent: re-running on unchanged files yields
identical records keyed by content SHA."""
from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from src.core.database import SourceDocument
from src.core.hashing import sha256_file
from src.core.logging import get_logger

log = get_logger("source.inventory")

ARCHIVE_SUFFIXES = {".zip"}
PDF_SUFFIXES = {".pdf"}
PPTX_SUFFIXES = {".pptx", ".ppt"}
DOC_SUFFIXES = {".docx", ".doc"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".tiff"}


def classify_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in PDF_SUFFIXES:
        return "pdf"
    if suffix in PPTX_SUFFIXES:
        return "pptx"
    if suffix in ARCHIVE_SUFFIXES:
        return "zip"
    if suffix in DOC_SUFFIXES:
        return "docx"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in {".xlsx", ".xls", ".csv"}:
        return "spreadsheet"
    if suffix in {".txt", ".md"}:
        return "text"
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "unknown"


def inventory_directory(
    session: Session,
    root: str | Path,
    repo_name: str,
    repo_url: str = "",
    batch: str = "",
    rights_default: str = "unknown",
    version: str = "0.1.0",
    commit_sha: str = "",
) -> list[SourceDocument]:
    root = Path(root)
    docs: list[SourceDocument] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        sha = sha256_file(path)
        existing = (
            session.query(SourceDocument)
            .filter_by(repo_name=repo_name, source_path=str(path.relative_to(root)))
            .first()
        )
        if existing and existing.file_sha256 == sha:
            docs.append(existing)  # idempotent: unchanged
            continue
        doc = existing or SourceDocument(
            id=str(uuid.uuid4()),
            repo_name=repo_name,
            repo_url=repo_url,
            source_path=str(path.relative_to(root)),
            rights_status=rights_default,
            ingestion_batch=batch,
            ingestion_version=version,
            commit_sha=commit_sha,
        )
        doc.file_sha256 = sha
        doc.file_size = path.stat().st_size
        doc.file_type = classify_file(path)
        session.add(doc)
        docs.append(doc)
    session.commit()
    log.info("inventoried %d files from %s", len(docs), root)
    return docs
