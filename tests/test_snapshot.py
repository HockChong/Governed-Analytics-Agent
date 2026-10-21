from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

from ingestion.snapshot import (
    METADATA_TABLE,
    SOURCE_DATASET,
    TABLES,
    SnapshotError,
    snapshot,
)

DATASET = "proj.thelook_snapshot"
MODIFIED = datetime(2026, 10, 21, tzinfo=UTC)


class _Job:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id

    def result(self) -> None:
        return None


class FakeClient:
    """Just enough of bigquery.Client for snapshot(): tables live in a dict."""

    def __init__(self, existing: frozenset[str] = frozenset()) -> None:
        self.tables: dict[str, SimpleNamespace] = {
            f"{SOURCE_DATASET}.{name}": SimpleNamespace(num_rows=i + 1, modified=MODIFIED)
            for i, name in enumerate(TABLES)
        }
        for name in existing:
            self.tables[f"{DATASET}.{name}"] = SimpleNamespace(num_rows=0, modified=MODIFIED)
        self.copies: list[tuple[str, str, str]] = []
        self.loads: list[tuple[list[dict[str, Any]], str, str]] = []
        self.mutate_source_during_copy: str | None = None

    def get_table(self, table_id: str) -> SimpleNamespace:
        if table_id not in self.tables:
            raise NotFound(table_id)  # type: ignore[no-untyped-call]
        return self.tables[table_id]

    def copy_table(self, source: str, dest: str, job_config: bigquery.CopyJobConfig) -> _Job:
        self.copies.append((source, dest, str(job_config.write_disposition)))
        self.tables[dest] = SimpleNamespace(num_rows=self.tables[source].num_rows)
        if source.endswith(f".{self.mutate_source_during_copy}"):
            self.tables[source] = SimpleNamespace(num_rows=99, modified=datetime.now(UTC))
        return _Job(f"copy-{len(self.copies)}")

    def load_table_from_json(
        self, rows: list[dict[str, Any]], dest: str, job_config: bigquery.LoadJobConfig
    ) -> _Job:
        self.loads.append((rows, dest, str(job_config.write_disposition)))
        return _Job("load-1")


def _run(client: FakeClient, force: bool = False) -> list[Any]:
    return list(snapshot(cast(bigquery.Client, client), DATASET, force=force))


def test_copies_all_tables_and_records_metadata() -> None:
    client = FakeClient()
    results = _run(client)

    assert [dest for _, dest, _ in client.copies] == [f"{DATASET}.{t}" for t in TABLES]
    assert {disp for _, _, disp in client.copies} == {"WRITE_EMPTY"}
    assert [r.row_count for r in results] == [i + 1 for i in range(len(TABLES))]

    (rows, dest, disposition) = client.loads[0]
    assert dest == f"{DATASET}.{METADATA_TABLE}"
    assert disposition == "WRITE_EMPTY"
    assert [r["table_name"] for r in rows] == list(TABLES)
    assert len({r["snapshot_id"] for r in rows}) == 1
    assert len({r["snapshot_at"] for r in rows}) == 1


@pytest.mark.parametrize("existing", [frozenset({"orders"}), frozenset({METADATA_TABLE})])
def test_refuses_existing_snapshot_without_force(existing: frozenset[str]) -> None:
    client = FakeClient(existing)
    with pytest.raises(SnapshotError, match="--force"):
        _run(client)
    assert client.copies == []
    assert client.loads == []


def test_force_overwrites() -> None:
    client = FakeClient(frozenset({"orders", METADATA_TABLE}))
    _run(client, force=True)
    assert {disp for _, _, disp in client.copies} == {"WRITE_TRUNCATE"}
    assert client.loads[0][2] == "WRITE_TRUNCATE"


def test_source_changing_mid_copy_aborts_before_metadata() -> None:
    client = FakeClient()
    client.mutate_source_during_copy = "orders"
    with pytest.raises(SnapshotError, match="changed during the copy"):
        _run(client)
    assert client.loads == []


def test_row_count_mismatch_aborts() -> None:
    client = FakeClient()
    original_copy = client.copy_table

    def short_copy(source: str, dest: str, job_config: bigquery.CopyJobConfig) -> _Job:
        job = original_copy(source, dest, job_config)
        client.tables[dest] = SimpleNamespace(num_rows=0)
        return job

    client.copy_table = short_copy  # type: ignore[method-assign]
    with pytest.raises(SnapshotError, match="copied 0 rows"):
        _run(client)
    assert client.loads == []
