import uuid

from src.core.database import SourceDocument
from src.source.inventory import classify_file, inventory_directory


def test_classify_file():
    from pathlib import Path
    assert classify_file(Path("a.pdf")) == "pdf"
    assert classify_file(Path("b.pptx")) == "pptx"
    assert classify_file(Path("c.zip")) == "zip"
    assert classify_file(Path("d.png")) == "image"


def test_inventory_idempotent(session, tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    docs1 = inventory_directory(session, tmp_path, "spike", batch="b1")
    docs2 = inventory_directory(session, tmp_path, "spike", batch="b1")
    assert len(docs1) == 1 and len(docs2) == 1
    assert docs1[0].id == docs2[0].id


def test_inventory_detects_change(session, tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("v1", encoding="utf-8")
    d1 = inventory_directory(session, tmp_path, "spike", batch="b1")[0]
    sha1 = d1.file_sha256
    session.expunge_all()
    p.write_text("v2-contents-different", encoding="utf-8")
    d2 = inventory_directory(session, tmp_path, "spike", batch="b1")[0]
    assert sha1 != d2.file_sha256
