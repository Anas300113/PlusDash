"""Representative extraction spike CLI."""
from __future__ import annotations

import argparse
from pathlib import Path

from src.core.config import Settings
from src.core.database import get_engine, get_session_factory, init_db
from src.pipeline.pipeline import run_pipeline


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the representative extraction spike")
    ap.add_argument("--source-root", required=True)
    ap.add_argument("--repo-name", default="spike")
    ap.add_argument("--batch", default="spike-001")
    ap.add_argument("--db", default="sqlite:///./elevenplus.db")
    ap.add_argument("--resume-from", default=None)
    ap.add_argument("--commit-sha", default="")
    args = ap.parse_args()

    engine = get_engine(args.db)
    init_db(engine)
    session = get_session_factory(engine)()
    run = run_pipeline(session, Path(args.source_root), args.repo_name,
                       args.batch, resume_from=args.resume_from,
                       commit_sha=args.commit_sha,
                       assets_dir="data/assets")
    print(f"run={run.id} status={run.status} checkpoint={run.checkpoint}")
    print(f"stats={run.stats_json}")


if __name__ == "__main__":
    main()
