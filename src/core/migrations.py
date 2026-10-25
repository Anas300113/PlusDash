"""Explicit additive schema migration for the 11+ platform.

Only missing tables, columns, and indexes are added. Existing rows are kept;
no table is dropped and no question data is seeded. Run this module explicitly
with ``python -m src.core.migrate`` before the combined service is published.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn, CreateIndex

from src.core.database import Base, utcnow

SCHEMA_VERSION = "0.2.0-learning"
_MIGRATION_TABLE = "schema_migrations"


def _ensure_migration_table(conn) -> None:
    if conn.dialect.name == "mysql":
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS `schema_migrations` ("
            "`id` VARCHAR(255) NOT NULL PRIMARY KEY, "
            "`applied_at` VARCHAR(40) NOT NULL) "
            "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
    else:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")


def _insert_migration(conn, migration_id: str) -> None:
    if conn.dialect.name == "mysql":
        statement = text(
            "INSERT IGNORE INTO `schema_migrations` (`id`, `applied_at`) "
            "VALUES (:migration_id, :applied_at)")
    else:
        statement = text(
            "INSERT OR IGNORE INTO schema_migrations (id, applied_at) "
            "VALUES (:migration_id, :applied_at)")
    conn.execute(statement, {
        "migration_id": migration_id,
        "applied_at": utcnow().isoformat(),
    })


def applied_migrations(engine) -> set[str]:
    """Ids of migrations already applied (empty if the table is absent)."""
    if not inspect(engine).has_table(_MIGRATION_TABLE):
        return set()
    with engine.connect() as conn:
        return {row[0] for row in conn.exec_driver_sql(
            "SELECT id FROM schema_migrations")}


def _pending_columns(engine) -> list[tuple[str, str]]:
    """Return [(table, column)] present in metadata but absent in the DB."""
    insp = inspect(engine)
    pending: list[tuple[str, str]] = []
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {column["name"] for column in insp.get_columns(table.name)}
        for column in table.columns:
            if column.name not in existing:
                pending.append((table.name, column.name))
    return pending


def ensure_schema(engine) -> list[str]:
    """Add missing schema elements and return applied migration identifiers.

    This operation is explicit and idempotent. It is additive: the existing
    application data and tables are retained.
    """
    Base.metadata.create_all(bind=engine)
    applied: list[str] = []
    pending = _pending_columns(engine)
    if pending:
        tables = {table.name: table for table in Base.metadata.sorted_tables}
        touched = {table for table, _ in pending}
        quote = engine.dialect.identifier_preparer.quote
        with engine.begin() as conn:
            _ensure_migration_table(conn)
            for table_name, column_name in pending:
                column = tables[table_name].columns[column_name]
                ddl = str(CreateColumn(column).compile(dialect=engine.dialect))
                conn.exec_driver_sql(
                    f"ALTER TABLE {quote(table_name)} ADD COLUMN {ddl}")
                migration_id = f"{SCHEMA_VERSION}:{table_name}.{column_name}"
                _insert_migration(conn, migration_id)
                applied.append(migration_id)
        _create_missing_indexes(engine, touched, applied)
    else:
        _ensure_migration_table_exists(engine)
    applied.extend(_record_new_tables(engine))
    return applied


def _record_new_tables(engine) -> list[str]:
    """Audit the two additive tables introduced after the original schema."""
    insp = inspect(engine)
    if not insp.has_table(_MIGRATION_TABLE):
        return []
    applied: list[str] = []
    for table_name, migration_id in (
        ("question_region_board", _QUESTION_REGION_BOARD_ID),
        ("corpus_snapshots", _CORPUS_SNAPSHOT_ID),
    ):
        if not insp.has_table(table_name):
            continue
        with engine.begin() as conn:
            already = {row[0] for row in conn.exec_driver_sql(
                "SELECT id FROM schema_migrations").fetchall()}
            if migration_id in already:
                continue
            _insert_migration(conn, migration_id)
            applied.append(migration_id)
    return applied


_DATA_PAGE_PROVENANCE_ID = f"{SCHEMA_VERSION}:data:page_provenance_reconciliation"
_QUESTION_REGION_BOARD_ID = f"{SCHEMA_VERSION}:create_table:question_region_board"
_CORPUS_SNAPSHOT_ID = f"{SCHEMA_VERSION}:create_table:corpus_snapshot"


def reconcile_fabricated_page_ids(engine) -> list[str]:
    """Explicitly clear known fabricated page pointers without deleting rows.

    This changes existing content data and is intentionally not called by
    ``ensure_schema``. Invoke only after reviewing and approving the correction.
    """
    insp = inspect(engine)
    if not insp.has_table("question_occurrences") or not insp.has_table("source_pages"):
        return []
    with engine.begin() as conn:
        _ensure_migration_table(conn)
        already = {row[0] for row in conn.exec_driver_sql(
            "SELECT id FROM schema_migrations").fetchall()}
        if _DATA_PAGE_PROVENANCE_ID in already:
            return []
        result = conn.exec_driver_sql(
            "UPDATE question_occurrences SET page_id = '' "
            "WHERE page_id <> '' AND page_id = document_id "
            "AND page_id NOT IN (SELECT id FROM source_pages)")
        if not result.rowcount:
            return []
        _insert_migration(conn, _DATA_PAGE_PROVENANCE_ID)
    return [_DATA_PAGE_PROVENANCE_ID]


def _create_missing_indexes(engine, table_names: set[str],
                            applied: list[str]) -> None:
    """Create indexes associated with newly-added indexed columns."""
    insp = inspect(engine)
    for table_name in sorted(table_names):
        table = Base.metadata.tables[table_name]
        existing = {index["name"] for index in insp.get_indexes(table_name)}
        for index in table.indexes:
            if index.name in existing:
                continue
            with engine.begin() as conn:
                conn.exec_driver_sql(str(CreateIndex(index).compile(
                    dialect=engine.dialect)))
            applied.append(
                f"{SCHEMA_VERSION}:{table_name}.index:{index.name}")


def _ensure_migration_table_exists(engine) -> None:
    with engine.begin() as conn:
        _ensure_migration_table(conn)
