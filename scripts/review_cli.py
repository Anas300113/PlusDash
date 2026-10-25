"""Review CLI: list queue, approve, reject."""
from __future__ import annotations

import argparse

from src.core.database import get_engine, get_session_factory, init_db
from src.pipeline.review import review_queue, set_status


def main() -> None:
    ap = argparse.ArgumentParser(description="Review question candidates")
    ap.add_argument("--db", default="sqlite:///./elevenplus.db")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--approve", default=None)
    ap.add_argument("--reject", default=None)
    args = ap.parse_args()

    engine = get_engine(args.db)
    init_db(engine)
    session = get_session_factory(engine)()
    if args.list:
        for q, s in review_queue(session):
            print(f"{q.id} [{s.status}] {q.subject}/{q.topic} :: {q.question_text[:120]}")
    if args.approve:
        set_status(session, args.approve, "approved")
        print(f"approved {args.approve}")
    if args.reject:
        set_status(session, args.reject, "rejected")
        print(f"rejected {args.reject}")


if __name__ == "__main__":
    main()
