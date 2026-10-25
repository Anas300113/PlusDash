"""Image preservation tests: assets stored with hash, idempotent."""
from __future__ import annotations

import uuid

from src.core.database import SourceAsset, SourceDocument
from src.pipeline.extract import _store_image_asset
from pathlib import Path


def test_store_image_asset_idempotent(session, tmp_path):
    doc = SourceDocument(id=str(uuid.uuid4()), repo_name="spike",
                         source_path="img.png", file_sha256="s", file_size=4,
                         file_type="image")
    session.add(doc)
    session.commit()
    data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    n1 = _store_image_asset(session, doc, None, data, ".png", tmp_path)
    session.commit()
    n2 = _store_image_asset(session, doc, None, data, ".png", tmp_path)
    session.commit()
    assert n1 == 1 and n2 == 0  # second store is a no-op
    assets = session.query(SourceAsset).filter_by(document_id=doc.id).all()
    assert len(assets) == 1
    assert Path(tmp_path, assets[0].storage_path).exists()
