"""Reference-bank ingestion regression tests (external repo -> Plus).

Lock the controlled-ingestion contract for SahirVhora/11plus-prep banks:
  * schema mapping + malformed-record rejection (real adapter + validator),
  * deterministic dedup and repeat-ingestion idempotency,
  * region / exam-board metadata preservation,
  * provenance + licence attribution on SourceDocument,
  * upstream-change detection without silent overwrite,
  * manifest correctness,
  * answer-key safety: imported banks create NO SourcePage rows, so their
    answer-bearing records can never enter the knowledge retrieval index,
  * student-facing protection: imported questions are not approved and never
    appear in /api/questions.
"""
from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from src.core.database import (
    CanonicalQuestion, QuestionOccurrence, QuestionReviewStatus,
    SourceDocument, SourcePage,
)
from src.core.hashing import content_fingerprint
from src.canonical.validators import validate_canonical_question
from src.source.adapters.prep_adapter import PrepAdapter
from scripts.import_reference import _write_manifests, import_file


def _record(qid="bham-maths-001", question="What is 256 x 4?",
            options=None, answer="B", region="birmingham", board="GL"):
    return {
        "id": qid, "subject": "maths", "topic": "arithmetic",
        "difficulty": 2, "type": "mcq", "question": question,
        "options": options or ["A) 984", "B) 1024", "C) 1044", "D) 1124"],
        "answer": answer, "explanation": "256 x 4 = 1024.",
        "tags": ["multiplication"], "region": region, "examBoard": board,
        "format": "mcq",
    }


def _write_bank(tmp_path, name, records):
    p = tmp_path / name
    p.write_text(json.dumps(records), encoding="utf-8")
    return p


def _import(session, path, batch="test-batch", source_sha="abc123"):
    return import_file(session, path, PrepAdapter(), "11plus-prep",
                       "https://github.com/SahirVhora/11plus-prep", batch,
                       source_sha)


# ---- schema mapping and rejection -----------------------------------------

def test_prep_mapping_preserves_region_board_and_options(session):
    adapter = PrepAdapter()
    canon = adapter.to_canonical(_record())
    assert validate_canonical_question(canon).passed
    assert canon["region"] == "birmingham"
    assert canon["exam_board"] == "GL"
    assert canon["subject"] == "maths"
    assert canon["options_json"][1] == {"letter": "B", "text": "1024"}
    assert canon["correct_answer"] == "B"


def test_malformed_record_is_rejected_not_imported(session, tmp_path):
    bad = _record(answer="Z")           # answer not among options
    path = _write_bank(tmp_path, "bad.json", [bad])
    stats = _import(session, path)
    assert stats["imported"] == 0 and stats["invalid"] == 1


# ---- dedup and idempotency -------------------------------------------------

def test_repeat_import_is_idempotent(session, tmp_path):
    path = _write_bank(tmp_path, "bank.json", [_record()])
    first = _import(session, path)
    assert first["imported"] == 1
    before = session.query(CanonicalQuestion).count()
    second = _import(session, path)
    assert second["imported"] == 0 and second["dupes"] == 1
    assert session.query(CanonicalQuestion).count() == before


def test_cross_file_content_duplicates_are_skipped(session, tmp_path):
    a = _write_bank(tmp_path, "a.json", [_record(qid="a-1")])
    b = _write_bank(tmp_path, "b.json",
                    [_record(qid="b-1")])   # identical text+answer
    assert _import(session, a)["imported"] == 1
    stats_b = _import(session, b)
    assert stats_b["imported"] == 0 and stats_b["dupes"] == 1


