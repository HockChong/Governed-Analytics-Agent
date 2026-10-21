"""Migrations apply cleanly to an empty database and are idempotent.

Runs only when POSTGRES_PASSWORD is set (e.g. via `make test` with .env and
`make up`); otherwise skipped. Uses a throwaway database, dropped afterwards.
"""

import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql

from core.config import Settings
from core.migrations import apply_migrations, discover

pytestmark = pytest.mark.integration


@pytest.fixture
def empty_db(settings: Settings) -> Iterator[psycopg.Connection]:
    if settings.postgres_password is None:
        pytest.skip("POSTGRES_PASSWORD not set")
    name = f"migration_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(settings.postgres_conninfo(), autocommit=True) as admin:
        admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
        try:
            with psycopg.connect(settings.postgres_conninfo(name), autocommit=True) as conn:
                yield conn
        finally:
            admin.execute(sql.SQL("drop database {}").format(sql.Identifier(name)))


def test_apply_migrations_creates_tables_then_is_a_noop(empty_db: psycopg.Connection) -> None:
    applied = apply_migrations(empty_db)
    assert applied == [path.name for path in discover()]
    assert apply_migrations(empty_db) == []

    tables = {
        row[0]
        for row in empty_db.execute(
            "select table_name from information_schema.tables where table_schema = 'public'"
        )
    }
    assert {"audit_log", "eval_run", "schema_migration"} <= tables


def test_audit_log_rejects_unknown_exit_code(empty_db: psycopg.Connection) -> None:
    apply_migrations(empty_db)
    with pytest.raises(psycopg.errors.CheckViolation):
        empty_db.execute(
            "insert into audit_log (request_id, user_id, role, question, exit_code)"
            " values (gen_random_uuid(), 'u', 'r', 'q', 'bogus')"
        )
