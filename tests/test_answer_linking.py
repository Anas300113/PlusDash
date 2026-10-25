import uuid

from src.pipeline.link import is_answer_sheet, parse_answers
from src.core.database import (
    QuestionOccurrence, SourceDocument, SourcePage,
)


def test_parse_answers():
    text = "1. B\n2 - 42\nQ3: C"
    assert parse_answers(text) == {"1": "B", "2": "42", "3": "C"}


def test_is_answer_sheet_by_filename():
    doc = SourceDocument(id="x", repo_name="r", source_path="maths_answers.pdf",
                         file_sha256="s", file_size=1, file_type="pdf")
    assert is_answer_sheet(doc, []) is True


# --------------------------------------------------------------------- #
# Real-corpus regression tests (11NVRPaper2.pdf false answer links)      #
# --------------------------------------------------------------------- #

def _doc(session, path, pages):
    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="11-dump", source_path=path,
        file_sha256=str(uuid.uuid4()), file_type="pdf")
    session.add(doc)
    session.flush()
    for i, text in enumerate(pages, start=1):
        session.add(SourcePage(id=str(uuid.uuid4()), document_id=doc.id,
                               page_number=i, text_content=text))
    session.commit()
    return doc


def _page(session, doc, number):
    return (session.query(SourcePage)
            .filter_by(document_id=doc.id, page_number=number).one())


def test_question_paper_mentioning_answer_is_not_an_answer_key(session):
    """Real corpus: question papers say "Answer: ______" on every question.

    The pre-fix linker matched the substring "answer" anywhere in the
    document and therefore treated ordinary question papers as answer keys.
    """
    doc = _doc(session, "Maths_P9.pdf", [
        "1) What is 6 x 7?\nAnswer: _______________\n",
        "2) What is 84 / 7?\nAnswer: _______________\n",
    ])
    pages = session.query(SourcePage).filter_by(document_id=doc.id).all()
    assert is_answer_sheet(doc, pages) is False


def test_cross_document_numeric_coincidence_is_not_linked(session):
    """Real corpus defect: NVR q3 was linked to a CSSE maths answer ('193').

    The pre-fix linker merged every key document into one global
    number -> answer map, so an unrelated marking scheme's answer number 3
    became the NVR question's answer.
    """
    from src.pipeline.link import run as link_run

    key = _doc(session, "csse 2008 MATHS marking scheme.pdf", [
        "Marking Scheme\n",
        "Question Answer Marks\n1. 1457 1 mark\n3. 193 1 mark\n",
    ])
    nvr = _doc(session, "11NVRPaper2.pdf", ["A B C D E\nA B C D E\n"])
    session.add(QuestionOccurrence(
        id=str(uuid.uuid4()), document_id=nvr.id,
        page_id=_page(session, nvr, 1).id, question_number="3",
        extraction_run="b1", extraction_version="0.1.0",
        extraction_confidence=0.5))
    session.commit()

    stats = link_run(session, [key, nvr])
    occ = session.query(QuestionOccurrence).one()
    assert occ.linked_answer == ""
    assert stats["linked"] == 0
    assert stats["unresolved"] == 1


def test_ambiguous_key_table_leaves_answers_unresolved(session):
    """Real corpus: the NVR answers page numbers 1-5 three times (three
    sections). A repeated number with a different answer is ambiguous, so no
    answer may be claimed."""
    from src.pipeline.link import run as link_run

    doc = _doc(session, "11NVRPaper2.pdf", [
        "A B C D E\nA B C D E\n",
        "Answers\nSimilarities\n1. C\n2. D\n3. D\n"
        "Odd One Out\n1. E\n2. B\n3. C\nSeries\n1. B\n2. E\n3. C\n",
    ])
    for qn in ("1", "2", "3"):
        session.add(QuestionOccurrence(
            id=str(uuid.uuid4()), document_id=doc.id,
            page_id=_page(session, doc, 1).id, question_number=qn,
            extraction_run="b1", extraction_version="0.1.0",
            extraction_confidence=0.5))
    session.commit()

    stats = link_run(session, [doc])
    assert stats["linked"] == 0
    assert stats["unresolved"] == 3
    assert all(o.linked_answer == ""
               for o in session.query(QuestionOccurrence).all())


def test_own_document_key_table_links_answers(session):
    """Real corpus: 11ComprehensionPracticePaper has its own Answers page;
    single-table numbering links cleanly (no cross-document guessing)."""
    from src.pipeline.link import run as link_run

    doc = _doc(session, "11ComprehensionPracticePaper.pdf", [
        "1) What is an example of personification?\nA B C D\n",
        "Answers\n" + "".join("%d. %s\n" % (i, "ABCD"[i % 4])
                              for i in range(1, 11)),
    ])
    occs = []
    for qn in ("1", "2", "3"):
        o = QuestionOccurrence(
            id=str(uuid.uuid4()), document_id=doc.id,
            page_id=_page(session, doc, 1).id, question_number=qn,
            extraction_run="b1", extraction_version="0.1.0",
            extraction_confidence=0.5)
        session.add(o)
        occs.append(o)
    session.commit()

    stats = link_run(session, [doc])
    assert stats["linked"] == 3
    assert stats["answer_keys"] == 1
    assert occs[0].linked_answer == "B"
    assert occs[1].linked_answer == "C"
    assert occs[2].linked_answer == "D"


def test_link_run_reports_unresolved_remainder(session):
    """Unlinked occurrences must be reported, not silently dropped."""
    from src.pipeline.link import run as link_run

    doc = _doc(session, "plain_paper.pdf", ["1) Question text here\n"])
    session.add(QuestionOccurrence(
        id=str(uuid.uuid4()), document_id=doc.id,
        page_id=_page(session, doc, 1).id, question_number="1",
        extraction_run="b1", extraction_version="0.1.0",
        extraction_confidence=0.5))
    session.commit()

    stats = link_run(session, [doc])
    assert stats == {"linked": 0, "answer_keys": 0, "unresolved": 1}