def test_upstream_change_is_detected_never_overwritten(session, tmp_path):
    path = _write_bank(tmp_path, "bank.json", [_record()])
    first = _import(session, path)
    fp_before = content_fingerprint(
        "What is 256 x 4?", "B")
    # upstream changes the file content
    path.write_text(json.dumps(
        [_record(question="What is 300 x 4?")]), encoding="utf-8")
    stats = _import(session, path)
    assert stats["upstream_changed"] is True
    # nothing was overwritten: original question still present, count stable
    assert (session.query(CanonicalQuestion)
            .filter_by(fingerprint=fp_before).count()) == 1
    assert (session.query(SourceDocument)
            .filter_by(source_path="bank.json").one().file_sha256
            == first["sha256"])


# ---- provenance, licence and manifest -------------------------------------

def test_source_document_records_sha_and_attribution(session, tmp_path):
    path = _write_bank(tmp_path, "bank.json", [_record()])
    _import(session, path, source_sha="d970c16614c95140")
    doc = session.query(SourceDocument).filter_by(
        source_path="bank.json").one()
    assert doc.commit_sha == "d970c16614c95140"
    assert doc.repo_url == "https://github.com/SahirVhora/11plus-prep"
    assert "MIT License" in doc.rights_note
    assert "Sahir Vhora" in doc.rights_note


def test_manifest_records_source_and_outcomes(session, tmp_path):
    path = _write_bank(tmp_path, "bank.json",
                       [_record(), _record(answer="Z")])
    stats = import_banks(tmp_path, session, batch="test-batch")
    args = Namespace(source_sha="d970c16614c95140", batch="test-batch")
    _write_manifests(tmp_path / "m",
                     {"11plus-prep": stats}, args, run_id=None)
    man = json.loads(
        (tmp_path / "m" / "11plus-prep-d970c16614c9-unknown.json")
        .read_text(encoding="utf-8"))
    assert man["source_sha"] == "d970c16614c95140"
    assert "SahirVhora/11plus-prep" in man["source_repo"]
    assert "MIT License" in man["licence"]
    assert man["run_id"] is None
    assert man["totals"]["records"] == 2
    assert man["totals"]["imported"] == 1
    assert man["totals"]["invalid"] == 1
    assert man["totals"]["board_conflicts"] == 0
    assert man["files"][0]["sha256"]


# ---- Gate 1: deterministic dedup with retained associations ----------------

def import_banks(bank_dir, session, batch="gate1"):
    from scripts.import_reference import import_banks as _ib
    return _ib(session, bank_dir, PrepAdapter(), "11plus-prep",
               "https://github.com/SahirVhora/11plus-prep", batch,
               "d970c16614c95140")


def _cluster_pair(tmp_path, dirname, first_name, second_name):
    """Two banks containing the same question; first asserts nothing,
    second asserts birmingham/GL with a longer explanation."""
    d = tmp_path / dirname
    d.mkdir()
    base = dict(_record(), region="", examBoard="mixed")
    (d / first_name).write_text(json.dumps([base]), encoding="utf-8")
    variant = dict(_record(), id="bham-english-008-x", region="birmingham",
                   examBoard="GL",
                   explanation="Because 256 x 4 = 1024, option B.")
    (d / second_name).write_text(json.dumps([variant]), encoding="utf-8")
    return d


def _canonical_state(session, fp):
    q = session.query(CanonicalQuestion).filter_by(fingerprint=fp).one()
    occ = sorted(
        (o.document_id, o.question_number)
        for o in session.query(QuestionOccurrence)
        .filter_by(canonical_question_id=q.id).all())
    return q, occ


def test_subject_bank_first_keeps_region_and_occurrences(session, tmp_path):
    """Old defect: importing the subject-bank copy first silently dropped the
    regional copy's region/board and its source occurrence."""
    d = _cluster_pair(tmp_path, "s1", "a-maths.json", "b-birmingham.json")
    stats = import_banks(d, session)
    assert stats["imported"] == 1 and stats["duplicates_merged"] == 1
    fp = content_fingerprint("What is 256 x 4?", "B")
    q, occ = _canonical_state(session, fp)
    assert q.region == "birmingham" and q.exam_board == "GL"
    docs = session.query(SourceDocument).filter(
        SourceDocument.source_path.in_(
            ["a-maths.json", "b-birmingham.json"])).all()
    assert len(occ) == 2          # both source files keep an occurrence
    assert {o[0] for o in occ} == {doc.id for doc in docs}


