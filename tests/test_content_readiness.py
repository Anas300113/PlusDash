"""Content-readiness regression tests.

These reproduce the concrete defects found during the readiness audit:

1. ``ingest`` CLI must bridge a source directory into the DB. The old CLI
   only had ``index`` (which reads existing SourcePage rows), so a freshly
   discovered directory was never ingested -- the documented vertical slice
   was not reproducible from a directory.
2. Tesseract is frequently installed but off-PATH on Windows. The OCR step
   must honour ``PLUS_TESSERACT_CMD`` so an installed engine is actually used,
   and must expose status that distinguishes a *configuration* problem from an
   *extraction* failure.
3. ``report`` must produce reproducible metrics from stored records only,
   distinguishing a genuine ``0`` from an unmeasurable ``null``, and must be
   strictly read-only (no writes, no approval).
"""
from __future__ import annotations

import uuid

from src.core.database import (
    CanonicalQuestion,
    CanonicalQuestionType,
    QuestionOccurrence,
    QuestionReviewStatus,
    SourceDocument,
    SourcePage,
)
from src.knowledge.report import content_report
from src.pipeline.ocr import (
    ocr_engine_status,
    resolve_tesseract_cmd,
)


def _write_minimal_pdf(path):
    """A 1-page PDF with real extractable text (no OCR needed)."""
    import fitz  # PyMuPDF is already a dependency
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Whole numbers place value worksheet page one.")
    doc.save(str(path))
    doc.close()


def _open(db_file):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(bind=create_engine(f"sqlite:///{db_file}"))()


# --------------------------------------------------------------------------
# 1. ingest CLI: directory -> DB bridge
# --------------------------------------------------------------------------
def test_ingest_cli_populates_db_from_directory(tmp_path):
    """Regression: the CLI ``ingest`` subcommand must discover a directory and
    persist documents + pages. Previously only ``index`` existed and it could
    only reflect rows already in the DB, so a real directory was never ingested.
    """
    from scripts.knowledge_cli import main as cli_main

    src = tmp_path / "src"
    src.mkdir()
    _write_minimal_pdf(src / "worksheet.pdf")
    db_file = tmp_path / "ingest.db"
    rc = cli_main(["--db", str(db_file), "ingest",
                   "--source", str(src), "--repo", "r", "--batch", "b",
                   "--no-ocr", "--assets", str(tmp_path / "assets")])
    assert rc == 0, "ingest must complete successfully"

    S = _open(db_file)
    try:
        assert S.query(SourceDocument).count() == 1
        assert S.query(SourcePage).count() >= 1
        doc = S.query(SourceDocument).first()
        assert "worksheet" in doc.source_path
    finally:
        S.close()


def test_ingest_cli_is_idempotent(tmp_path):
    """Re-running ingest against unchanged files creates no duplicate rows."""
    from scripts.knowledge_cli import main as cli_main

    src = tmp_path / "src"
    src.mkdir()
    _write_minimal_pdf(src / "same.pdf")
    db_file = tmp_path / "idem.db"
    args = ["--db", str(db_file), "ingest", "--source", str(src),
            "--repo", "r", "--batch", "b", "--no-ocr",
            "--assets", str(tmp_path / "assets")]
    assert cli_main(args) == 0
    assert cli_main(args) == 0

    S = _open(db_file)
    try:
        assert S.query(SourceDocument).count() == 1
        assert S.query(SourcePage).count() >= 1
    finally:
        S.close()


# --------------------------------------------------------------------------
# 2. OCR engine configuration
# --------------------------------------------------------------------------
def test_resolve_tesseract_cmd_honours_env(monkeypatch):
    """Regression: an installed-but-off-PATH tesseract must be usable via
    PLUS_TESSERACT_CMD instead of silently degrading OCR to 0."""
    cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    monkeypatch.setenv("PLUS_TESSERACT_CMD", cmd)
    assert resolve_tesseract_cmd() == cmd


def test_resolve_tesseract_cmd_none_when_unset(monkeypatch):
    monkeypatch.delenv("PLUS_TESSERACT_CMD", raising=False)
    assert resolve_tesseract_cmd() is None


