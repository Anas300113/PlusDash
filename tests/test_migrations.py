"""Schema migration tests: the additive column migrator.

Guarantees:
  * a database created before the learning layer still opens and gains the
    new columns (no wipe, no data loss);
  * running twice is a no-op;
  * a fresh database needs no migration at all;
  * applied migrations are recorded for auditability.
"""
from __future__ import annotations

import sqlite3

from sqlalchemy import inspect

from src.core.database import (
    Base, get_engine, get_session_factory,
    LearningReviewItem, LearningSkillMastery, LearningStudySession,
)
from src.core.migrations import (
    SCHEMA_VERSION, applied_migrations, ensure_schema,
    reconcile_fabricated_page_ids,
)

# Shape of learning_study_sessions before the learning layer existed.
LEGACY_SESSION_SQL = """
CREATE TABLE learning_study_sessions (
    id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    session_type TEXT,
    started_at DATETIME,
    ended_at DATETIME
)
"""

NEW_SESSION_COLUMNS = {"state", "planned_duration_seconds",
                       "actual_duration_seconds", "goals_json",
                       "recommended_activities_json", "question_order_json",
                       "current_index", "skipped_ids_json", "accuracy"}


def _legacy_engine(db_file):
    con = sqlite3.connect(db_file)
    con.execute(LEGACY_SESSION_SQL)
    con.commit()
    con.close()
    return get_engine(f"sqlite:///{db_file}")


def test_legacy_database_gains_new_columns(tmp_path):
    engine = _legacy_engine(str(tmp_path / "legacy.db"))
    applied = ensure_schema(engine)
    cols = {c["name"] for c in
            inspect(engine).get_columns("learning_study_sessions")}
    assert NEW_SESSION_COLUMNS <= cols
    assert any(m.startswith(SCHEMA_VERSION) for m in applied)
    assert all(
        any(m.endswith(f"learning_study_sessions.{c}") for m in applied)
        for c in sorted(NEW_SESSION_COLUMNS))


def test_ensure_schema_is_idempotent(tmp_path):
    engine = _legacy_engine(str(tmp_path / "idem.db"))
    first = ensure_schema(engine)
    second = ensure_schema(engine)
    assert second == []
    assert len(first) > 0
    assert ensure_schema(engine) == []


def test_migrations_are_recorded_for_audit(tmp_path):
    engine = _legacy_engine(str(tmp_path / "audit.db"))
    ensure_schema(engine)
    recorded = applied_migrations(engine)
    assert any("learning_study_sessions.accuracy" in m for m in recorded)
    assert all(m.startswith(SCHEMA_VERSION) for m in recorded)


def test_fresh_database_needs_no_column_migration(tmp_path):
    """A fresh DB needs no ALTER COLUMN migrations (all columns exist from
    create_all). New additive tables are still recorded for audit."""
    engine = get_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    applied = ensure_schema(engine)
    # New tables are recorded; no column ALTER migrations.
    assert all("question_region_board" in m or "corpus_snapshot" in m
               for m in applied)
    assert ensure_schema(engine) == []


def test_new_learning_tables_exist_after_migration(tmp_path):
    engine = _legacy_engine(str(tmp_path / "tables.db"))
    ensure_schema(engine)
    insp = inspect(engine)
    for table in ("learning_review_items", "learning_skill_mastery",
                  "schema_migrations"):
        assert insp.has_table(table), table
    review_cols = {c["name"] for c in insp.get_columns("learning_review_items")}
    assert {"source_type", "source_id", "state", "due_at", "interval_days",
            "consecutive_correct", "review_history_json"} <= review_cols


def test_legacy_rows_survive_the_migration(tmp_path):
    """Existing sessions must keep their identity and student link."""
    db_file = str(tmp_path / "rows.db")
    con = sqlite3.connect(db_file)
    con.execute(LEGACY_SESSION_SQL)
    con.execute("INSERT INTO learning_study_sessions VALUES "
                "('sess-1', 'student-1', 'practice', NULL, NULL)")
    con.commit()
    con.close()
    engine = get_engine(f"sqlite:///{db_file}")
    ensure_schema(engine)
    S = get_session_factory(engine)
    s = S()
    row = s.query(LearningStudySession).filter_by(id="sess-1").one()
    assert row.student_id == "student-1"
    # New columns fall back to their server defaults for old rows.
    assert row.state == "started"
    assert row.current_index == 0
    assert row.accuracy == 0.0
    assert row.question_order == []
    s.close()


def test_review_item_unique_constraint_prevents_duplicates(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'unique.db'}")
    ensure_schema(engine)
    S = get_session_factory(engine)
    s = S()
    s.add(LearningReviewItem(id="ri-1", student_id="stu-1",
                             source_type="question", source_id="q-1"))
    s.commit()
    s.add(LearningReviewItem(id="ri-2", student_id="stu-1",
                             source_type="question", source_id="q-1"))
    try:
        s.commit()
    except Exception:
        s.rollback()
    else:
        raise AssertionError("duplicate review item should be rejected")
    assert s.query(LearningReviewItem).count() == 1
    s.close()


