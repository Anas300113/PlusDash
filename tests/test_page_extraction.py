"""Page extraction tests: SourcePage rows created per PDF page."""
from __future__ import annotations

from pathlib import Path

from src.core.database import SourceDocument, SourcePage
from src.pipeline import extract as extract_step
from src.source.inventory import inventory_directory


def test_page_rows_created(session, tmp_path):
    import shutil
    for p in Path("data/fixtures/spike").glob("*.pdf"):
        shutil.copy(p, tmp_path / p.name)
    docs = inventory_directory(session, tmp_path, "spike", batch="t")
    pdf_docs = [d for d in docs if d.file_type == "pdf"]
    assert pdf_docs
    total = 0
    for doc in pdf_docs:
        pages = extract_step.extract_pdf_pages(tmp_path / doc.source_path, session, doc)
        total += len(pages)
        assert all(p.page_number >= 1 for p in pages)
    assert total >= len(pdf_docs)
    # idempotent: re-run does not duplicate rows
    for doc in pdf_docs:
        before = session.query(SourcePage).filter_by(document_id=doc.id).count()
        extract_step.extract_pdf_pages(tmp_path / doc.source_path, session, doc)
        after = session.query(SourcePage).filter_by(document_id=doc.id).count()
        assert before == after
