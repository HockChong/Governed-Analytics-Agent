from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from google.cloud import bigquery

from core.errors import ProfileError
from ingestion.profile import (
    ColumnSpec,
    check_schema_matches,
    load_column_specs,
    profile_query,
    profile_snapshot,
    render_markdown,
    top_values_candidates,
)

SOURCES_YML = Path(__file__).resolve().parents[1] / "dbt" / "models" / "sources.yml"
SNAPSHOT_AT = datetime(2026, 10, 21, 3, 16, tzinfo=UTC)
TABLE_ID = "test-project.test_snapshot.users"

USERS = [
    ColumnSpec(name="id", data_type="int64", pii=False),
    ColumnSpec(name="email", data_type="string", pii=True),
    ColumnSpec(name="country", data_type="string", pii=False),
    ColumnSpec(name="created_at", data_type="timestamp", pii=False),
    ColumnSpec(name="user_geom", data_type="geography", pii=True),
]


def test_load_column_specs_reads_pii_from_config_meta() -> None:
    specs = {column.name: column for column in load_column_specs(SOURCES_YML)["users"]}
    assert specs["email"].pii is True
    assert specs["country"].pii is False
    assert specs["created_at"].data_type == "timestamp"


def test_profile_query_never_selects_values_of_pii_columns() -> None:
    sql = profile_query(TABLE_ID, USERS)
    assert "countif(`email` is null)" in sql
    assert "min(`email`)" not in sql
    assert "max(`email`)" not in sql


def test_profile_query_selects_min_and_max_of_non_pii_columns() -> None:
    sql = profile_query(TABLE_ID, USERS)
    assert "min(`country`)" in sql
    assert "max(`created_at`)" in sql


def test_profile_query_counts_future_rows_for_timestamps_only() -> None:
    sql = profile_query(TABLE_ID, USERS)
    assert "countif(`created_at` > @snapshot_at)" in sql
    assert "countif(`id` > @snapshot_at)" not in sql


def test_profile_query_skips_distinct_and_range_for_geography() -> None:
    sql = profile_query(TABLE_ID, USERS)
    assert "count(distinct `user_geom`)" not in sql
    assert "countif(`user_geom` is null)" in sql


def test_profile_query_rejects_unsafe_identifier() -> None:
    bad = [ColumnSpec(name="id`; drop table x; --", data_type="int64", pii=False)]
    with pytest.raises(ProfileError, match="identifier"):
        profile_query(TABLE_ID, bad)


def test_top_values_candidates_exclude_pii_even_when_low_cardinality() -> None:
    distinct_counts = {"email": 3, "country": 15}
    assert top_values_candidates(USERS, distinct_counts) == ["country"]


def test_top_values_candidates_skip_high_cardinality_and_non_strings() -> None:
    distinct_counts = {"id": 5, "email": 3, "country": 500}
    assert top_values_candidates(USERS, distinct_counts) == []


def test_check_schema_rejects_undeclared_column() -> None:
    actual = [("id", "INTEGER"), ("email", "STRING"), ("nickname", "STRING")]
    with pytest.raises(ProfileError, match="nickname"):
        check_schema_matches("users", USERS[:2], actual)


def test_check_schema_rejects_type_mismatch() -> None:
    actual = [("id", "STRING"), ("email", "STRING")]
    with pytest.raises(ProfileError, match="id"):
        check_schema_matches("users", USERS[:2], actual)


def test_check_schema_accepts_legacy_bigquery_type_names() -> None:
    actual = [
        ("id", "INTEGER"),
        ("email", "STRING"),
        ("country", "STRING"),
        ("created_at", "TIMESTAMP"),
        ("user_geom", "GEOGRAPHY"),
    ]
    check_schema_matches("users", USERS, actual)


class _QueryJob:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def result(self) -> list[dict[str, object]]:
        return self._rows


class FakeClient:
    """Returns canned rows; records every SQL string it is asked to run."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def get_table(self, table_id: str) -> SimpleNamespace:
        types = {"int64": "INTEGER", "string": "STRING", "timestamp": "TIMESTAMP"}
        types["geography"] = "GEOGRAPHY"
        schema = [SimpleNamespace(name=c.name, field_type=types[c.data_type]) for c in USERS]
        return SimpleNamespace(schema=schema)

    def query(self, sql: str, job_config: bigquery.QueryJobConfig) -> _QueryJob:
        self.queries.append(sql)
        if "group by" in sql:
            return _QueryJob([{"value": "Brasil", "row_count": 9}, {"value": None, "row_count": 1}])
        return _QueryJob(
            [
                {
                    "row_count": 10,
                    "c0_nulls": 0,
                    "c0_distinct": 10,
                    "c0_min": "1",
                    "c0_max": "10",
                    "c1_nulls": 0,
                    "c1_distinct": 10,
                    "c2_nulls": 0,
                    "c2_distinct": 2,
                    "c2_min": "Brasil",
                    "c2_max": "China",
                    "c3_nulls": 0,
                    "c3_distinct": 10,
                    "c3_min": "2020-01-01 00:00:00+00",
                    "c3_max": "2026-12-01 00:00:00+00",
                    "c3_future": 1,
                    "c4_nulls": 0,
                }
            ]
        )


def _profile(client: FakeClient) -> list[object]:
    return list(
        profile_snapshot(
            cast(bigquery.Client, client),
            "test-project.test_snapshot",
            {"users": USERS},
            snapshot_at=SNAPSHOT_AT,
            max_bytes_billed=1_000_000_000,
        )
    )


def test_profile_snapshot_queries_top_values_for_non_pii_only() -> None:
    client = FakeClient()
    _profile(client)
    top_value_queries = [sql for sql in client.queries if "group by" in sql]
    assert len(top_value_queries) == 1
    assert "`country`" in top_value_queries[0]
    assert all("`email`" not in sql for sql in top_value_queries)


def test_render_markdown_shows_no_values_for_pii_columns() -> None:
    profiles = profile_snapshot(
        cast(bigquery.Client, FakeClient()),
        "test-project.test_snapshot",
        {"users": USERS},
        snapshot_at=SNAPSHOT_AT,
        max_bytes_billed=1_000_000_000,
    )
    text = render_markdown(profiles, snapshot_id="snap-1", snapshot_at=SNAPSHOT_AT)

    email_line = next(line for line in text.splitlines() if line.startswith("| email "))
    assert "pii" in email_line
    assert "Brasil" in text
    assert "1 future" in text
    assert "snap-1" in text
