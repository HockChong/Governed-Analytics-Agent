"""Apply plain-SQL migrations in migrations/ in filename order, each at most once.

Run via `make migrate` (scripts/migrate.py).
"""

import re
from pathlib import Path

import psycopg

from core.errors import MigrationError

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
_NAME = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


def discover(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    """Return migration files sorted by version; reject badly named or duplicate versions."""
    files = sorted(directory.glob("*.sql"))
    versions: set[str] = set()
    for path in files:
        match = _NAME.match(path.name)
        if not match:
            raise MigrationError(f"migration name must look like 001_name.sql: {path.name}")
        if match.group(1) in versions:
            raise MigrationError(f"duplicate migration version {match.group(1)}")
        versions.add(match.group(1))
    return files


def apply_migrations(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations, each in its own transaction. Returns the names applied."""
    with conn.transaction():
        conn.execute(
            "create table if not exists schema_migration ("
            " name text primary key, applied_at timestamptz not null default now())"
        )
    applied = {row[0] for row in conn.execute("select name from schema_migration")}
    newly_applied: list[str] = []
    for path in discover(directory):
        if path.name in applied:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8").encode())
            conn.execute("insert into schema_migration (name) values (%s)", (path.name,))
        newly_applied.append(path.name)
    return newly_applied