def test_base_metadata_still_creates_everything(tmp_path):
    """The create_all path used by tests stays valid alongside ensure_schema."""
    engine = get_engine(f"sqlite:///{tmp_path / 'all.db'}")
    Base.metadata.create_all(bind=engine)
    applied = ensure_schema(engine)
    # New tables already created by create_all; only their migration
    # records are applied (idempotent on re-run).
    assert all("question_region_board" in m or "corpus_snapshot" in m
               for m in applied)
    assert ensure_schema(engine) == []


def test_mysql_schema_and_indexes_compile_with_bounded_strings():
    """Every ORM table and index must emit valid MySQL DDL offline."""
    from sqlalchemy import String as SQLString, UniqueConstraint
    from sqlalchemy.dialects.mysql import dialect
    from sqlalchemy.schema import CreateIndex, CreateTable

    mysql = dialect()
    for table in Base.metadata.sorted_tables:
        str(CreateTable(table).compile(dialect=mysql))
        for index in table.indexes:
            str(CreateIndex(index).compile(dialect=mysql))
        for constraint in table.constraints:
            if isinstance(constraint, UniqueConstraint):
                indexed_string_bytes = sum(
                    (column.type.length or 0) * 4
                    for column in constraint.columns
                    if isinstance(column.type, SQLString)
                )
                assert indexed_string_bytes <= 3072, (
                    table.name, constraint.name, indexed_string_bytes)


# ---- Gate 1: fabricated page-provenance reconciliation ---------------------

def _occurrence_engine(db_file):
    """A DB with the occurrences table + a real source_page row, no other
    learning tables needed."""
    engine = get_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    return engine


def test_fabricated_page_ids_are_cleared_and_real_ones_kept(tmp_path):
    """Legacy reference-import rows stored the document id in page_id (a
    fabricated page pointer). The reconciliation must clear exactly those to
    '' while preserving genuine page-backed occurrences and file+record
    provenance (document_id + question_number untouched)."""
    import uuid as _uuid
    from src.core.database import (
        QuestionOccurrence, SourceDocument, SourcePage,
    )
    db_file = str(tmp_path / "fab.db")
    engine = _occurrence_engine(db_file)
    S = get_session_factory(engine)
    s = S()
    doc = SourceDocument(
        id=str(_uuid.uuid4()), repo_name="r", repo_url="", source_path="b.json",
        file_sha256="0" * 64, file_size=1, file_type="json")
    s.add(doc)
    s.flush()
    page = SourcePage(
        id=str(_uuid.uuid4()), document_id=doc.id, page_number=1,
        text_content="real page")
    s.add(page)
    s.flush()
    # Fabricated occurrence: page_id = document_id (no such source_page row).
    s.add(QuestionOccurrence(
        id=str(_uuid.uuid4()), canonical_question_id="q-fab",
        document_id=doc.id, page_id=doc.id, question_number="rec-1"))
    # Genuine occurrence: page_id = a real source_page id.
    s.add(QuestionOccurrence(
        id=str(_uuid.uuid4()), canonical_question_id="q-real",
        document_id=doc.id, page_id=page.id, question_number="rec-2"))
    s.commit()

    schema_applied = ensure_schema(engine)
    assert not any("page_provenance_reconciliation" in m
                   for m in schema_applied)
    applied = reconcile_fabricated_page_ids(engine)
    assert any("page_provenance_reconciliation" in m for m in applied)

    s.expire_all()
    fab = s.query(QuestionOccurrence).filter_by(
        canonical_question_id="q-fab").one()
    real = s.query(QuestionOccurrence).filter_by(
        canonical_question_id="q-real").one()
    # Fabricated pointer cleared to the file-level sentinel...
    assert fab.page_id == ""
    # ...but its honest file+record provenance is intact.
    assert fab.document_id == doc.id and fab.question_number == "rec-1"
    # The genuine page-backed occurrence is untouched.
    assert real.page_id == page.id
    # Idempotent: a second run clears nothing and records nothing new.
    assert ensure_schema(engine) == []
    assert reconcile_fabricated_page_ids(engine) == []
    s.close()


def test_reconciliation_is_noop_when_no_fabricated_rows(tmp_path):
    """A clean DB (no fabricated page ids) must not record the reconciliation
    migration, so ensure_schema still reports no changes."""
    db_file = str(tmp_path / "clean.db")
    engine = _occurrence_engine(db_file)
    applied = ensure_schema(engine)
    assert not any("page_provenance_reconciliation" in m for m in applied)
    assert reconcile_fabricated_page_ids(engine) == []
    assert ensure_schema(engine) == []
