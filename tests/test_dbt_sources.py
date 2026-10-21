from pathlib import Path
from typing import Any

import yaml

SOURCES_YML = Path(__file__).resolve().parents[1] / "dbt" / "models" / "sources.yml"

# Rule (progress.md): postal codes, street addresses, names, emails, IPs and
# point locations are PII; city, state and country are not (RLS uses country).
EXPECTED_PII = {
    ("users", "first_name"),
    ("users", "last_name"),
    ("users", "email"),
    ("users", "street_address"),
    ("users", "postal_code"),
    ("users", "latitude"),
    ("users", "longitude"),
    ("users", "user_geom"),
    ("events", "ip_address"),
    ("events", "postal_code"),
}


# Any: yaml.safe_load returns untyped nested data; the tests only index known keys.
def _source_tables() -> list[dict[str, Any]]:
    sources = yaml.safe_load(SOURCES_YML.read_text(encoding="utf-8"))["sources"]
    tables: list[dict[str, Any]] = sources[0]["tables"]
    return tables


def _columns() -> list[tuple[str, dict[str, Any]]]:
    return [(table["name"], column) for table in _source_tables() for column in table["columns"]]


def test_every_source_table_declares_columns() -> None:
    for table in _source_tables():
        assert table.get("columns"), f"{table['name']} declares no columns"


def test_every_source_column_has_data_type() -> None:
    for table_name, column in _columns():
        assert column.get("data_type"), f"{table_name}.{column['name']} has no data_type"


def test_no_column_uses_deprecated_top_level_meta() -> None:
    # dbt 1.10+ ignores-with-warning top-level `meta`; a tag there would look set but drift.
    for table_name, column in _columns():
        assert "meta" not in column, f"{table_name}.{column['name']}: use config.meta"


def test_pii_tags_match_the_pii_rule() -> None:
    tagged = {
        (table_name, column["name"])
        for table_name, column in _columns()
        if column.get("config", {}).get("meta", {}).get("pii") is True
    }
    assert tagged == EXPECTED_PII
