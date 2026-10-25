"""Gate 2 regression: region/board attribution is preserved per source,
never collapsed to "" when sources conflict.

The reference importer historically collapsed conflicting region assertions
to "" (and fell back to the cluster representative for boards).
These tests lock the fix: every source record's region/board assertion is
stored individually in question_region_board; conflicts are counted
and reported, not silently discarded.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from src.core.database import (
    CanonicalQuestion, QuestionRegionBoard, SourceDocument,
)
from src.pipeline.review import provenance_level, has_provenance
from scripts.import_reference import import_file
from src.source.adapters.prep_adapter import PrepAdapter


def _doc(session, repo="11plus-prep", path="bank.json"):
    d = SourceDocument(
        id=str(uuid.uuid4()), repo_name=repo,
        repo_url="https://github.com/SahirVhora/11plus-prep",
        source_path=path, file_sha256="0" * 64, file_size=1,
        file_type="json", commit_sha="abc123", rights_status="licensed",
        rights_note="MIT License", ingestion_batch="b")
    session.add(d)
    session.flush()
    return d


def _fp(q_text, answer):
    from src.core.hashing import content_fingerprint
    return content_fingerprint(q_text, answer)


def test_region_assertions_preserved_per_source(session, tmp_path):
    """Two source records for the same fingerprint with different regions
    both survive in question_region_board; canonical region stays ""."""
    from scripts.import_reference import _write_clusters

    d = _doc(session, path="bank.json")
    canon_a = {
        "subject": "maths", "topic": "arithmetic",
        "question_text": "What is 2+2?", "correct_answer": "B",
        "options_json": [{"letter": "A", "text": "3"},
                         {"letter": "B", "text": "4"}],
        "region": "birmingham", "exam_board": "GL",
        "source_question_id": "rec-1",
    }
    canon_b = {
        "subject": "maths", "topic": "arithmetic",
        "question_text": "What is 2+2?", "correct_answer": "B",
        "options_json": [{"letter": "A", "text": "3"},
                         {"letter": "B", "text": "4"}],
        "region": "london", "exam_board": "CEM",
        "source_question_id": "rec-2",
    }
    fp = _fp(canon_a["question_text"], canon_a["correct_answer"])

    clusters = {
        fp: [
            {"canon": canon_a, "filename": "bank.json", "doc": d,
             "changed": False, "source_id": "rec-1"},
            {"canon": canon_b, "filename": "bank.json", "doc": d,
             "changed": False, "source_id": "rec-2"},
        ],
    }
    per_file = {"bank.json": {"records": 2, "sha256": "0" * 64,
                              "document_id": d.id, "upstream_changed": False}}
    stats = _write_clusters(session, clusters, per_file, 0, PrepAdapter(),
                            "batch-1")

    assert stats["region_ambiguous"] == 1
    assert stats["board_conflicts"] == 1
    assert stats["imported"] == 1

    q = session.query(CanonicalQuestion).filter_by(fingerprint=fp).one()
    assert q.region == ""
    assert q.exam_board == ""

    rows = session.query(QuestionRegionBoard).filter_by(
        question_id=q.id).all()
    assert len(rows) == 2
    regions = {r.region for r in rows}
    boards = {r.board for r in rows}
    assert regions == {"birmingham", "london"}
    assert boards == {"GL", "CEM"}


def test_region_consensus_when_sources_agree(session, tmp_path):
    """All source records agree on region -> canonical region set."""
    from scripts.import_reference import _write_clusters

    d = _doc(session, path="bank.json")
    canon_a = {
        "subject": "maths", "topic": "arithmetic",
        "question_text": "What is 2+2?", "correct_answer": "B",
        "options_json": [{"letter": "A", "text": "3"},
                         {"letter": "B", "text": "4"}],
        "region": "birmingham", "exam_board": "GL",
        "source_question_id": "rec-1",
    }
    canon_b = dict(canon_a, source_question_id="rec-2")
    fp = _fp(canon_a["question_text"], canon_a["correct_answer"])

    clusters = {
        fp: [
            {"canon": canon_a, "filename": "bank.json", "doc": d,
             "changed": False, "source_id": "rec-1"},
            {"canon": canon_b, "filename": "bank.json", "doc": d,
             "changed": False, "source_id": "rec-2"},
        ],
    }
    per_file = {"bank.json": {"records": 2, "sha256": "0" * 64,
                              "document_id": d.id, "upstream_changed": False}}
    stats = _write_clusters(session, clusters, per_file, 0, PrepAdapter(),
                            "batch-1")

    assert stats["region_ambiguous"] == 0
    assert stats["board_conflicts"] == 0

    q = session.query(CanonicalQuestion).filter_by(fingerprint=fp).one()
    assert q.region == "birmingham"
    assert q.exam_board == "GL"

    rows = session.query(QuestionRegionBoard).filter_by(
        question_id=q.id).all()
    assert len(rows) == 2
    assert all(r.region == "birmingham" for r in rows)
    assert all(r.board == "GL" for r in rows)


def test_region_board_idempotent_on_reimport(session, tmp_path):
    """Re-importing the same source records does not duplicate
    question_region_board rows."""
    from scripts.import_reference import _write_clusters

    d = _doc(session, path="bank.json")
    canon = {
        "subject": "maths", "topic": "arithmetic",
        "question_text": "What is 2+2?", "correct_answer": "B",
        "options_json": [{"letter": "A", "text": "3"},
                         {"letter": "B", "text": "4"}],
        "region": "birmingham", "exam_board": "GL",
        "source_question_id": "rec-1",
    }
    fp = _fp(canon["question_text"], canon["correct_answer"])

    clusters = {
        fp: [{"canon": canon, "filename": "bank.json", "doc": d,
              "changed": False, "source_id": "rec-1"}],
    }
    per_file = {"bank.json": {"records": 1, "sha256": "0" * 64,
                              "document_id": d.id, "upstream_changed": False}}
    _write_clusters(session, clusters, per_file, 0, PrepAdapter(), "batch-1")
    _write_clusters(session, clusters, per_file, 0, PrepAdapter(), "batch-1")

    q = session.query(CanonicalQuestion).filter_by(fingerprint=fp).one()
    rows = session.query(QuestionRegionBoard).filter_by(
        question_id=q.id).all()
    assert len(rows) == 1  # no duplication


def test_import_file_region_board_written(session, tmp_path):
    """import_file path also writes question_region_board rows."""
    bank = tmp_path / "bank.json"
    bank.write_text(json.dumps([{
        "id": "prep-001", "subject": "maths", "topic": "arithmetic",
        "type": "mcq", "question": "What is 256 x 4?",
        "options": ["A) 984", "B) 1024"], "answer": "B",
        "explanation": "256 x 4 = 1024.", "region": "birmingham",
        "examBoard": "GL", "format": "mcq",
    }]), encoding="utf-8")
    d = _doc(session, path="bank.json")
    import scripts.import_reference as ir
    original = ir._doc_for
    ir._doc_for = lambda *a, **k: (d, False)
    try:
        stats = import_file(session, bank, PrepAdapter(), "11plus-prep",
                            "https://github.com/SahirVhora/11plus-prep",
                            "batch", "", run_id=None)
    finally:
        ir._doc_for = original

    assert stats["imported"] == 1
    q = session.query(CanonicalQuestion).one()
    rows = session.query(QuestionRegionBoard).filter_by(
        question_id=q.id).all()
    assert len(rows) == 1
    assert rows[0].region == "birmingham"
    assert rows[0].board == "GL"


def test_provenance_still_works_with_region_board(session):
    """Region/board additions don't break Gate 1 provenance."""
    q = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="maths", topic="arithmetic",
        question_type="mcq", question_text="What is 2+2?",
        correct_answer="B",
        options_json=[{"letter": "A", "text": "3"},
                      {"letter": "B", "text": "4"}],
        explanation="2+2=4.", fingerprint=str(uuid.uuid4()))
    session.add(q)
    session.flush()
    assert provenance_level(session, q.id) == "none"
    assert has_provenance(session, q.id) is False