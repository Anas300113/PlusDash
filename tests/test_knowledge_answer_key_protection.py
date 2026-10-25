"""Regression tests for the P0 answer-key leak through knowledge retrieval.

Reproduces the real leak measured against the live on-disk index:
  * ``answer_sheet.pdf`` and ``marking_scheme.pdf`` were indexed and their
    content ("Answer Sheet - Maths Paper 1 1. B 2. B ...") was returned
    verbatim by the unauthenticated ``POST /api/knowledge/search``.
  * Any caller could extract protected answer keys with no token.

The fix has two layers, both locked here:
  1. Build-time exclusion in ``iter_page_chunks`` (service.py): answer-key
     pages never enter a newly built/persisted index.
  2. Search-time defense-in-depth in ``KnowledgeIndex.search`` (retriever.py):
     an already-built stale index on disk can never surface key content even
     before it is rebuilt.

Both layers reuse the pipeline's authoritative classifier (link.py helpers),
never a duplicated heuristic.
"""
from __future__ import annotations

import uuid

from src.core.database import SourceDocument, SourcePage
from src.knowledge.chunk import Chunk
from src.knowledge.retriever import KnowledgeIndex
from src.knowledge.service import build_index


def _mkpage(session, filename, page_number, text="", ocr_text="",
            ocr_used=False):
    """Seed one SourceDocument + SourcePage row (same pattern as
    test_knowledge_engine.py)."""
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


# ---- Layer 1: build-time exclusion ----------------------------------------

def test_answer_key_filenames_never_enter_a_built_index(session):
    """Real leak reproduction: answer_sheet.pdf / marking_scheme.pdf content
    must never be indexed, while ordinary content still is (positive control)."""
    _mkpage(session, "answer_sheet.pdf", 1,
            "Answer Sheet - Maths Paper 1\n1. B\n2. B\n3. A\n4. C\n5. D")
    _mkpage(session, "marking_scheme.pdf", 1,
            "Marking Scheme: each correct answer is worth 1 mark. "
            "1 A 2 B 3 C 4 D 5 A")
    _mkpage(session, "maths_paper1.pdf", 1,
            "What is 2 + 2?\nA) 3\nB) 4\nC) 5\nChoose the correct option.")

    idx = build_index(session)
    filenames = {c.filename for c in idx.chunks}
    assert "answer_sheet.pdf" not in filenames
    assert "marking_scheme.pdf" not in filenames
    # positive control: normal content is still indexed
    assert "maths_paper1.pdf" in filenames


def test_key_heading_page_excluded_even_with_ordinary_filename(session):
    """The real classifier also detects key *headings* in page text, so a key
    page inside an innocently named document is excluded too."""
    _mkpage(session, "practice_paper.pdf", 1,
            "Answer Sheet\n1. B\n2. B\n3. A\n4. C")
    _mkpage(session, "fractions_notes.pdf", 1,
            "Equivalent fractions have the same value. One half equals "
            "two quarters and four eighths.")

    idx = build_index(session)
    key_chunks = [c for c in idx.chunks if c.filename == "practice_paper.pdf"]
    assert key_chunks == []          # heading page never indexed
    assert any(c.filename == "fractions_notes.pdf" for c in idx.chunks)


def test_build_index_search_returns_no_key_content(session):
    """End-to-end at the service layer: querying for keys must yield no hits,
    while a legitimate content query still retrieves evidence."""
    _mkpage(session, "answer_sheet.pdf", 1,
            "Answer Sheet - Maths Paper 1\n1. B\n2. B\n3. A")
    _mkpage(session, "fractions_notes.pdf", 1,
            "Equivalent fractions have the same value. One half equals "
            "two quarters and four eighths.")

    idx = build_index(session)
    key_hits = idx.search("answer key maths paper", top_k=5)
    assert all(h["filename"] != "answer_sheet.pdf" for h in key_hits)
    assert all("1. B" not in h["text"] for h in key_hits)


def _mkdoc_pages(session, filename, pages: dict[int, str]):
    """Seed ONE SourceDocument with several pages (a real corpus file is one
    document; _mkpage creates a fresh document per call and must not be used
    for multi-page document-level scenarios)."""
    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="test", source_path=filename,
        file_sha256=str(uuid.uuid4()), file_type="pdf")
    session.add(doc)
    session.flush()
    for page_number, text in pages.items():
        session.add(SourcePage(
            id=str(uuid.uuid4()), document_id=doc.id, page_number=page_number,
            text_content=text, text_confidence=0.9 if text else 0.0,
            ocr_used=False, ocr_text=""))
    session.commit()
    return doc


