"""Regression tests for the source-grounded EXPLAIN endpoint.

The ``/api/explain/{question_id}`` feature integrates the trustworthy
knowledge engine into the learning loop's EXPLAIN step. It is security
sensitive and was introduced untested, so these tests lock down the exact
integrity properties the endpoint claims:

  * Answer-key protection: only APPROVED questions are explainable; a
    non-approved question returns 403 and never leaks answer/explanation.
  * No fabrication: with no index, or with no lexical overlap, ``source_evidence``
    is empty and ``grounding`` says so -- a citation is never invented and an
    excerpt is never labelled a verbatim quotation.
  * No ownership-gap inheritance: the endpoint is keyed by ``question_id``
    only; there is no ``student_id`` parameter to abuse.
  * Graceful degradation: a broken/absent index degrades to a no-evidence note,
    never a 500.

The index is built for real (KnowledgeIndex over chunked text), not mocked, so
the retrieval path under test is the production one.
"""
from __future__ import annotations

import uuid

from src.core.database import CanonicalQuestion, QuestionReviewStatus
from src.knowledge.chunk import chunk_text
from src.knowledge.retriever import KnowledgeIndex


def _approved_mcq(db, *, question_text="2+2?", correct_answer="B",
                  explanation="2+2 equals 4, which is option B."):
    q = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="maths", topic="maths-arithmetic",
        question_type="mcq", question_text=question_text,
        correct_answer=correct_answer, explanation=explanation,
        options_json=[{"letter": "A", "text": "3"},
                      {"letter": "B", "text": "4"}])
    db.add(q)
    db.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    db.commit()
    return q.id


def _real_index(filename="ksol.pdf", page_number=1,
                text="Addition sums combine two whole numbers to a total. "
                     "2+2 equals 4."):
    chunks = chunk_text(text, filename=filename, page_number=page_number,
                        page_id=str(uuid.uuid4()), document_id=str(uuid.uuid4()))
    return KnowledgeIndex().build(chunks)


def _api(tmp_path, monkeypatch):
    """Wired TestClient + session factory against a fresh temp DB."""
    from src.core.database import get_engine, get_session_factory, init_db
    from fastapi.testclient import TestClient
    import src.api.main as api_main

    engine = get_engine(f"sqlite:///{tmp_path / 'api.db'}")
    init_db(engine)
    S = get_session_factory(engine)
    monkeypatch.setattr(api_main, "_Session", S)
    return TestClient(api_main.app), S


# ---- Answer-key protection -------------------------------------------------
def test_explain_rejects_non_approved_question(tmp_path, monkeypatch):
    """A question that has not passed the trustworthy contract must never be
    explainable: 403, no answer/explanation leak. Guards the answer key."""
    c, S = _api(tmp_path, monkeypatch)
    db = S()
    q = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="maths", topic="maths-arithmetic",
        question_type="mcq", question_text="2+2?", correct_answer="B",
        explanation="secret explanation", options_json=[
            {"letter": "A", "text": "3"}, {"letter": "B", "text": "4"}])
    db.add(q)
    db.add(QuestionReviewStatus(question_id=q.id, status="extracted"))
    db.commit()
    qid = q.id
    db.close()

    r = c.get(f"/api/explain/{qid}")
    assert r.status_code == 403
    assert "correct_answer" not in r.text and "secret" not in r.text


def test_explain_missing_question_is_404(tmp_path, monkeypatch):
    c, _ = _api(tmp_path, monkeypatch)
    assert c.get(f"/api/explain/{uuid.uuid4()}").status_code == 404


def test_explain_without_index_returns_no_evidence_not_fabrication(
        tmp_path, monkeypatch):
    """No index built -> source_evidence empty + explicit grounding note, and
    the stored explanation is still returned. Never fabricates a citation."""
    import src.api.main as api_main
    c, S = _api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_main, "_KNOWLEDGE_INDEX_PATH",
                        str(tmp_path / "does-not-exist.joblib"))

    db = S()
    qid = _approved_mcq(db)
    db.close()

    r = c.get(f"/api/explain/{qid}")
    assert r.status_code == 200
    body = r.json()
    assert body["source_evidence"] == []
    assert body["grounding"]
    assert body["explanation"]


def test_explain_with_no_lexical_overlap_reports_no_evidence(
        tmp_path, monkeypatch):
    import src.api.main as api_main
    c, S = _api(tmp_path, monkeypatch)
    idx_path = tmp_path / "idx.joblib"
    KnowledgeIndex().build(chunk_text(
        "Photosynthesis converts light into chemical energy in plants.",
        filename="bio.pdf", page_number=1, page_id="p1",
        document_id="d1")).save(idx_path)
    monkeypatch.setattr(api_main, "_KNOWLEDGE_INDEX_PATH", str(idx_path))

    db = S()
    qid = _approved_mcq(db, question_text="Zorbling quixotic frobnicate?",
                        correct_answer="B")
    db.close()

    body = c.get(f"/api/explain/{qid}").json()
    assert body["source_evidence"] == []
    assert "no source-backed evidence" in body["grounding"]


def test_explain_grounds_in_source_with_verifiable_provenance(
        tmp_path, monkeypatch):
    import src.api.main as api_main
    c, S = _api(tmp_path, monkeypatch)
    idx_path = tmp_path / "idx.joblib"
    KnowledgeIndex().build(chunk_text(
        "2+2 equals 4. Addition of two whole numbers gives their total.",
        filename="ksol_arithmetic.pdf", page_number=7, page_id="p7",
        document_id="d7")).save(idx_path)
    monkeypatch.setattr(api_main, "_KNOWLEDGE_INDEX_PATH", str(idx_path))

    db = S()
    qid = _approved_mcq(
        db, question_text="What is the total when adding whole numbers?")
    db.close()

    body = c.get(f"/api/explain/{qid}").json()
    ev = body["source_evidence"]
    assert ev, "lexical overlap must produce evidence"
    top = ev[0]
    assert top["filename"] == "ksol_arithmetic.pdf"
    assert top["page_number"] == 7
    assert top["excerpt"].strip()
    assert top["score"] > 0
    assert top["document_id"] and top["page_id"]
    assert "not verbatim quotations" in body["grounding"]


def test_explain_has_no_student_identity_parameter():
    import src.api.main as api_main
    from fastapi.routing import APIRoute

    routes = {(r.path, tuple(sorted(r.methods or [])))
              for r in api_main.app.routes if isinstance(r, APIRoute)}
    assert ("/api/explain/{question_id}", ("GET",)) in routes
    for path, _ in routes:
        if "explain" in path:
            assert "student" not in path.lower()
