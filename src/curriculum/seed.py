"""Curriculum seed data: one lesson + strategy + worked example +
common mistake per flagship topic (maths-fractions, eng-grammar,
vr-synonyms, nvr-rotations). Stored independently of runtime content."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from src.core.database import (
    CurriculumCommonMistake, CurriculumLesson, CurriculumStrategy,
    CurriculumWorkedExample,
)

SEED = [
    ("maths-fractions", "Fractions: Simplifying",
     "# Simplifying fractions\n\nDivide numerator and denominator by their HCF.",
     "mcq", "Fractions: find the HCF first",
     "Always simplify before comparing answers.",
     "Example: 12/18", "HCF of 12 and 18 is 6, so 12/18 = 2/3.",
     "Adding numerators with different denominators",
     "Find a common denominator first: 3/4 + 1/3 = 9/12 + 4/12 = 13/12."),
    ("eng-grammar", "Grammar: Sentence types",
     "# Sentences\n\nSimple, compound (FANBOYS), complex (subordinate clause).",
     "mcq", "Grammar: spot the conjunction",
     "Look for FANBOYS joining two independent clauses.",
     "Example: compound", "The sun shone, but we wore coats: two clauses joined by but.",
     "Calling any long sentence complex",
     "Complex needs a subordinate clause, not just length."),
    ("vr-synonyms", "Synonyms: closest in meaning",
     "# Synonyms\n\nTest each pair; eliminate pairs with unrelated words.",
     "mcq", "Synonyms: eliminate first",
     "Cross out options where either word clearly mismatches.",
     "Example: rapid/swift", "Both mean moving quickly.",
     "Picking related-but-not-synonymous pairs",
     "Gentle/kind works; gentle/swift does not."),
    ("nvr-rotations", "Rotations: 90-degree steps",
     "# Rotations\n\nTrack one vertex through each 90-degree turn.",
     "image_choice", "Rotations: follow one corner",
     "Mark a single distinctive corner and follow it step by step.",
     "Example: triangle quarter-turns", "Up, right, down, left, then up again.",
     "Mirroring instead of rotating",
     "A rotation keeps chirality; a mirror flips it."),
]


def seed_curriculum(session: Session) -> int:
    n = 0
    for (topic, lt, lc, st, stt, sc, wet, wec, mmt, mme) in SEED:
        if not session.query(CurriculumLesson).filter_by(
                topic_id=topic, title=lt).first():
            session.add(CurriculumLesson(
                id=str(uuid.uuid4()), topic_id=topic, title=lt,
                content_markdown=lc))
            session.add(CurriculumStrategy(
                id=str(uuid.uuid4()), topic_id=topic, question_type=st,
                title=stt, content_markdown=sc))
            session.add(CurriculumWorkedExample(
                id=str(uuid.uuid4()), topic_id=topic, title=wet,
                content_markdown=wec))
            session.add(CurriculumCommonMistake(
                id=str(uuid.uuid4()), topic_id=topic, mistake_text=mmt,
                explanation_markdown=mme))
            n += 4
    session.commit()
    return n
