"""Freeze thelook_ecommerce into our own dataset so results are reproducible.

The public dataset is regenerated over time (it even holds future-dated rows), so
dbt reads from a one-off copy instead. Uses copy and load jobs only: no SQL DDL/DML.
Refuses to touch an existing snapshot unless force=True.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from google.cloud import bigquery
from google.cloud.exceptions import NotFound

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


@dataclass(frozen=True)
class TableSnapshot:
    table_name: str
    source_last_modified: datetime
    row_count: int
    copy_job_id: str


def _exists(client: bigquery.Client, table_id: str) -> bool:
    try:
        client.get_table(table_id)
    except NotFound:
        return False
    return True


def existing_targets(client: bigquery.Client, dataset: str) -> list[str]:
    """Snapshot tables (including metadata) already present in `dataset`."""
    names = (*TABLES, METADATA_TABLE)
    return [name for name in names if _exists(client, f"{dataset}.{name}")]


def snapshot(client: bigquery.Client, dataset: str, *, force: bool = False) -> list[TableSnapshot]:
    """Copy every source table into `dataset` and record row counts in snapshot_metadata."""
    existing = existing_targets(client, dataset)
    if existing and not force:
        raise SnapshotError(
            f"{dataset} already has {', '.join(existing)}; pass --force to overwrite"
        )
    disposition = (
        bigquery.WriteDisposition.WRITE_TRUNCATE if force else bigquery.WriteDisposition.WRITE_EMPTY
    )

    snapshot_at = datetime.now(UTC)
    results: list[TableSnapshot] = []
    for name in TABLES:
        source_id = f"{SOURCE_DATASET}.{name}"
        before = client.get_table(source_id)
        job = client.copy_table(
            source_id,
            f"{dataset}.{name}",
            job_config=bigquery.CopyJobConfig(write_disposition=disposition, labels=LABELS),
        )
        job.result()
        after = client.get_table(source_id)
        if after.modified != before.modified:
            raise SnapshotError(f"{source_id} changed during the copy; rerun with --force")
        copied = client.get_table(f"{dataset}.{name}")
        if copied.num_rows != before.num_rows:
            raise SnapshotError(
                f"{name}: copied {copied.num_rows} rows, source had {before.num_rows}"
            )
        if before.modified is None or copied.num_rows is None or job.job_id is None:
            raise SnapshotError(f"{name}: BigQuery returned incomplete table metadata")
        results.append(TableSnapshot(name, before.modified, copied.num_rows, job.job_id))

    snapshot_id = uuid.uuid4().hex
    rows = [
        {
            "snapshot_id": snapshot_id,
            "table_name": r.table_name,
            "source_table": f"{SOURCE_DATASET}.{r.table_name}",
            "source_last_modified": r.source_last_modified.isoformat(),
            "row_count": r.row_count,
            "snapshot_at": snapshot_at.isoformat(),
            "copy_job_id": r.copy_job_id,
        }
        for r in results
    ]
    client.load_table_from_json(
        rows,
        f"{dataset}.{METADATA_TABLE}",
        job_config=bigquery.LoadJobConfig(
            schema=METADATA_SCHEMA, write_disposition=disposition, labels=LABELS
        ),
    ).result()
    return results
