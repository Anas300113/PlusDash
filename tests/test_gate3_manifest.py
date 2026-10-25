"""Gate 3 regression: manifest semantics — immutable per-run record +
cumulative corpus snapshot.

Each ingestion run writes a PipelineRun record + an immutable manifest
file named with run_id, and a CorpusSnapshot capturing whole-corpus state
so incremental runs reconcile against the full corpus.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from src.core.database import (
    CanonicalQuestion, CorpusSnapshot, PipelineRun, QuestionOccurrence,
    QuestionRegionBoard, QuestionReviewStatus, SourceDocument,
)
from scripts.import_reference import (
    _write_corpus_snapshot, _write_manifests, import_banks, import_file,
)
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


def _make_question(session, fp="fp-1", region="", board=""):
    q = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="maths", topic="arithmetic",
        question_type="mcq", question_text="What is 2+2?",
        correct_answer="B",
        options_json=[{"letter": "A", "text": "3"},
                      {"letter": "B", "text": "4"}],
        explanation="2+2=4.", region=region, exam_board=board,
        fingerprint=fp)
    session.add(q)
    session.flush()
    return q


def test_corpus_snapshot_captures_whole_corpus_state(session):
    """CorpusSnapshot records total questions, occurrences, approved,
    pending counts and per-source breakdown."""
    d = _doc(session)
    q = _make_question(session, fp="fp-1")
    session.add(QuestionOccurrence(
        id=str(uuid.uuid4()), canonical_question_id=q.id,
        document_id=d.id, page_id="", question_number="rec-1",
        extraction_run="b", extraction_version="adapter-0.2.0",
        extraction_confidence=0.8))
    session.add(QuestionReviewStatus(
        question_id=q.id, status="approved", source="ingestion",
        confidence=0.9))
    session.commit()

    run = PipelineRun(
        id=str(uuid.uuid4()), pipeline_version="adapter-0.2.0",
        status="running")
    session.add(run)
    session.commit()

    _write_corpus_snapshot(session, run.id)

    snap = session.query(CorpusSnapshot).filter_by(run_id=run.id).one()
    assert snap.total_questions == 1
    assert snap.total_occurrences == 1
    assert snap.total_approved == 1
    assert snap.total_pending_review == 0
    assert snap.per_source_json is not None
    assert "11plus-prep" in snap.per_source_json


def test_manifest_includes_run_id_and_is_immutable(session, tmp_path):
    """Manifest file name includes run_id so prior runs are never
    overwritten; payload includes run_id."""
    d = _doc(session)
    canon = {
        "subject": "maths", "topic": "arithmetic",
        "question_text": "What is 2+2?", "correct_answer": "B",
        "options_json": [{"letter": "A", "text": "3"},
                         {"letter": "B", "text": "4"}],
        "region": "birmingham", "exam_board": "GL",
        "source_question_id": "rec-1",
    }
    clusters = {
        "fp-1": [{"canon": canon, "filename": "bank.json", "doc": d,
                  "changed": False, "source_id": "rec-1"}],
    }
    per_file = {"bank.json": {"records": 1, "sha256": "0" * 64,
                              "document_id": d.id, "upstream_changed": False}}
    result = import_banks(session, Path("."), PrepAdapter(), "11plus-prep",
                          "https://github.com/SahirVhora/11plus-prep",
                          "batch", "", run_id="run-123")

    manifests = {"11plus-prep": result}
    out_dir = tmp_path / "manifests"
    args = __import__("types").SimpleNamespace(source_sha="", batch="batch")
    _write_manifests(out_dir, manifests, args, run_id="run-123")

    files = list(out_dir.iterdir())
    assert len(files) == 1
    assert "run-123" in files[0].name

    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-123"
    assert "board_conflicts" in payload["totals"]


def test_manifest_differs_across_runs(session, tmp_path):
    """Two runs with different run_ids produce different manifest files
    (immutable per-run)."""
    d = _doc(session)
    canon = {
        "subject": "maths", "topic": "arithmetic",
        "question_text": "What is 2+2?", "correct_answer": "B",
        "options_json": [{"letter": "A", "text": "3"},
                         {"letter": "B", "text": "4"}],
        "region": "birmingham", "exam_board": "GL",
        "source_question_id": "rec-1",
    }
    clusters = {
        "fp-1": [{"canon": canon, "filename": "bank.json", "doc": d,
                  "changed": False, "source_id": "rec-1"}],
    }
    per_file = {"bank.json": {"records": 1, "sha256": "0" * 64,
                              "document_id": d.id, "upstream_changed": False}}
    result = import_banks(session, Path("."), PrepAdapter(), "11plus-prep",
                          "https://github.com/SahirVhora/11plus-prep",
                          "batch", "", run_id="run-abc")

    args = __import__("types").SimpleNamespace(source_sha="", batch="batch")

    out_dir = tmp_path / "manifests"
    _write_manifests(out_dir, {"11plus-prep": result}, args, run_id="run-abc")
    files_first = set(p.name for p in out_dir.iterdir())

    _write_manifests(out_dir, {"11plus-prep": result}, args, run_id="run-def")
    files_second = set(p.name for p in out_dir.iterdir())

    assert len(files_first | files_second) == 2  # both files exist
    assert "run-abc" in next(iter(files_first))
    assert "run-def" in next(iter(files_second - files_first))