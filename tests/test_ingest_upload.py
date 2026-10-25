from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from starlette.datastructures import Headers

from src.core.database import SourceAsset, SourceDocument, get_engine, get_session_factory, init_db
from src.core.hashing import sha256_bytes
from src.ingest import upload as upload_module


def test_upload_registers_content_and_stores_exact_image_bytes(tmp_path, monkeypatch):
    engine = get_engine(f"sqlite:///{tmp_path / 'upload-test.sqlite'}")
    init_db(engine)
    session_factory = get_session_factory(engine)
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(upload_module, "UPLOAD_DIR", str(upload_dir))
    payload = b"isolated test image bytes"
    file = UploadFile(
        file=BytesIO(payload),
        filename="sample.png",
        headers=Headers({"content-type": "image/png"}),
    )
    db = session_factory()
    try:
        result = asyncio.run(upload_module.handle_upload(db, file))
        document = db.query(SourceDocument).filter_by(id=result["doc_id"]).one()
        asset = db.query(SourceAsset).filter_by(document_id=document.id).one()
        assert document.file_sha256 == sha256_bytes(payload)
        assert document.file_size == len(payload)
        assert Path(upload_dir, asset.storage_path).read_bytes() == payload
    finally:
        db.close()
        engine.dispose()
