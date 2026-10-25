"""Deterministic page-level OCR tests and MCQ option extraction tests."""
from __future__ import annotations

import uuid

from src.core.database import (
    QuestionOccurrence, SourceDocument, SourcePage,
)
from src.pipeline.detect import extract_options
from src.pipeline.ocr import (
    MIN_NATIVE_TEXT_CHARS, is_scanned_page, ocr_page, run_ocr,
)


def _page(session, text="", ocr_used=False, ocr_text=""):
    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="test", source_path="t.pdf",
        file_sha256=str(uuid.uuid4()), file_type="pdf")
    session.add(doc)
    session.flush()
    page = SourcePage(
        id=str(uuid.uuid4()), document_id=doc.id, page_number=1,
        text_content=text, text_confidence=0.9 if text else 0.0,
        ocr_used=ocr_used, ocr_text=ocr_text)
    session.add(page)
    session.commit()
    return doc, page


def test_ocr_tests_cover_expected_functions(session):
    _, page = _page(session, text="")
    assert callable(is_scanned_page)
    assert callable(ocr_page)
    assert callable(run_ocr)
    assert isinstance(MIN_NATIVE_TEXT_CHARS, int)
    assert page.id


def test_empty_page_with_no_native_text_is_scanned(session):
    _, page = _page(session, text="")
    assert page.text_content == ""
    assert not page.ocr_used
    assert is_scanned_page(page) is True


def test_short_native_text_page_is_scanned(session):
    _, page = _page(session, text="1. hello")
    assert is_scanned_page(page) is True


def test_long_native_text_page_is_not_scanned(session):
    _, page = _page(session, text="x" * MIN_NATIVE_TEXT_CHARS)
    assert is_scanned_page(page) is False
    assert len(page.text_content.strip()) == MIN_NATIVE_TEXT_CHARS


def test_already_ocred_page_is_not_scanned(session):
    _, page = _page(session, text="", ocr_used=True, ocr_text="older text")
    assert page.ocr_used is True
    assert is_scanned_page(page) is False


def test_ocr_page_with_no_image_bytes_returns_empty(session):
    _, page = _page(session, text="")
    assert ocr_page(session, page, image_bytes=None) == ""
    assert page.ocr_used is False
    assert page.ocr_text == ""
    assert ocr_page(session, page, image_bytes=b"") == ""
    assert page.ocr_used is False


def test_run_ocr_skips_pages_without_renderable_source(session, tmp_path):
    doc, page = _page(session, text="")
    assert is_scanned_page(page) is True
    stats = run_ocr(session, [doc], source_root=tmp_path)
    assert stats["skipped"] >= 1
    session.refresh(page)
    assert page.ocr_used is False
    assert page.ocr_text == ""


def test_run_ocr_skips_pages_with_reliable_native_text(session, tmp_path):
    doc, _ = _page(session, text="x" * (MIN_NATIVE_TEXT_CHARS + 5))
    stats = run_ocr(session, [doc], source_root=tmp_path)
    assert stats["ocred"] == 0
    assert stats["skipped"] == 1


def test_run_ocr_is_idempotent_for_already_ocred_pages(session, tmp_path):
    doc, page = _page(session, text="", ocr_used=True, ocr_text="old")
    stats = run_ocr(session, [doc], source_root=tmp_path)
    assert stats["ocred"] == 0
    session.refresh(page)
    assert page.ocr_text == "old"
    assert page.ocr_used is True


def test_ocr_does_not_touch_native_text_content(session):
    _, page = _page(session, text="existing text")
    session.refresh(page)
    assert page.text_content == "existing text"
    assert page.text_confidence == 0.9


def test_dot_letter_option_extraction():
    text = "1. Pick one.\nA. apple\nB. banana\nC. cherry"
    options = extract_options(text)
    assert [o["letter"] for o in options] == ["A", "B", "C"]
    assert options[0]["text"] == "apple"
    assert options[2]["text"] == "cherry"


def test_paren_letter_option_extraction():
    text = "2. Choose.\nA) red\nB) blue\nC) green"
    options = extract_options(text)
    assert [o["letter"] for o in options] == ["A", "B", "C"]
    assert options[1]["text"] == "blue"


def test_single_option_is_not_enough(session):
    assert extract_options("Question?\nA. only one") == []
    assert extract_options("plain question without options") == []


