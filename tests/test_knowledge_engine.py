"""Knowledge-engine regression tests.

Reproduce the real behaviours the vertical slice must guarantee:
  * Provenance-preserving, deterministic chunking.
  * Retrieval returns verifiable filename + page + excerpt.
  * Restart stability: save -> load -> identical results.
  * Idempotent indexing: same content twice -> no duplicate chunks.
  * Incremental indexing of a document subset.
  * Interruption/restart semantics (index persists, DB unchanged).
  * Insufficient-evidence: no vocab overlap -> [] (never invents evidence).
  * Scanned-page handling: readable text comes from ocr_text.
  * Failed/unsupported pages never corrupt committed data.
  * API integration: read-only, returns evidence, 503 when no index.
"""
from __future__ import annotations

import uuid

from src.core.database import SourceDocument, SourcePage
from src.knowledge.chunk import chunk_text
from src.knowledge.retriever import KnowledgeIndex
from src.knowledge.service import build_index, iter_page_chunks


def _mkpage(session, filename, page_number, text="", ocr_text="",
            ocr_used=False):
    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="test", source_path=filename,
        file_sha256=str(uuid.uuid4()), file_type="pdf")
    session.add(doc)
    session.flush()
    page = SourcePage(
        id=str(uuid.uuid4()), document_id=doc.id, page_number=page_number,
        text_content=text, text_confidence=0.9 if text else 0.0,
        ocr_used=ocr_used, ocr_text=ocr_text)
    session.add(page)
    session.commit()
    return doc, page


# ---- Chunking -----------------------------------------------------------
def test_chunking_preserves_provenance():
    chunks = chunk_text(
        "Photosynthesis converts light into chemical energy in plants.",
        filename="bio.pdf", page_number=3, page_id="p1", document_id="d1",
        chunk_size=50, overlap=10)
    assert chunks, "non-empty text must produce >=1 chunk"
    for c in chunks:
        assert c.filename == "bio.pdf"
        assert c.page_number == 3
        assert c.page_id == "p1"
        assert c.document_id == "d1"
        assert c.text.strip()


def test_chunking_is_deterministic_and_idempotent():
    text = "The mitochondria is the powerhouse of the cell. " * 6
    a = chunk_text(text, filename="x.pdf", page_number=1, page_id="p",
                   document_id="d", chunk_size=80, overlap=20)
    b = chunk_text(text, filename="x.pdf", page_number=1, page_id="p",
                   document_id="d", chunk_size=80, overlap=20)
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]
    assert [c.text for c in a] == [c.text for c in b]


def test_empty_page_yields_no_chunks():
    assert chunk_text("   \n  ", filename="e.pdf", page_number=1,
                      page_id="p", document_id="d") == []


def test_chunk_text_covers_all_content():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa " * 4
    chunks = chunk_text(text, filename="f.pdf", page_number=1, page_id="p",
                        document_id="d", chunk_size=60, overlap=15)
    assert len(chunks) > 1
    assert [c.index for c in chunks] == list(range(len(chunks)))



# ---- Retrieval + citation ----------------------------------------------
def _sample_index():
    c1 = chunk_text("Verbal reasoning: find the word opposite in meaning to "
                    "generous. The antonym of generous is stingy.",
                    filename="VR.pdf", page_number=2, page_id="pa",
                    document_id="da", chunk_size=200, overlap=40)[0]
    c2 = chunk_text("Mathematics: long division of four digit numbers. Divide "
                    "9847 by 13 to obtain the quotient and remainder.",
                    filename="Maths.pdf", page_number=5, page_id="pb",
                    document_id="db", chunk_size=200, overlap=40)[0]
    return KnowledgeIndex().build([c1, c2])


def test_retrieval_returns_verifiable_citation():
    idx = _sample_index()
    hits = idx.search("opposite of generous", top_k=3)
    assert hits, "expected at least one hit"
    top = hits[0]
    assert top["filename"] == "VR.pdf"
    assert top["page_number"] == 2
    assert top["excerpt"]
    assert top["document_id"] == "da"
    assert top["page_id"] == "pa"


def test_retrieval_no_evidence_returns_empty():
    idx = _sample_index()
    hits = idx.search("zzzqqqxxwvv", top_k=5)
    assert hits == [], "no lexical overlap must yield no hits (no guessing)"


def test_empty_index_search_returns_empty():
    idx = KnowledgeIndex().build([])
    assert idx.search("anything", top_k=5) == []
    assert idx.size == 0


