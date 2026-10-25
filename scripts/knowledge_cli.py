#!/usr/bin/env python
"""Knowledge-engine CLI: build a retrieval index from ingested pages and
query it with verifiable citations.

Subcommands:
  ingest      Discover a source directory and ingest it into the DB
              (inventory -> page/text/image extract -> OCR -> detect/link/
              classify/dedup/validate). Run this BEFORE index. Idempotent.
  inventory   Dry-run: count documents/pages/chunks that would be indexed
              (reflects DB content only).
  index       Build (or rebuild) the persisted TF-IDF index from DB pages.
              Note: index does NOT discover files; ingest does that first.
  query       Retrieve top-k passages for a query (filename + page + excerpt).
  repair      Verify a persisted index loads and matches DB chunk count.
  report      Print reproducible, read-only content-readiness metrics (JSON).

All operations are deterministic, offline and idempotent. Re-running ``index``
against unchanged DB content produces no duplicate chunks (content-stable ids).

Examples (from repo root, PYTHONPATH=.):
  python scripts/knowledge_cli.py ingest --db elevenplus.db --source "D:/11+ dump"
  python scripts/knowledge_cli.py index --db elevenplus.db --out data/knowledge/index.joblib
  python scripts/knowledge_cli.py query --db elevenplus.db \\
      --index data/knowledge/index.joblib --q "opposite of generous" -k 3
  python scripts/knowledge_cli.py report --db elevenplus.db
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.database import SourcePage, init_db
from src.knowledge.service import build_index, iter_page_chunks
from src.knowledge.retriever import KnowledgeIndex
from src.knowledge.report import content_report
from src.pipeline.ocr import ocr_engine_status
from src.pipeline.pipeline import run_pipeline

DEFAULT_INDEX = "data/knowledge/index.joblib"


def _session(db: str):
    engine = create_engine(f"sqlite:///{db}")
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def cmd_inventory(args) -> int:
    s = _session(args.db)
    try:
        docs = s.query(SourcePage.document_id).distinct().count()
        pages = s.query(SourcePage).count()
        n_chunks = sum(1 for _ in iter_page_chunks(s))
        with_text = s.query(SourcePage).filter(
            SourcePage.text_content != "").count()
        print(f"documents={docs} pages={pages} pages_with_text={with_text} "
              f"chunks={n_chunks} index_out={args.out}")
        return 0
    finally:
        s.close()


def cmd_index(args) -> int:
    s = _session(args.db)
    try:
        idx = build_index(s)
        out = Path(args.out)
        idx.save(out)
        print(f"indexed chunks={idx.size} vocabulary={len(idx.vocabulary)} "
              f"out={out}")
        return 0
    finally:
        s.close()


def cmd_query(args) -> int:
    out = Path(args.index)
    idx = KnowledgeIndex.load(out)
    hits = idx.search(args.q, top_k=args.k)
    if not hits:
        print("NO_EVIDENCE (query shares no terms with the index)")
        return 1
    for i, h in enumerate(hits, 1):
        print(f"[{i}] score={h['score']}  {h['filename']}  p{h['page_number']}")
        print(f"    {h['excerpt']}")
    return 0


def cmd_repair(args) -> int:
    s = _session(args.db)
    try:
        expected = sum(1 for _ in iter_page_chunks(s))
        idx = KnowledgeIndex.load(Path(args.index))
        ok = idx.size == expected
        print(f"index_chunks={idx.size} db_chunks={expected} consistent={ok}")
        return 0 if ok else 2
    finally:
        s.close()


def cmd_ingest(args) -> int:
    """Bridge a source directory into the DB using the existing pipeline.

    The retrieval index only reflects DB content, so ingestion must run first.
    This is the missing link the CLI previously lacked: it discovers files,
    extracts pages/text/images, OCRs scanned pages and runs detect/link/etc.
    Idempotent: re-running against unchanged files creates no duplicate rows.
    """
    engine = create_engine(f"sqlite:///{args.db}")
    init_db(engine)
    s = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                     future=True)()
    try:
        if not args.no_ocr:
            status = ocr_engine_status()
            if not status.get("available"):
                # Environment configuration, not an extraction failure.
                print(f"WARNING: Tesseract unavailable ({status.get('error', '')}). "
                      f"Set PLUS_TESSERACT_CMD to the tesseract.exe path to OCR "
                      f"scanned pages. Continuing; scanned pages stay un-OCRed.")
        run = run_pipeline(
            s, args.source, repo_name=args.repo, batch=args.batch,
            assets_dir=args.assets,
            resume_from=args.resume_from)
        import json
        print(json.dumps({"status": run.status, "stats": run.stats_json,
                          "error": run.error_message}, indent=2))
        return 0 if run.status == "completed" else 1
    finally:
        s.close()


def cmd_report(args) -> int:
    """Print the reproducible, read-only content-readiness report as JSON."""
    s = _session(args.db)
    try:
        import json
        print(json.dumps(content_report(s), indent=2))
        return 0
    finally:
        s.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Knowledge-engine CLI")
    p.add_argument("--db", default="elevenplus.db")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("inventory", help="dry-run chunk inventory")
    pi.add_argument("--out", default=DEFAULT_INDEX)
    pi.set_defaults(func=cmd_inventory)

    px = sub.add_parser("index", help="build/persist the index")
    px.add_argument("--out", default=DEFAULT_INDEX)
    px.set_defaults(func=cmd_index)

    pq = sub.add_parser("query", help="retrieve passages")
    pq.add_argument("--index", default=DEFAULT_INDEX)
    pq.add_argument("--q", required=True)
    pq.add_argument("-k", type=int, default=5)
    pq.set_defaults(func=cmd_query)

    pr = sub.add_parser("repair", help="verify index vs DB consistency")
    pr.add_argument("--index", default=DEFAULT_INDEX)
    pr.set_defaults(func=cmd_repair)

    pg = sub.add_parser("ingest", help="ingest a source directory into the DB "
                                      "(run before index)")
    pg.add_argument("--source", required=True,
                    help="directory of source documents")
    pg.add_argument("--repo", default="corpus")
    pg.add_argument("--batch", default="default")
    pg.add_argument("--assets", default="data/assets")
    pg.add_argument("--resume-from", default=None,
                    help="resume the pipeline from a named step")
    pg.add_argument("--no-ocr", action="store_true",
                    help="skip the Tesseract availability pre-check")
    pg.set_defaults(func=cmd_ingest)

    prp = sub.add_parser("report", help="print content-readiness metrics (JSON)")
    prp.set_defaults(func=cmd_report)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