# ---- Gate scenario A: multi-page answer doc with innocuous filename ------
def test_multi_page_answer_doc_with_innocuous_filename_fully_excluded(
        session):
    """Scenario A: maths-paper.pdf page 1 opens with an answer-sheet heading;
    later pages contain answer-like material WITHOUT the heading. ALL pages of
    a classified answer document must be excluded, not just the heading page.
    (Document-level classification, not page-level.)"""
    _mkdoc_pages(session, "maths-paper.pdf", {
        1: "Answer Sheet\n1. B\n2. A\n3. C",
        2: "1. C\n2. D\n3. A\n4. B\n5. D\n6. C\n7. A\n8. B\n9. D\n10. A",
        3: "11. B\n12. C\n13. D\n14. A\n15. B\n16. C\n17. D\n18. A\n19. B",
    })
    _mkpage(session, "fractions_notes.pdf", 1,
            "Equivalent fractions have the same value. One half equals "
            "two quarters and four eighths.")

    idx = build_index(session)
    leaked = [c for c in idx.chunks if c.filename == "maths-paper.pdf"]
    assert leaked == [], f"answer-doc pages leaked into index: {leaked}"
    # positive control: the separate legitimate document remains searchable
    assert any(c.filename == "fractions_notes.pdf" for c in idx.chunks)


# ---- Layer 2: search-time defense-in-depth (stale on-disk index) ----------

_KEY_CHUNK = Chunk(
    chunk_id="stale-key-1",
    text="Answer Sheet - Maths Paper 1 1. B 2. B 3. A 4. C",
    filename="answer_sheet.pdf", page_number=1, page_id="sp1",
    document_id="sd1", index=0, char_start=0, char_end=52)
_NORMAL_CHUNK = Chunk(
    chunk_id="stale-normal-1",
    text="Equivalent fractions have the same value. One half equals "
         "two quarters and four eighths.",
    filename="fractions_notes.pdf", page_number=2, page_id="sp2",
    document_id="sd2", index=0, char_start=0, char_end=93)


def _stale_index_on_disk(tmp_path):
    """Simulate the pre-fix on-disk index: it still physically contains the
    answer-key chunk (the leak measured on the live index)."""
    idx = KnowledgeIndex()
    idx.build([_KEY_CHUNK, _NORMAL_CHUNK])
    path = tmp_path / "stale.joblib"
    idx.save(path)
    return path


def test_stale_index_still_contains_key_on_disk_but_search_filters_it(
        tmp_path):
    path = _stale_index_on_disk(tmp_path)
    loaded = KnowledgeIndex.load(path)
    # the stale artifact still physically holds the key chunk...
    assert loaded.size == 2
    assert any(c.filename == "answer_sheet.pdf" for c in loaded.chunks)
    # ...but no search path can surface it
    hits = loaded.search("answer key maths paper", top_k=5)
    assert all(h["filename"] != "answer_sheet.pdf" for h in hits)
    assert all("1. B" not in h["text"] for h in hits)
    # legitimate evidence is still retrievable (filter is surgical)
    good = loaded.search("equivalent fractions halves quarters", top_k=5)
    assert any(h["filename"] == "fractions_notes.pdf" for h in good)


def test_stale_index_rejects_filename_classified_doc_pages(tmp_path):
    """Scenario B (what IS guaranteed): chunks from a filename-classified
    document are rejected at search time even without the heading in the
    chunk text -- every page shares the document's filename, which the chunk
    retains as provenance (filename + document_id + meta.source_path)."""
    page2 = Chunk(
        chunk_id="stale-key-p2",
        text="1. C\n2. D\n3. A\n4. B\n5. D",          # no heading present
        filename="answer_sheet.pdf", page_number=2, page_id="sp9",
        document_id="sd9", index=0, char_start=0, char_end=20)
    normal = Chunk(
        chunk_id="stale-normal-2",
        text="Equivalent fractions have the same value. One half equals "
             "two quarters and four eighths.",
        filename="fractions_notes.pdf", page_number=1, page_id="sp8",
        document_id="sd8", index=0, char_start=0, char_end=93)
    idx = KnowledgeIndex()
    idx.build([page2, normal])
    path = tmp_path / "stale2.joblib"
    idx.save(path)
    loaded = KnowledgeIndex.load(path)
    hits = loaded.search("1 C 2 D 3 A answers", top_k=5)
    assert all(h["filename"] != "answer_sheet.pdf" for h in hits)
    good = loaded.search("equivalent fractions halves quarters", top_k=5)
    assert any(h["filename"] == "fractions_notes.pdf" for h in good)