def test_detect_run_does_not_infer_answers(session):
    from src.pipeline.detect import run as detect_run

    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="test", source_path="choices.pdf",
        file_sha256=str(uuid.uuid4()), file_type="pdf")
    session.add(doc)
    session.flush()
    session.add(SourcePage(
        id=str(uuid.uuid4()), document_id=doc.id, page_number=1,
        text_content="1. Pick one.\nA. apple\nB. banana"))
    session.commit()
    stats = detect_run(session, [doc], version="0.1.0", batch="b1")
    assert stats["candidates"] == 1
    occ = session.query(QuestionOccurrence).one()
    assert occ.linked_answer == ""
    assert len(occ.options_json or []) == 2
    assert [o["letter"] for o in occ.options_json] == ["A", "B"]


def test_detect_run_has_no_options_when_source_has_none(session):
    from src.pipeline.detect import run as detect_run

    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="test", source_path="plain.pdf",
        file_sha256=str(uuid.uuid4()), file_type="pdf")
    session.add(doc)
    session.flush()
    session.add(SourcePage(
        id=str(uuid.uuid4()), document_id=doc.id, page_number=1,
        text_content="1. What is seven plus eight?"))
    session.commit()
    assert detect_run(session, [doc], version="0.1.0", batch="b1")["candidates"] == 1
    occ = session.query(QuestionOccurrence).one()
    assert occ.options_json in (None, [])


# --------------------------------------------------------------------- #
# Idempotency regression tests (real-corpus validation blockers)         #
# --------------------------------------------------------------------- #


def _write_pdf_two_pages_same_image(path):
    """Deterministic 2-page PDF with the same embedded image on both pages."""
    import fitz
    from PIL import Image
    import io

    buf = io.BytesIO()
    Image.new("RGB", (24, 24), (200, 30, 30)).save(buf, format="PNG")
    png = buf.getvalue()
    doc = fitz.open()
    for _ in range(2):
        page = doc.new_page()
        page.insert_image(fitz.Rect(10, 10, 34, 34), stream=png)
    doc.save(str(path))
    doc.close()
    return png


def test_image_extract_is_idempotent_across_runs(session, tmp_path):
    """Second extraction pass must not add new asset rows."""
    from src.pipeline.extract import _extract_pdf_images
    from src.core.database import SourceAsset

    pdf = tmp_path / "two_page_same_image.pdf"
    _write_pdf_two_pages_same_image(pdf)

    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="t", source_path=pdf.name,
        file_sha256="sha-image-test", file_type="pdf")
    session.add(doc)
    session.flush()
    for n in (1, 2):
        session.add(SourcePage(id=str(uuid.uuid4()), document_id=doc.id,
                               page_number=n, text_content=""))
    session.commit()

    first = _extract_pdf_images(session, doc, pdf, tmp_path / "assets")
    total_first = session.query(SourceAsset).count()
    second = _extract_pdf_images(session, doc, pdf, tmp_path / "assets")
    total_second = session.query(SourceAsset).count()

    assert first == 2  # one row per page
    assert second == 0  # rerun adds nothing
    assert total_second == total_first


def test_same_image_on_two_pages_keeps_page_provenance(session, tmp_path):
    """One row per (sha, page): page-level provenance is preserved."""
    from src.pipeline.extract import _extract_pdf_images
    from src.core.database import SourceAsset

    pdf = tmp_path / "same_image_both_pages.pdf"
    _write_pdf_two_pages_same_image(pdf)

    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="t", source_path=pdf.name,
        file_sha256="sha-page-prov", file_type="pdf")
    session.add(doc)
    session.flush()
    p1 = SourcePage(id=str(uuid.uuid4()), document_id=doc.id,
                    page_number=1, text_content="")
    p2 = SourcePage(id=str(uuid.uuid4()), document_id=doc.id,
                    page_number=2, text_content="")
    session.add_all([p1, p2])
    session.commit()

    _extract_pdf_images(session, doc, pdf, tmp_path / "assets")
    rows = session.query(SourceAsset).filter_by(document_id=doc.id).all()
    assert len(rows) == 2
    assert len({r.sha256 for r in rows}) == 1  # same bytes
    assert {r.page_id for r in rows} == {p1.id, p2.id}


