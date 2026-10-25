"""Seed taxonomy + exam boards into the DB (idempotent)."""
from __future__ import annotations

import argparse
from pathlib import Path

from src.core.config import load_exams, load_taxonomy
from src.core.database import (
    AssessmentExamBoard, CanonicalQuestionType, CanonicalSkill,
    CanonicalSubject, CanonicalTopic, get_engine, get_session_factory,
    init_db,
)


def seed(db_url: str, taxonomy_path: str, exams_path: str) -> dict:
    engine = get_engine(db_url)
    init_db(engine)
    session = get_session_factory(engine)()
    tax = load_taxonomy(taxonomy_path)
    exams = load_exams(exams_path)
    counts = {"subjects": 0, "topics": 0, "skills": 0, "types": 0, "boards": 0}
    for s in tax.get("subjects", []):
        if not session.query(CanonicalSubject).filter_by(id=s["id"]).first():
            session.add(CanonicalSubject(id=s["id"], name=s["name"],
                                         display_order=s.get("display_order", 0)))
            counts["subjects"] += 1
        for t in s.get("topics", []):
            if not session.query(CanonicalTopic).filter_by(id=t["id"]).first():
                session.add(CanonicalTopic(
                    id=t["id"], subject_id=s["id"], name=t["name"],
                    description=t.get("description", ""),
                    display_order=t.get("display_order", 0)))
                counts["topics"] += 1
            for sk in t.get("skills", []):
                if not session.query(CanonicalSkill).filter_by(id=sk["id"]).first():
                    session.add(CanonicalSkill(id=sk["id"], topic_id=t["id"],
                                               name=sk["name"]))
                    counts["skills"] += 1
    for qt in tax.get("question_types", []):
        if not session.query(CanonicalQuestionType).filter_by(id=qt["id"]).first():
            session.add(CanonicalQuestionType(
                id=qt["id"], name=qt["name"],
                description=qt.get("description", ""),
                requires_options=bool(qt.get("requires_options", False))))
            counts["types"] += 1
    for b in exams.get("exam_boards", []):
        if not session.query(AssessmentExamBoard).filter_by(id=b["id"]).first():
            session.add(AssessmentExamBoard(
                id=b["id"], name=b["name"],
                description=b.get("description", ""),
                regions_json=[r.get("id") for r in exams.get("regions", [])]))
            counts["boards"] += 1
    session.commit()
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="sqlite:///./elevenplus.db")
    ap.add_argument("--taxonomy", default="config/taxonomy.yaml")
    ap.add_argument("--exams", default="config/exams.yaml")
    args = ap.parse_args()
    print(seed(args.db, args.taxonomy, args.exams))


if __name__ == "__main__":
    main()
