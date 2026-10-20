"""Apply plain-SQL migrations in migrations/ in filename order, each at most once.

Usage: python -m core.migrations   (PYTHONPATH=src; `make migrate` sets it)
"""

import re
from pathlib import Path

import psycopg

from core.config import Settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
_NAME = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


def discover(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    """Return migration files sorted by version; reject badly named or duplicate versions."""
    files = sorted(directory.glob("*.sql"))
    versions: set[str] = set()
    for path in files:
        match = _NAME.match(path.name)
        if not match:
            raise ValueError(f"migration name must look like 001_name.sql: {path.name}")
        if match.group(1) in versions:
            raise ValueError(f"duplicate migration version {match.group(1)}")
        versions.add(match.group(1))
    return files


def apply_migrations(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations, each in its own transaction. Returns the names applied."""
    with conn.transaction():
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migration ("
            " name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
    applied = {row[0] for row in conn.execute("SELECT name FROM schema_migration")}
    newly_applied: list[str] = []
    for path in discover(directory):
        if path.name in applied:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8").encode())
            conn.execute("INSERT INTO schema_migration (name) VALUES (%s)", (path.name,))
        newly_applied.append(path.name)
    return newly_applied


def main() -> None:
    settings = Settings()
    with psycopg.connect(settings.postgres_conninfo(), autocommit=True) as conn:
        names = apply_migrations(conn)
    print(f"applied {len(names)} migration(s): {', '.join(names) or 'none pending'}")


if __name__ == "__main__":
    main()