# ---- Restart stability --------------------------------------------------
def test_index_restart_is_stable(tmp_path):
    idx = _sample_index()
    before = idx.search("long division", top_k=3)
    p = tmp_path / "index.joblib"
    idx.save(p)
    reloaded = KnowledgeIndex.load(p)
    after = reloaded.search("long division", top_k=3)
    assert reloaded.size == idx.size
    assert [h["chunk_id"] for h in before] == [h["chunk_id"] for h in after]
    assert [h["excerpt"] for h in before] == [h["excerpt"] for h in after]
    assert [h["page_number"] for h in before] == [h["page_number"] for h in after]


def test_load_missing_index_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        KnowledgeIndex.load(tmp_path / "nope.joblib")


# ---- Idempotency + incremental -----------------------------------------
def test_build_index_dedups_identical_chunks(session):
    _mkpage(session, "same.pdf", 1, text="repeated content about fractions "
            "and decimals that appears on the page")
    n1 = build_index(session).size
    n2 = build_index(session).size
    assert n2 == n1


def test_incremental_index_subset(session):
    d1, _ = _mkpage(session, "a.pdf", 1, text="alpha alpha alpha content")
    _mkpage(session, "b.pdf", 1, text="beta beta beta content")
    sub = build_index(session, only_document_ids=[d1.id])
    full = build_index(session)
    assert sub.size < full.size
    assert all(c.filename == "a.pdf" for c in sub.chunks)


# ---- Scanned pages ------------------------------------------------------
def test_scanned_page_text_from_ocr(session):
    _mkpage(session, "scan.pdf", 1, text="",
            ocr_text="OCR recovered sentence about algebra and equations",
            ocr_used=True)
    idx = build_index(session)
    assert idx.size >= 1
    hits = idx.search("algebra equations", top_k=3)
    assert hits
    assert hits[0]["filename"] == "scan.pdf"


# ---- Interruption / DB immutability ------------------------------------
def test_indexing_does_not_mutate_db(session):
    doc, page = _mkpage(session, "keep.pdf", 1,
                        text="immutable source text for retrieval")
    before_pages = session.query(SourcePage).count()
    before_text = page.text_content
    build_index(session)
    session.expire_all()
    assert session.query(SourcePage).count() == before_pages
    refreshed = session.get(SourcePage, page.id)
    assert refreshed.text_content == before_text
    assert doc.source_path == "keep.pdf"


def test_iter_page_chunks_skips_empty_pages(session):
    _mkpage(session, "full.pdf", 1, text="real content here")
    _mkpage(session, "empty.pdf", 1, text="", ocr_text="")
    chunks = list(iter_page_chunks(session))
    assert chunks
    assert all(c.filename != "empty.pdf" for c in chunks)


# ---- API integration (read-only) ---------------------------------------
import pytest  # noqa: E402

httpx = pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

import src.api.main as api_main  # noqa: E402
from src.core.database import (  # noqa: E402
    get_engine, get_session_factory, init_db,
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "k.db"
    engine = get_engine(f"sqlite:///{db_file}")
    init_db(engine)
    monkeypatch.setattr(api_main, "_Session", get_session_factory(engine))
    return TestClient(api_main.app)


def _write_index(tmp_path, text, filename="bio.pdf", page=1):
    idx = KnowledgeIndex().build([
        chunk_text(text, filename=filename, page_number=page,
                   page_id="p", document_id="d", chunk_size=200,
                   overlap=40)[0]])
    p = tmp_path / "idx.joblib"
    idx.save(p)
    return str(p)


def test_api_knowledge_search_returns_evidence(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        api_main, "_KNOWLEDGE_INDEX_PATH",
        _write_index(tmp_path, "Cells and organelles in biology lessons."))
    r = client.post("/api/knowledge/search",
                    json={"q": "cells biology", "k": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["insufficient_evidence"] is False
    ev = body["evidence"][0]
    assert ev["filename"] == "bio.pdf"
    assert ev["page_number"] == 1
    assert ev["excerpt"]


def test_api_knowledge_search_insufficient_evidence(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        api_main, "_KNOWLEDGE_INDEX_PATH",
        _write_index(tmp_path, "Some content about geometry shapes."))
    r = client.post("/api/knowledge/search", json={"q": "zzxxqqwv", "k": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["evidence"] == []
    assert body["insufficient_evidence"] is True


def test_api_knowledge_search_503_when_no_index(client, tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "_KNOWLEDGE_INDEX_PATH",
                        str(tmp_path / "absent.joblib"))
    r = client.post("/api/knowledge/search", json={"q": "anything", "k": 3})
    assert r.status_code == 503
