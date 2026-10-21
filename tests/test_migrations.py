from pathlib import Path

import pytest

from core.errors import MigrationError
from core.migrations import MIGRATIONS_DIR, discover


def test_repo_migrations_are_well_formed() -> None:
    files = discover()
    assert files, "expected at least one migration"
    assert [p.name for p in files] == sorted(p.name for p in files)


def test_bad_name_rejected(tmp_path: Path) -> None:
    (tmp_path / "init.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationError, match="001_name.sql"):
        discover(tmp_path)


def test_duplicate_version_rejected(tmp_path: Path) -> None:
    (tmp_path / "001_a.sql").write_text("SELECT 1;")
    (tmp_path / "001_b.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationError, match="duplicate"):
        discover(tmp_path)


def test_migrations_contain_no_destructive_statements() -> None:
    # Migrations only ever add; drops and truncates need a deliberate review.
    for path in MIGRATIONS_DIR.glob("*.sql"):
        text = path.read_text(encoding="utf-8").upper()
        for keyword in ("DROP ", "TRUNCATE ", "DELETE "):
            assert keyword not in text, f"{path.name} contains {keyword.strip()}"