def test_ocr_engine_status_distinguishes_config_from_failure(monkeypatch):
    """Status must always be a dict with an ``available`` flag and, when
    unavailable, a clear error -- so an operator can tell 'engine missing'
    (configuration) apart from a page-level extraction failure."""
    monkeypatch.setenv("PLUS_TESSERACT_CMD", "definitely-not-a-real-binary.exe")
    st = ocr_engine_status()
    assert isinstance(st, dict)
    assert st["available"] is False
    assert st.get("error")


# --------------------------------------------------------------------------
# 3. Content-readiness report
# --------------------------------------------------------------------------
def _seed(session):
    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="r", source_path="m.pdf",
        file_sha256=str(uuid.uuid4()), file_type="pdf", file_size=100)
    session.add(doc)
    session.flush()
    page = SourcePage(id=str(uuid.uuid4()), document_id=doc.id, page_number=1,
                      text_content="real text", text_confidence=0.9)
    session.add(page)
    qtype = CanonicalQuestionType(id=str(uuid.uuid4()), name="mcq",
                                  requires_options=True)
    session.add(qtype)
    q = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="Maths", topic="Numbers",
        question_type=qtype.id, question_text="What is 2+2?",
        correct_answer="B", explanation="2+2=4",
        options_json=[{"letter": "A", "text": "3"}, {"letter": "B", "text": "4"},
                      {"letter": "C", "text": "5"}],
        fingerprint="fp1")
    session.add(q)
    session.flush()
    occ = QuestionOccurrence(
        id=str(uuid.uuid4()), canonical_question_id=q.id, document_id=doc.id,
        page_id=page.id, question_number="1", linked_answer="B")
    session.add(occ)
    session.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    session.commit()
    return doc, page, q


def test_report_is_read_only_and_reproducible(session):
    _seed(session)
    before = (session.query(SourceDocument).count(),
              session.query(CanonicalQuestion).count())
    r1 = content_report(session)
    r2 = content_report(session)
    after = (session.query(SourceDocument).count(),
             session.query(CanonicalQuestion).count())
    assert before == after, "report must not write"
    assert r1 == r2, "report must be deterministic"
    assert r1["canonical_questions"]["total"] == 1
    assert r1["canonical_questions"]["valid_ordered_options"] == 1
    assert r1["canonical_questions"]["with_provenance"] == 1
    assert r1["canonical_questions"]["missing_provenance"] == 0
    assert r1["review"]["approved"] == 1
    assert r1["review"]["approved_usable_mcq"] == 1
    assert r1["question_occurrences"]["with_answer_evidence"] == 1


def test_report_empty_db_is_all_zeros_not_null(session):
    """Missing data must be distinguishable: schema-supported counts are 0,
    never null. This prevents 'no data' being mistaken for a real zero signal
    or, worse, a fabricated one."""
    r = content_report(session)
    assert r["source"]["documents"] == 0
    assert r["pages"]["total"] == 0
    assert r["canonical_questions"]["total"] == 0
    assert r["review"]["approved"] == 0
    # ocr_coverage is null only when no pages need OCR (undefined denominator)
    assert r["pages"]["ocr_coverage"] is None
    assert r["pages"]["needing_ocr"] == 0


def test_report_flags_missing_provenance_and_unordered_options(session):
    """A canonical question without a back-reference occurrence, or with
    unordered options, must be reported as such -- not silently counted as
    usable."""
    doc = SourceDocument(id=str(uuid.uuid4()), repo_name="r",
                         source_path="x.pdf", file_sha256=str(uuid.uuid4()),
                         file_type="pdf", file_size=1)
    session.add(doc)
    qt = CanonicalQuestionType(id=str(uuid.uuid4()), name="mcq",
                               requires_options=True)
    session.add(qt)
    q = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="VR", topic="Words",
        question_type=qt.id, question_text="q",
        options_json=[{"letter": "C", "text": "x"}, {"letter": "A", "text": "y"}],
        fingerprint="fp2")
    session.add(q)
    session.commit()
    r = content_report(session)
    assert r["canonical_questions"]["valid_ordered_options"] == 0
    assert r["canonical_questions"]["missing_provenance"] == 1
    assert r["canonical_questions"]["with_provenance"] == 0
