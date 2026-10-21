from pathlib import Path

import pytest

from core.errors import MigrationError
from core.migrations import MIGRATIONS_DIR, discover


def test_discover_returns_repo_migrations_in_version_order() -> None:
    files = discover()
    assert files, "expected at least one migration"
    assert [path.name for path in files] == sorted(path.name for path in files)


def test_discover_rejects_badly_named_file(tmp_path: Path) -> None:
    (tmp_path / "init.sql").write_text("select 1;")
    with pytest.raises(MigrationError, match="001_name.sql"):
        discover(tmp_path)


def test_discover_rejects_duplicate_version(tmp_path: Path) -> None:
    (tmp_path / "001_a.sql").write_text("select 1;")
    (tmp_path / "001_b.sql").write_text("select 1;")
    with pytest.raises(MigrationError, match="duplicate"):
        discover(tmp_path)


def test_repo_migrations_contain_no_destructive_statements() -> None:
    # Migrations only ever add; drops and truncates need a deliberate review.
    for path in MIGRATIONS_DIR.glob("*.sql"):
        text = path.read_text(encoding="utf-8").upper()
        for keyword in ("DROP ", "TRUNCATE ", "DELETE "):
            assert keyword not in text, f"{path.name} contains {keyword.strip()}"