def test_region_bank_first_same_outcome(session, tmp_path):
    """File order must not change the association outcome."""
    d = _cluster_pair(tmp_path, "s2", "a-birmingham.json", "b-maths.json")
    stats = import_banks(d, session)
    assert stats["imported"] == 1
    fp = content_fingerprint("What is 256 x 4?", "B")
    q, occ = _canonical_state(session, fp)
    assert q.region == "birmingham" and q.exam_board == "GL"
    assert len(occ) == 2


def test_conflicting_regions_invent_nothing(session, tmp_path):
    """kent + yorkshire both assert a region for identical content:
    canonical region stays empty (ambiguous), board resolves to the single
    distinct board, and both occurrences survive."""
    d = tmp_path / "s3"
    d.mkdir()
    base = _record()
    (d / "a-kent.json").write_text(json.dumps(
        [dict(base, region="kent", examBoard="GL")]), encoding="utf-8")
    (d / "b-yorkshire.json").write_text(json.dumps(
        [dict(base, id="yorks-1", region="yorkshire",
              examBoard="GL")]), encoding="utf-8")
    import_banks(d, session)
    q, occ = _canonical_state(
        session, content_fingerprint("What is 256 x 4?", "B"))
    assert q.region == ""              # not kent, not yorkshire, not both
    assert q.exam_board == "GL"
    assert len(occ) == 2


def test_banks_second_run_backfills_and_is_idempotent(session, tmp_path):
    d = _cluster_pair(tmp_path, "s4", "a-maths.json", "b-birmingham.json")
    first = import_banks(d, session)
    assert first["occurrences_added"] == 2
    second = import_banks(d, session)
    assert second["imported"] == 0
    assert second["occurrences_added"] == 0
    fp = content_fingerprint("What is 256 x 4?", "B")
    _, occ = _canonical_state(session, fp)
    assert len(occ) == 2          # no duplicate occurrences either



# ---- answer-key structural safety -----------------------------------------

def test_imported_banks_create_no_retrievable_pages(session, tmp_path):
    """Answer-bearing JSON banks must never become retrieval content. The
    import creates SourceDocument + canonical rows but ZERO SourcePage rows,
    so the knowledge index (which only reads SourcePage.text) can never
    contain the banks' answers or explanations."""
    from src.knowledge.service import build_index
    path = _write_bank(tmp_path, "bank.json", [_record()])
    stats = _import(session, path)
    doc_id = stats["document_id"]
    assert session.query(SourcePage).filter_by(
        document_id=doc_id).count() == 0
    idx = build_index(session)
    assert all(c.document_id != doc_id for c in idx.chunks)


# ---- student-facing protection --------------------------------------------

def test_imported_questions_are_not_student_visible(tmp_path, monkeypatch):
    """Imported questions arrive as 'validation_required' -- the /api/questions
    student feed must contain none of them until the review workflow approves."""
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from src.core.database import (
        get_engine, get_session_factory, init_db,
    )
    import src.api.main as api_main

    engine = get_engine(f"sqlite:///{tmp_path / 'api.db'}")
    init_db(engine)
    S = get_session_factory(engine)
    s = S()
    path = _write_bank(tmp_path, "bank.json", [_record()])
    stats = _import(s, path)
    qid = (s.query(CanonicalQuestion)
           .filter_by(fingerprint=content_fingerprint(
               "What is 256 x 4?", "B")).one().id)
    s.close()
    monkeypatch.setattr(api_main, "_Session", S)
    client = TestClient(api_main.app)
    rows = client.get("/api/questions").json()
    assert all(r["id"] != qid for r in rows)
    assert stats["imported"] == 1   # question exists, just not exposed
