"""PDF parsing tests: page counts and text extraction on fixtures."""
from __future__ import annotations

from pathlib import Path

FIX = Path("data/fixtures/spike")


def test_pdfs_parse_and_have_text():
    from pypdf import PdfReader
    pdfs = [p for p in sorted(FIX.glob("*.pdf")) if p.stat().st_size > 0]
    assert len(pdfs) >= 9
    for p in pdfs:
        reader = PdfReader(str(p))
        assert len(reader.pages) >= 1
        text = "".join((pg.extract_text() or "") for pg in reader.pages)
        assert len(text.strip()) > 20, f"{p.name} has no extractable text"


def test_answer_sheet_contains_answer_lines():
    from pypdf import PdfReader
    reader = PdfReader(str(FIX / "answer_sheet.pdf"))
    text = "".join((pg.extract_text() or "") for pg in reader.pages)
    assert "1." in text and "B" in text
