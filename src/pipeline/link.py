"""Step: answer linking.

Evidence rules (established from real-corpus failure analysis):

* Only documents explicitly identified as answer keys may supply answers:
  a filename marker (answers / marking scheme / mark scheme) or a page
  heading such as "Answers", "Answer Sheet" or "Marking Scheme". A plain
  occurrence of the word "answer" inside question text ("Answer: ______")
  is NOT key evidence.
* One key page is one answer table. A document's key table is its densest
  answer page, preferring pages carrying a key heading. Question numbers
  that repeat in that table with different values are ambiguous, so they
  stay unresolved -- no answer is inferred.
* An occurrence is linked only from the key table of its own document. The
  linker cannot resolve paper identity across documents, so a numeric match
  against an unrelated document's key is not evidence.

Matches answer-sheet lines ('1. B', '1 - 42', 'Q1: C') by question number.
Multiple occurrences of the same question are preserved.
"""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.orm import Session

from src.core.database import QuestionOccurrence, SourceDocument, SourcePage
from src.core.logging import get_logger

log = get_logger("pipeline.link")

ANSWER_LINE = re.compile(
    r"(?:^|\n)\s*(?:Q\s?)?(\d{1,3})\s*[.).:\-]\s*([A-Ea-e]|\d[\d,./]*)\b")

# Filename markers for an answer key (matched on word tokens, not substrings).
KEY_STEM_TOKENS = {"answer", "answers", "ans", "key", "marking", "scheme"}
KEY_HEADING = re.compile(
    r"^[ \t]*(answers?|answer key|answers and marks|marking scheme|"
    r"mark scheme|answers? sheet)[ \t]*:?[ \t]*$",
    re.IGNORECASE | re.MULTILINE)

# Kept for API compatibility with earlier callers.
ANSWER_HINTS = ("answer", "marking", "mark scheme", "mark-scheme", "answers",
                "key")


def _stem_tokens(path: str) -> set[str]:
    name = Path(str(path)).name
    stem = name.rsplit(".", 1)[0].lower()
    return {t for t in re.split(r"[^a-z0-9]+", stem) if t}


def _has_key_heading(page_text: str) -> bool:
    return bool(KEY_HEADING.search((page_text or "")[:400]))


def is_answer_sheet(doc: SourceDocument, pages: list[SourcePage]) -> bool:
    """True only when the document carries explicit answer-key evidence."""
    if _stem_tokens(doc.source_path) & KEY_STEM_TOKENS:
        return True
    return any(_has_key_heading(getattr(p, "text_content", "") or "")
               for p in pages)


def filename_is_answer_key(filename: str) -> bool:
    """True when a filename alone marks a document as an answer key.

    Single source of truth for the filename half of :func:`is_answer_sheet`,
    reused by the knowledge engine so answer-key content is never made
    retrievable. Matches whole word tokens only, so a student worksheet named
    ``answers-review-activity.pdf`` is still caught but ``transkey.pdf`` (which
    merely contains the substring "key") is not.
    """
    return bool(_stem_tokens(filename) & KEY_STEM_TOKENS)


def text_is_answer_key_heading(text: str) -> bool:
    """True when page text opens with an explicit answer-key/marking heading.

    Reuses the exact same heading matcher as :func:`is_answer_sheet`.
    """
    return _has_key_heading(text or "")


def parse_answers(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in ANSWER_LINE.finditer("\n" + text)}


def key_table(pages: list[SourcePage]) -> tuple[dict[str, str], set[str]]:
    """Return (table, ambiguous) for one document.

    The table comes from the densest answer page (preferring pages that
    carry a key heading) because one page is one answer table; merging
    pages mixes blank answer sheets with the real key. Numbers repeating
    in that table with different values are ambiguous and excluded.
    """
    best: dict[str, str] = {}
    best_conf: set[str] = set()
    best_rank = (-1, -1)
    for page in pages:
        text = getattr(page, "text_content", "") or ""
        table: dict[str, str] = {}
        conf: set[str] = set()
        for m in ANSWER_LINE.finditer("\n" + text):
            num, val = m.group(1), m.group(2).strip()
            if num in table and table[num] != val:
                conf.add(num)
            table[num] = val
        rank = (1 if _has_key_heading(text) else 0, len(table))
        if rank > best_rank:
            best, best_conf, best_rank = table, conf, rank
    return best, best_conf


def run(session: Session, docs: list[SourceDocument]) -> dict:
    tables: dict[str, dict[str, str]] = {}
    ambiguous: dict[str, set[str]] = {}
    for doc in docs:
        pages = session.query(SourcePage).filter_by(document_id=doc.id).all()
        if is_answer_sheet(doc, pages):
            table, conf = key_table(pages)
            if table:
                tables[doc.id] = table
                ambiguous[doc.id] = conf

    linked = 0
    unresolved = 0
    for occ in session.query(QuestionOccurrence).all():
        table = tables.get(occ.document_id)
        if not table:
            unresolved += 1
            continue
        num = str(occ.question_number)
        ans = table.get(num, "")
        if ans and num not in ambiguous.get(occ.document_id, set()):
            occ.linked_answer = ans
            linked += 1
        else:
            unresolved += 1
    session.commit()
    log.info("link: %d occurrences matched to own-document keys, %d unresolved "
             "(%d key documents)", linked, unresolved, len(tables))
    return {"linked": linked, "answer_keys": len(tables),
            "unresolved": unresolved}
