"""Chunked asset bodies with predictable content hashes, dedup at storage."""
from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from src.core.database import SourceAsset
from src.core.hashing import sha256_bytes
from src.core.logging import get_logger

log = get_logger("ingest.assets")


def store_image_bytes(session: Session, doc_id: str, page_id: str | None,
                      data: bytes, ext: str, assets_dir: str) -> str:
    """Store an image body, dedup on sha; return the asset id."""
    sha = sha256_bytes(data)
    if session.query(SourceAsset).filter_by(sha256=sha).first():
        return ""
    asset_id = str(uuid.uuid4())
    rel = Path(sha[:2]) / (sha + ext)
    dest = Path(assets_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    session.add(SourceAsset(id=asset_id, document_id=doc_id, page_id=page_id,
                            asset_type="raster", mime_type=mime_for_ext(ext),
                            sha256=sha, storage_path=str(rel)))
    session.commit()
    return asset_id


def mime_for_ext(ext: str) -> str:
    return {"png": "image/png", "jpg": "image/jpeg",
            "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext.lower().lstrip("."), "image/png")
