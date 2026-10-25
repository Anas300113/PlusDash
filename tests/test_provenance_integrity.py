"""Gate 1 regression: provenance must be resolved against real rows.

The reference importer historically fabricated page provenance by writing the
*document* id into ``QuestionOccurrence.page_id`` (a dangling pointer into the
``source_pages`` foreign key). ``has_provenance()`` then only checked that the
ids were populated, so a fabricated page id passed the approval contract with
zero backing ``SourcePage`` rows.

These tests lock the fix: a page id only counts as page-level provenance when
it resolves to a real ``SourcePage`` belonging to the same document. Structured
JSON banks (no page extraction) are honestly graded as *file-level* provenance
-- a real ``SourceDocument`` plus a source record id -- never as page-level.
"""
from __future__ import annotations

import json
import uuid

from src.core.database import (
    CanonicalQuestion, QuestionOccurrence, QuestionReviewStatus,
    SourceDocument, SourcePage,
)
from src.pipeline.review import (
    approval_blockers, has_provenance, provenance_level,
)


def _question(session, text="What is 2+2?", answer="B"):
    q = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="maths", topic="arithmetic",
        question_type="mcq", question_text=text, correct_answer=answer,
        options_json=[{"letter": "A", "text": "3"},
                      {"letter": "B", "text": "4"}],
        explanation="2+2=4.", fingerprint=str(uuid.uuid4()))
    session.add(q)
    session.flush()
    return q


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


def _page(session, doc, number=1, text="stem"):
    p = SourcePage(
        id=str(uuid.uuid4()), document_id=doc.id, page_number=number,
        text_content=text, text_confidence=0.9)
    session.add(p)
    session.flush()
    return p


def _occurrence(session, q, doc, page_id="", question_number="rec-1"):
    o = QuestionOccurrence(
        id=str(uuid.uuid4()), canonical_question_id=q.id,
        document_id=doc.id, page_id=page_id, question_number=question_number,
        extraction_run="b", extraction_version="adapter-0.2.0",
        extraction_confidence=0.8)
    session.add(o)
    session.flush()
    return o


# ---- page-level provenance (PDF pipeline) ---------------------------------

def test_real_page_resolves_to_page_level(session):
    q = _question(session)
    d = _doc(session, path="paper.pdf")
    p = _page(session, d)
    _occurrence(session, q, d, page_id=p.id)
    assert provenance_level(session, q.id) == "page"
    assert has_provenance(session, q.id) is True


def test_page_from_a_different_document_is_not_page_level(session):
    """A page id resolving to a real SourcePage of ANOTHER document must not
    be trusted as this question's page provenance."""
    q = _question(session)
    d1 = _doc(session, path="a.pdf")
    d2 = _doc(session, path="b.pdf")
    foreign_page = _page(session, d2)
    _occurrence(session, q, d1, page_id=foreign_page.id)
    assert provenance_level(session, q.id) == "file"   # falls through


# ---- file-level provenance (JSON banks) -----------------------------------

def test_json_bank_record_is_honestly_file_level(session):
    q = _question(session)
    d = _doc(session, path="bank.json")
    _occurrence(session, q, d, page_id="", question_number="q-001")
    assert provenance_level(session, q.id) == "file"
    assert has_provenance(session, q.id) is True


def test_fabricated_page_id_is_never_page_level(session):
    """THE Gate 1 bug: page_id set to the document id (no real SourcePage)
    must not be graded page-level. It degrades to file-level only because a
    real document + record id back it."""
    q = _question(session)
    d = _doc(session, path="bank.json")
    _occurrence(session, q, d, page_id=d.id, question_number="q-001")
    assert provenance_level(session, q.id) == "file"   # NOT "page"
    assert d.id not in {p.id for p in session.query(SourcePage).all()}


def test_fabricated_page_with_no_real_document_is_none(session):
    """Fabricated ids resolving to NOTHING (no SourcePage, no SourceDocument)
    yield no provenance at all -- the pure-fabrication case."""
    q = _question(session)
    ghost = str(uuid.uuid4())
    o = QuestionOccurrence(
        id=str(uuid.uuid4()), canonical_question_id=q.id,
        document_id=ghost, page_id=ghost, question_number="q-001")
    session.add(o)
    session.flush()
    assert provenance_level(session, q.id) == "none"
    assert has_provenance(session, q.id) is False


def test_real_doc_but_no_record_id_is_none(session):
    """File-level provenance requires a source record id; a document alone is
    not enough to locate the question within the file."""
    q = _question(session)
    d = _doc(session, path="bank.json")
    _occurrence(session, q, d, page_id="", question_number="  ")
    assert provenance_level(session, q.id) == "none"
    assert has_provenance(session, q.id) is False


def test_no_occurrence_is_none(session):
    q = _question(session)
    assert provenance_level(session, q.id) == "none"
    assert has_provenance(session, q.id) is False


# ---- approval contract ----------------------------------------------------

def test_file_level_satisfies_provenance_blocker(session):
    """File-level provenance (real doc + record id) clears the provenance
    blocker, but never masquerades as page-level."""
    q = _question(session)
    d = _doc(session, path="bank.json")
    _occurrence(session, q, d, page_id=d.id, question_number="q-001")
    assert has_provenance(session, q.id) is True
    assert provenance_level(session, q.id) == "file"
    assert not any("provenance" in b
                   for b in approval_blockers(session, q.id))


def test_no_provenance_still_blocks_approval(session):
    q = _question(session)
    session.add(QuestionReviewStatus(question_id=q.id, status="extracted"))
    session.flush()
    blockers = approval_blockers(session, q.id)
    assert any("provenance" in b for b in blockers)


def test_mismatched_page_alone_without_document_is_none(session):
    """A page id pointing at a real page of another document, with a document
    id that does NOT resolve, is not enough for file-level either."""
    q = _question(session)
    d2 = _doc(session, path="b.pdf")
    foreign_page = _page(session, d2)
    o = QuestionOccurrence(
        id=str(uuid.uuid4()), canonical_question_id=q.id,
        document_id=str(uuid.uuid4()),  # ghost document
        page_id=foreign_page.id, question_number="q-001")
    session.add(o)
    session.flush()
    assert provenance_level(session, q.id) == "none"


# ---- importer no longer fabricates page ids -------------------------------

def test_reference_import_writes_empty_page_id(session, tmp_path):
    """The reference importer must NOT write the document id into page_id.
    File-sourced occurrences carry honest file-level provenance."""
    from scripts.import_reference import import_file
    from src.source.adapters.prep_adapter import PrepAdapter

    record = {
        "id": "prep-001", "subject": "maths", "topic": "arithmetic",
        "type": "mcq", "question": "What is 256 x 4?",
        "options": ["A) 984", "B) 1024"], "answer": "B",
        "explanation": "256 x 4 = 1024.", "region": "birmingham",
        "examBoard": "GL", "format": "mcq",
    }
    bank = tmp_path / "bank.json"
    bank.write_text(json.dumps([record]), encoding="utf-8")
    import_file(session, bank, PrepAdapter(), "11plus-prep",
                "https://github.com/SahirVhora/11plus-prep", "batch", "abc123")
    occ = session.query(QuestionOccurrence).one()
    assert occ.page_id == ""            # never the document id
    assert occ.document_id != ""        # real document provenance
    assert occ.question_number == "prep-001"
    assert provenance_level(session, occ.canonical_question_id) == "file"
    assert has_provenance(session, occ.canonical_question_id) is True