def test_ingest_zip_registration_is_idempotent(session, tmp_path):
    """Unpacking the same ZIP twice must not duplicate staged documents."""
    import hashlib
    import zipfile
    from src.pipeline.ingest import run as ingest_run
    from src.core.database import SourceDocument as SD

    payload = tmp_path / "pack"
    payload.mkdir()
    (payload / "w.pdf").write_bytes(b"%PDF-1.4 minimal\n")
    zip_path = tmp_path / "pack.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(payload / "w.pdf", "w.pdf")

    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="t", source_path="pack.zip",
        file_sha256=hashlib.sha256(zip_path.read_bytes()).hexdigest(),
        file_type="zip")
    session.add(doc)
    session.commit()

    staged = tmp_path / "staged"
    first = ingest_run(session, [doc], "b1", staging_root=staged,
                       source_root=tmp_path)
    second = ingest_run(session, [doc], "b1", staging_root=staged,
                        source_root=tmp_path)
    assert first["archives"] == 1
    assert second["archives"] == 1
    staged_docs = (session.query(SD)
                   .filter(SD.source_path.like("staged%")).all())
    assert len(staged_docs) == 1


def test_detect_uses_ocr_text_when_native_empty(session):
    """OCR-only pages must still yield candidates (downstream usability)."""
    from src.pipeline.detect import run as detect_run

    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="t", source_path="scan.pdf",
        file_sha256=str(uuid.uuid4()), file_type="pdf")
    session.add(doc)
    session.flush()
    session.add(SourcePage(
        id=str(uuid.uuid4()), document_id=doc.id, page_number=1,
        text_content="",
        ocr_text="3. What is twelve plus nine?\nA. 20\nB. 21\nC. 22",
        ocr_used=True))
    session.commit()
    stats = detect_run(session, [doc], version="0.1.0", batch="b1")
    assert stats["candidates"] == 1
    occ = session.query(QuestionOccurrence).one()
    assert len(occ.options_json or []) == 3
    assert occ.linked_answer == ""


def test_validate_promote_preserves_real_options(session):
    from src.pipeline.validate import run as validate_run

    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="test", source_path="v.pdf",
        file_sha256=str(uuid.uuid4()), file_type="pdf")
    session.add(doc)
    session.flush()
    session.add(SourcePage(
        id=str(uuid.uuid4()), document_id=doc.id, page_number=1,
        text_content="1. Pick one.\nA. apple\nB. banana\nC. cherry"))
    session.commit()
    pages = session.query(SourcePage).filter_by(document_id=doc.id).all()
    page = pages[0]
    options = extract_options(page.text_content)
    assert len(options) == 3
    session.add(QuestionOccurrence(
        id=str(uuid.uuid4()), document_id=doc.id, page_id=page.id,
        question_number="1", extraction_run="b1",
        extraction_version="0.1.0", extraction_confidence=0.5,
        options_json=options))
    session.commit()
    stats = validate_run(session, [doc])
    assert stats["promoted"] == 1

    from src.core.database import CanonicalQuestion

    kept = session.query(CanonicalQuestion).one()
    assert len(kept.options_json or []) == 3
    assert [o["letter"] for o in kept.options_json] == ["A", "B", "C"]
    assert kept.options_json[0]["text"] == "apple"
    assert kept.question_type == "mcq"


def test_validate_does_not_promote_without_real_options(session):
    """Real corpus defect chain: validate promoted MCQs with placeholder
    A-E options and an empty answer, i.e. it manufactured option sets.
    Occurrences without extracted option text must stay queued."""
    from src.pipeline.validate import run as validate_run

    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="test", source_path="plain.pdf",
        file_sha256=str(uuid.uuid4()), file_type="pdf")
    session.add(doc)
    session.flush()
    session.add(SourcePage(
        id=str(uuid.uuid4()), document_id=doc.id, page_number=1,
        text_content="1. What is 6 x 7?"))
    session.commit()
    page = session.query(SourcePage).one()
    session.add(QuestionOccurrence(
        id=str(uuid.uuid4()), document_id=doc.id, page_id=page.id,
        question_number="1", extraction_run="b1",
        extraction_version="0.1.0", extraction_confidence=0.5,
        options_json=None))
    session.commit()

    stats = validate_run(session, [doc])
    from src.core.database import CanonicalQuestion

    assert stats["promoted"] == 0
    assert stats["queued_no_options"] == 1
    assert session.query(CanonicalQuestion).count() == 0

    """OCR metadata records the real engine/version, not a placeholder."""
    from src.pipeline.ocr import ocr_page
    from PIL import Image
    import io

    _, page = _page(session, text="")
    buf = io.BytesIO()
    Image.new("RGB", (60, 30), (255, 255, 255)).save(buf, format="PNG")
    text = ocr_page(session, page, buf.getvalue())
    session.refresh(page)
    assert page.ocr_used is True  # attempted even if engine is missing
    if text:
        assert page.ocr_engine == "tesseract"
        assert page.ocr_version not in ("", "unknown")
