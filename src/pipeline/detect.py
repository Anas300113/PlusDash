"""Step: question candidate detection with MCQ option extraction.

Deterministic pattern-based splitter: splits page text on numbered markers
like '1.', 'Q1', '(1)'. Also extracts MCQ options from the body when present.

Option patterns detected:
  A. text    B. text    (letter + dot + space)
  A) text    B) text    (letter + paren + space)
  (A) text   (B) text   (paren + letter + paren)
  A - text   B - text   (letter + dash + space)

Extracted options are stored on the QuestionOccurrence. No answer is
inferred from options.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy.orm import Session

from src.core.database import QuestionOccurrence, SourceDocument, SourcePage
from src.core.logging import get_logger

log = get_logger("pipeline.detect")

MARKER = re.compile(r"(?:^|\n)\s*(?:Q\s?)?(\d{1,3})\s*[.)\-:]\s+", re.IGNORECASE)

OPTION_PATTERNS = [
    re.compile(r"\b([A-Ea-e])\s*\.\s+(.+?)(?=\n\s*[A-Ea-e]\s*\.|\n\s*[A-Ea-e]\s*\)|$\n?)",
              re.IGNORECASE | re.DOTALL),
    re.compile(r"\b([A-Ea-e])\s*\)\s+(.+?)(?=\n\s*[A-Ea-e]\s*\)|\n\s*[A-Ea-e]\s*\)|$)",
              re.IGNORECASE | re.DOTALL),
    re.compile(r"\(([A-Ea-e])\)\s+(.+?)(?=\n\s*\([A-Ea-e]\)|\n\s*\([A-Ea-e]\)|$)",
              re.IGNORECASE | re.DOTALL),
    re.compile(r"\b([A-Ea-e])\s*-\s+(.+?)(?=\n\s*[A-Ea-e]\s*-|$)",
              re.IGNORECASE | re.DOTALL),
]


# Table-layout option rows: the KSOL table layout emits each option
# label on its own extracted-text line.
BARE_OPTION_RUN = re.compile(
    r"(?:^|\n)\s*([A-Ea-e])(?:\s*\n\s*([A-Ea-e])){1,4}\s*\n",
    re.IGNORECASE,
)

def split_candidates(text: str) -> list[tuple[str, str]]:
    """Return [(question_number, body)] in document order."""
    matches = list(MARKER.finditer("\n" + text))
    out: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.end() - 1
        end = matches[i + 1].start() + 1 if i + 1 < len(matches) else len(text) + 1
        body = text[start - 1:end - 1].strip()
        if len(body) >= 8:
            out.append((m.group(1), body))
    return out


def _bare_run_options(text: str) -> list[dict[str, str]]:
    """Table-layout option rows: consecutive bare single-letter lines."""
    options: list[dict[str, str]] = []
    for m in BARE_OPTION_RUN.finditer(text):
        run_letters = "".join(
            ch.upper() for ch in re.findall(r"[A-Ea-e]", m.group(0)))
        # Real option rows start at A and increase by at most one
        # (KSOL answers bubblesets read "A B C D", "A B C", "A B").
        letters = list(run_letters)
        if letters[0] != "A":
            continue
        run = [letters[0]]
        for ch in letters[1:]:
            if ord(ch) - ord(run[-1]) > 1:
                break
            run.append(ch)
        run_letters = "".join(run)
        if len(run_letters) < 2:
            continue
        rest = text[m.end():]
        texts = [ln.strip() for ln in rest.splitlines()
                 if ln.strip() and not re.fullmatch(r"[A-Ea-e]\s*", ln.strip())]
        n = min(len(run_letters), len(texts))
        if n >= 2:
            return [{"letter": run_letters[i], "text": texts[i]} for i in range(n)]
    return []


def _is_ascending_option_run(letters: list[str]) -> bool:
    """True only for a complete A, B, C ... run.

    Real MCQ option lists start at A and increase by one label at a time.
    Noisy OCR/native text can return shuffled (A, C, B), gapped (A, B, D),
    or repeated (A, B, A) label sequences; those are unreliable evidence,
    so they must not become an option set.
    """
    return letters == [chr(ord("A") + i) for i in range(len(letters))]


OPTION_TEXT_CONTENT = re.compile(r"[A-Za-z0-9]")
# Option labels that start a line: "F. text", "F) text", "(F) text".
OPTION_LABEL_AT_START = re.compile(
    r"(?:^|\n)[ \t]*(?:\(([A-Z])\)|([A-Z])\s*[.)])")


def _texts_have_content(options: list[dict[str, str]]) -> bool:
    """Every captured option must carry real text.

    Real corpus: `2008 intake English.pdf` p4 q8 is a write-in question whose
    A/B/C labels are dot-only answer blanks; blank leaders are not option text.
    """
    return all(OPTION_TEXT_CONTENT.search(o["text"]) for o in options)


def _has_label_beyond(text: str, matches: list[re.Match],
                      last_letter: str) -> bool:
    """True when the source keeps listing options past the captured run.

    Patterns only capture A-E, so an A-F or A-J source (real corpus:
    `2008 intake English.pdf` p2 q3, p3 q6/q7) would truncate the run and
    swallow later labels into the last option's text. Such a run is
    incomplete, so it stays unresolved instead of becoming canonical.
    """
    starts = [m.start() for m in matches
              if m.group(1) == m.group(1).upper()]
    if not starts:
        return False
    for m in OPTION_LABEL_AT_START.finditer(text, starts[0]):
        label = m.group(1) or m.group(2)
        if label > last_letter:
            return True
    return False


def extract_options(text: str) -> list[dict[str, str]]:
    """Extract MCQ options from text body.

    Returns list of {letter, text} dicts. Empty list if no options found.
    Does NOT infer the correct answer.
    """
    for pattern in OPTION_PATTERNS:
        # Real 11+ option labels in this corpus are uppercase A-E. Lowercase
        # labels are maths sub-parts ("(a) ... (b) ...", "a. Rectangle"), so
        # filtering to uppercase keeps those questions unresolved instead of
        # promoting them as fake MCQ option sets.
        matches = [m for m in pattern.finditer(text)
                   if m.group(1) == m.group(1).upper()]
        if matches:
            options: list[dict[str, str]] = [{
                "letter": m.group(1).upper(),
                "text": m.group(2).strip(),
            } for m in matches]
            letters = [option["letter"] for option in options]
            if len(options) >= 2 and _is_ascending_option_run(letters):
                # Only structurally supported sets survive: real text in every
                # option and no further option labels beyond the captured run.
                # Otherwise the question stays unresolved for review.
                if (_texts_have_content(options)
                        and not _has_label_beyond(text, matches, letters[-1])):
                    return options
                return []
            # A matched but non-contiguous label run is unreliable. Keep
            # looking at the next separator pattern rather than emitting it.
    return _bare_run_options(text)


def run(session: Session, docs: list[SourceDocument],
        version: str = "0.1.0", batch: str = "") -> dict:
    created = 0
    for doc in docs:
        pages = session.query(SourcePage).filter_by(document_id=doc.id).all()
        for page in pages:
            # Native text first; OCR text is the fallback for scanned pages
            # so that image-only material still yields candidates.
            native = (page.text_content or "").strip()
            ocr = (page.ocr_text or "").strip()
            if not native and not ocr:
                continue
            text = native if len(native) >= len(ocr) else ocr
            for number, body in split_candidates(text):
                exists = session.query(QuestionOccurrence).filter_by(
                    document_id=doc.id, page_id=page.id,
                    question_number=number).first()
                if exists:
                    continue
                options = extract_options(body)
                session.add(QuestionOccurrence(
                    id=str(uuid.uuid4()), document_id=doc.id, page_id=page.id,
                    question_number=number, extraction_run=batch,
                    extraction_version=version, extraction_confidence=0.5,
                    options_json=options if options else None))
                created += 1
    session.commit()
    log.info("detect: %d candidates", created)
    return {"candidates": created}
