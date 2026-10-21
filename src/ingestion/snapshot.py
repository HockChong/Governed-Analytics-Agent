"""Freeze thelook_ecommerce into our own dataset so results are reproducible.

The public dataset is regenerated over time (it even holds future-dated rows), so
dbt reads from a one-off copy instead. Uses copy and load jobs only: no SQL DDL/DML.
Refuses to touch an existing snapshot unless force=True.
"""

from collections.abc import Callable
from datetime import datetime

from google.cloud import bigquery
from google.cloud.exceptions import NotFound
from pydantic import BaseModel, ConfigDict, Field, field_serializer

from core.errors import SnapshotError

SOURCE_DATASET = "bigquery-public-data.thelook_ecommerce"
TABLES = (
    "distribution_centers",
    "events",
    "inventory_items",
    "order_items",
    "orders",
    "products",
    "users",
)
METADATA_TABLE = "snapshot_metadata"
METADATA_SCHEMA = [
    bigquery.SchemaField("snapshot_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("table_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("source_table", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("source_last_modified", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("row_count", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("snapshot_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("copy_job_id", "STRING", mode="REQUIRED"),
]
LABELS = {"component": "snapshot"}


class TableSnapshot(BaseModel):
    """One source table copied into the snapshot dataset, as verified after the copy."""

    model_config = ConfigDict(frozen=True)

    table_name: str
    source_last_modified: datetime
    row_count: int = Field(ge=0)
    copy_job_id: str


class SnapshotMetadataRow(BaseModel):
    """One row of the snapshot_metadata table; fields mirror METADATA_SCHEMA."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    table_name: str
    source_table: str
    source_last_modified: datetime
    row_count: int = Field(ge=0)
    snapshot_at: datetime
    copy_job_id: str

    @field_serializer("source_last_modified", "snapshot_at")
    def _serialize_timestamp(self, value: datetime) -> str:
        # Pydantic's JSON mode would write "Z"; keep the "+00:00" form the load job
        # was first written against.
        return value.isoformat()


def snapshot(
    client: bigquery.Client,
    dataset: str,
    *,
    force: bool = False,
    now: Callable[[], datetime],
    new_id: Callable[[], str],
) -> list[TableSnapshot]:
    """Copy every source table into `dataset` and record row counts in snapshot_metadata.

    Args:
        now: Clock for snapshot_at; injected so tests can pin it.
        new_id: Generator for snapshot_id; injected so tests can pin it.
    """
    _refuse_existing_snapshot(client, dataset, force=force)
    disposition = _write_disposition(force)
    snapshot_at = now()
    table_snapshots = [
        _copy_and_verify(client, table_name, dataset, disposition) for table_name in TABLES
    ]
    rows = metadata_rows(table_snapshots, snapshot_id=new_id(), snapshot_at=snapshot_at)
    _load_metadata(client, dataset, rows, disposition)
    return table_snapshots


def existing_targets(client: bigquery.Client, dataset: str) -> list[str]:
    """Snapshot tables (including metadata) already present in `dataset`."""
    names = (*TABLES, METADATA_TABLE)
    return [name for name in names if _exists(client, f"{dataset}.{name}")]


def metadata_rows(
    table_snapshots: list[TableSnapshot], *, snapshot_id: str, snapshot_at: datetime
) -> list[SnapshotMetadataRow]:
    """Build one snapshot_metadata row per copied table, all sharing one snapshot id and time."""
    return [
        SnapshotMetadataRow(
            snapshot_id=snapshot_id,
            table_name=table_snapshot.table_name,
            source_table=f"{SOURCE_DATASET}.{table_snapshot.table_name}",
            source_last_modified=table_snapshot.source_last_modified,
            row_count=table_snapshot.row_count,
            snapshot_at=snapshot_at,
            copy_job_id=table_snapshot.copy_job_id,
        )
        for table_snapshot in table_snapshots
    ]


def _exists(client: bigquery.Client, table_id: str) -> bool:
    try:
        client.get_table(table_id)
    except NotFound:
        return False
    return True


def _refuse_existing_snapshot(client: bigquery.Client, dataset: str, *, force: bool) -> None:
    existing = existing_targets(client, dataset)
    if existing and not force:
        raise SnapshotError(
            f"{dataset} already has {', '.join(existing)}; pass --force to overwrite"
        )


def _write_disposition(force: bool) -> str:
    if force:
        return bigquery.WriteDisposition.WRITE_TRUNCATE
    return bigquery.WriteDisposition.WRITE_EMPTY


def _copy_and_verify(
    client: bigquery.Client, table_name: str, dataset: str, disposition: str
) -> TableSnapshot:
    source_id = f"{SOURCE_DATASET}.{table_name}"
    before = client.get_table(source_id)
    job = client.copy_table(
        source_id,
        f"{dataset}.{table_name}",
        job_config=bigquery.CopyJobConfig(write_disposition=disposition, labels=LABELS),
    )
    job.result()
    after = client.get_table(source_id)
    if after.modified != before.modified:
        raise SnapshotError(f"{source_id} changed during the copy; rerun with --force")
    copied = client.get_table(f"{dataset}.{table_name}")
    if copied.num_rows != before.num_rows:
        raise SnapshotError(
            f"{table_name}: copied {copied.num_rows} rows, source had {before.num_rows}"
        )
    if before.modified is None or copied.num_rows is None or job.job_id is None:
        raise SnapshotError(f"{table_name}: BigQuery returned incomplete table metadata")
    return TableSnapshot(
        table_name=table_name,
        source_last_modified=before.modified,
        row_count=copied.num_rows,
        copy_job_id=job.job_id,
    )


def _load_metadata(
    client: bigquery.Client, dataset: str, rows: list[SnapshotMetadataRow], disposition: str
) -> None:
    client.load_table_from_json(
        [row.model_dump(mode="json") for row in rows],
        f"{dataset}.{METADATA_TABLE}",
        job_config=bigquery.LoadJobConfig(
            schema=METADATA_SCHEMA, write_disposition=disposition, labels=LABELS
        ),
    ).result()