def test_stale_index_limitation_heading_classified_doc_needs_rebuild():
    """Scenario B (DOCUMENTED LIMITATION, do not claim full stale-index
    protection): a stale index built BEFORE document-level classification may
    contain non-heading pages of a heading-classified document whose filename
    is innocuous. Such a chunk carries no flag distinguishing it from ordinary
    content -- filename and text are both innocent -- so search-time filtering
    cannot identify it. Only a rebuild removes it. This test pins the current
    behaviour honestly: the chunk IS returned, and the required remediation
    is 'rebuild the index', not 'trust the filter'."""
    doc_id = str(uuid.uuid4())
    orphan_key_page = Chunk(
        chunk_id="stale-orphan-key",
        # bare answer lines listed below -- no heading, innocuous filename
        text="1. C\n2. D\n3. A\n4. B\n5. D\nfinal answers listed below",
        filename="maths-paper.pdf", page_number=2, page_id="sp7",
        document_id=doc_id, index=0, char_start=0, char_end=20)
    idx = KnowledgeIndex()
    idx.build([orphan_key_page])
    hits = idx.search("final answers listed", top_k=5)
    # CURRENT behaviour pinned: cannot be detected from chunk provenance alone.
    # Operational requirement: rebuild indexes built before this fix
    # (python scripts/knowledge_cli.py index) -- see foundation-gate report.
    assert any(h["filename"] == "maths-paper.pdf" for h in hits)


# ---- End-to-end: the actual unauthenticated API endpoint ------------------

def test_knowledge_search_endpoint_does_not_leak_answer_keys(tmp_path,
                                                             monkeypatch):
    """The real leak route: unauthenticated POST /api/knowledge/search must
    never return answer-key content, even when the on-disk index is stale."""
    pytest = __import__("pytest")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    import src.api.main as api_main

    path = _stale_index_on_disk(tmp_path)
    monkeypatch.setattr(api_main, "_KNOWLEDGE_INDEX_PATH", str(path))
    client = TestClient(api_main.app)

    r = client.post("/api/knowledge/search",
                    json={"q": "answer key maths paper", "k": 5})
    assert r.status_code == 200
    body = r.json()
    evidence = body["evidence"]
    assert all(h["filename"] != "answer_sheet.pdf" for h in evidence)
    assert all("1. B" not in h["text"] for h in evidence)
    # no key evidence == honest insufficient-evidence signal, not a guess
    assert body["insufficient_evidence"] is True

    # positive control: a legitimate query still works through the endpoint
    r2 = client.post("/api/knowledge/search",
                     json={"q": "equivalent fractions halves quarters",
                           "k": 5})
    assert r2.status_code == 200
    ev2 = r2.json()["evidence"]
    assert any(h["filename"] == "fractions_notes.pdf" for h in ev2)


def test_endpoint_rebuilt_index_multi_page_answer_doc_clean(tmp_path,
                                                            monkeypatch,
                                                            session):
    """Scenario D on a REBUILT index: build from a DB containing the
    multi-page innocuous-filename answer doc, persist, then query through the
    real unauthenticated endpoint with alternate answer-seeking wording.
    No page of the classified document may appear in any response."""
    pytest = __import__("pytest")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    import src.api.main as api_main
    from src.knowledge.service import build_index

    _mkdoc_pages(session, "maths-paper.pdf", {
        1: "Answer Sheet\n1. B\n2. A\n3. C",
        2: "1. C\n2. D\n3. A\n4. B\n5. D\n6. C\n7. A\n8. B\n9. D\n10. A",
    })
    _mkpage(session, "fractions_notes.pdf", 1,
            "Equivalent fractions have the same value. One half equals "
            "two quarters and four eighths.")
    idx = build_index(session)
    path = tmp_path / "rebuilt.joblib"
    idx.save(path)
    monkeypatch.setattr(api_main, "_KNOWLEDGE_INDEX_PATH", str(path))
    client = TestClient(api_main.app)

    for q in ("answer key maths paper", "1. C 2. D 3. A 4. B answers",
              "marking scheme maths"):
        r = client.post("/api/knowledge/search", json={"q": q, "k": 10})
        assert r.status_code == 200
        for h in r.json()["evidence"]:
            assert h["filename"] != "maths-paper.pdf"
            assert "1. C" not in h["text"]
    # legitimate content still served
    r2 = client.post("/api/knowledge/search",
                     json={"q": "equivalent fractions halves quarters",
                           "k": 5})
    assert any(h["filename"] == "fractions_notes.pdf"
               for h in r2.json()["evidence"])
