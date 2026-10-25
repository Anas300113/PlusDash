"""Explicit additive FastAPI schema migration entry point.

Run ``python -m src.core.migrate`` after reviewing the target DATABASE_URL.
It creates missing schema and adds columns/indexes only; it does not seed
questions, delete rows, or rewrite existing content. The separate
``--reconcile-page-provenance`` option performs an explicit content-data
correction and should be used only after operator review and approval.
"""
from __future__ import annotations

import argparse
import os

from src.core.database import get_engine
from src.core.migrations import ensure_schema, reconcile_fabricated_page_ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Plus11 schema migration")
    parser.add_argument(
        "--reconcile-page-provenance",
        action="store_true",
        help=(
            "also rewrite only known fabricated source-page pointers; "
            "this changes existing content data and is not part of schema migration"
        ),
    )
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL") or os.environ.get("PLUS_DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL (or PLUS_DATABASE_URL) before migrating.")
    engine = get_engine(url)
    try:
        applied = ensure_schema(engine)
        print(f"Schema is ready. Applied {len(applied)} additive migration action(s).")
        for migration_id in applied:
            print(f"  + {migration_id}")
        if args.reconcile_page_provenance:
            reconciled = reconcile_fabricated_page_ids(engine)
            print(f"Explicitly applied {len(reconciled)} provenance correction(s).")
            for migration_id in reconciled:
                print(f"  + {migration_id}")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
