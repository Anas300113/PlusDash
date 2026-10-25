"""Hosted-upload flow: accept a source file, return a deterministic asset
id. Thumbnails are served only for known assets."""
from __future__ import annotations

import uuid

from fastapi import UploadFile
from sqlalchemy.orm import Session

from src.core.database import SourceDocument, SourceAsset
from src.core.hashing import sha256_bytes
from src.ingest.assets import store_image_bytes

UPLOAD_DIR = "data/uploads"


async def register_upload(session: Session, file: UploadFile, repo_name: str = "upload"):
    data = await file.read()
    sha = sha256_bytes(data)
    doc = session.query(SourceDocument).filter_by(file_sha256=sha).first()
    if doc is None:
        doc = SourceDocument(id=str(uuid.uuid4()), repo_name=repo_name,
                             source_path=file.filename or "upload.png",
                             file_sha256=sha, file_size=len(data),
                             file_type="image", rights_status="unknown")
        session.add(doc)
        session.flush()
    await file.seek(0)
    return doc.id


async def handle_upload(session: Session, file: UploadFile):
    doc_id = await register_upload(session, file, "upload")
    if file.content_type and file.content_type.startswith("image/"):
        ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename else ""
        if not ext:
            ext = "png"
        store_image_bytes(session, doc_id, None, (await file.read()), "." + ext, UPLOAD_DIR)
    return {"doc_id": doc_id}
