from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast

import pytest
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

from core.errors import SnapshotError
from ingestion.snapshot import (
    METADATA_SCHEMA,
    METADATA_TABLE,
    SOURCE_DATASET,
    TABLES,
    SnapshotMetadataRow,
    TableSnapshot,
    snapshot,
)

JsonRow = dict[str, object]

DATASET = "test-project.test_snapshot"
MODIFIED = datetime(2026, 10, 21, tzinfo=UTC)
SNAPSHOT_AT = datetime(2026, 10, 21, 9, 30, tzinfo=UTC)
SNAPSHOT_ID = "snapshot-0001"


class _Job:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id

    def result(self) -> None:
        return None


class FakeClient:
    """Just enough of bigquery.Client for snapshot(): tables live in a dict."""

    def __init__(self, existing: frozenset[str] = frozenset()) -> None:
        self.tables: dict[str, SimpleNamespace] = {
            f"{SOURCE_DATASET}.{name}": SimpleNamespace(num_rows=position, modified=MODIFIED)
            for position, name in enumerate(TABLES, start=1)
        }
        for name in existing:
            self.tables[f"{DATASET}.{name}"] = SimpleNamespace(num_rows=0, modified=MODIFIED)
        self.copies: list[tuple[str, str, str]] = []
        self.loads: list[tuple[list[JsonRow], str, str]] = []
        self.mutate_source_during_copy: str | None = None

    def get_table(self, table_id: str) -> SimpleNamespace:
        if table_id not in self.tables:
            raise NotFound(table_id)  # type: ignore[no-untyped-call]
        return self.tables[table_id]

    def copy_table(self, source: str, destination: str, job_config: bigquery.CopyJobConfig) -> _Job:
        self.copies.append((source, destination, str(job_config.write_disposition)))
        self.tables[destination] = SimpleNamespace(num_rows=self.tables[source].num_rows)
        if source.endswith(f".{self.mutate_source_during_copy}"):
            self.tables[source] = SimpleNamespace(
                num_rows=99, modified=MODIFIED + timedelta(hours=1)
            )
        return _Job(f"copy-{len(self.copies)}")

    def load_table_from_json(
        self, rows: list[JsonRow], destination: str, job_config: bigquery.LoadJobConfig
    ) -> _Job:
        self.loads.append((rows, destination, str(job_config.write_disposition)))
        return _Job("load-1")


def _run(client: FakeClient, force: bool = False) -> list[TableSnapshot]:
    return list(
        snapshot(
            cast(bigquery.Client, client),
            DATASET,
            force=force,
            now=lambda: SNAPSHOT_AT,
            new_id=lambda: SNAPSHOT_ID,
        )
    )


def test_snapshot_copies_all_tables_and_records_metadata() -> None:
    client = FakeClient()
    results = _run(client)

    assert [destination for _, destination, _ in client.copies] == [
        f"{DATASET}.{table_name}" for table_name in TABLES
    ]
    assert {disposition for _, _, disposition in client.copies} == {"WRITE_EMPTY"}
    assert [result.row_count for result in results] == list(range(1, len(TABLES) + 1))

    (rows, destination, disposition) = client.loads[0]
    assert destination == f"{DATASET}.{METADATA_TABLE}"
    assert disposition == "WRITE_EMPTY"
    assert [row["table_name"] for row in rows] == list(TABLES)


def test_snapshot_metadata_rows_use_injected_clock_and_id() -> None:
    client = FakeClient()
    _run(client)

    (rows, _, _) = client.loads[0]
    assert rows[0] == {
        "snapshot_id": SNAPSHOT_ID,
        "table_name": TABLES[0],
        "source_table": f"{SOURCE_DATASET}.{TABLES[0]}",
        "source_last_modified": "2026-10-21T00:00:00+00:00",
        "row_count": 1,
        "snapshot_at": "2026-10-21T09:30:00+00:00",
        "copy_job_id": "copy-1",
    }
    assert {row["snapshot_id"] for row in rows} == {SNAPSHOT_ID}
    assert {row["snapshot_at"] for row in rows} == {"2026-10-21T09:30:00+00:00"}


def test_metadata_row_fields_match_bigquery_schema() -> None:
    assert list(SnapshotMetadataRow.model_fields) == [field.name for field in METADATA_SCHEMA]


@pytest.mark.parametrize("existing", [frozenset({"orders"}), frozenset({METADATA_TABLE})])
def test_snapshot_refuses_existing_tables_without_force(existing: frozenset[str]) -> None:
    client = FakeClient(existing)
    with pytest.raises(SnapshotError, match="--force"):
        _run(client)
    assert client.copies == []
    assert client.loads == []


def test_snapshot_with_force_overwrites_existing_tables() -> None:
    client = FakeClient(frozenset({"orders", METADATA_TABLE}))
    _run(client, force=True)
    assert {disposition for _, _, disposition in client.copies} == {"WRITE_TRUNCATE"}
    assert client.loads[0][2] == "WRITE_TRUNCATE"


def test_snapshot_aborts_before_metadata_when_source_changes_mid_copy() -> None:
    client = FakeClient()
    client.mutate_source_during_copy = "orders"
    with pytest.raises(SnapshotError, match="changed during the copy"):
        _run(client)
    assert client.loads == []


def test_snapshot_aborts_on_row_count_mismatch() -> None:
    client = FakeClient()
    original_copy = client.copy_table

    def short_copy(source: str, destination: str, job_config: bigquery.CopyJobConfig) -> _Job:
        job = original_copy(source, destination, job_config)
        client.tables[destination] = SimpleNamespace(num_rows=0)
        return job

    client.copy_table = short_copy  # type: ignore[method-assign]
    with pytest.raises(SnapshotError, match="copied 0 rows"):
        _run(client)
    assert client.loads == []
