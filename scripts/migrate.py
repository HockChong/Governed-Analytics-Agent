"""Apply pending Postgres migrations. Run via `make migrate`."""

import sys

import psycopg

from core.config import Settings
from core.migrations import apply_migrations


def main() -> int:
    """Apply pending migrations and print which ones ran."""
    settings = Settings()
    with psycopg.connect(settings.postgres_conninfo(), autocommit=True) as conn:
        names = apply_migrations(conn)
    print(f"applied {len(names)} migration(s): {', '.join(names) or 'none pending'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
