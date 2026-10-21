"""Copy thelook_ecommerce into ${SNAPSHOT_DATASET}.

Run via `make snapshot`; `make snapshot FORCE=1` adds --force.
Exit codes: 0 done, 1 snapshot refused or unverified, 2 configuration missing.
"""

import argparse
import sys
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from core.config import Settings
from core.errors import SnapshotError
from ingestion.snapshot import SOURCE_DATASET, snapshot
from tools.bq import impersonated_client


def main(argv: Sequence[str] | None = None) -> int:
    """Run the snapshot and print one line per copied table."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="overwrite an existing snapshot")
    args = parser.parse_args(argv)

    settings = Settings()
    if settings.dbt_impersonate_sa is None:
        print("snapshot refused: DBT_IMPERSONATE_SA is not set", file=sys.stderr)
        return 2
    dataset = f"{settings.gcp_project_id}.{settings.snapshot_dataset}"
    client = impersonated_client(settings.gcp_project_id, settings.dbt_impersonate_sa)
    try:
        results = snapshot(
            client,
            dataset,
            force=args.force,
            now=lambda: datetime.now(UTC),
            new_id=lambda: uuid.uuid4().hex,
        )
    except SnapshotError as error:
        print(f"snapshot refused: {error}", file=sys.stderr)
        return 1
    print(f"snapshot of {SOURCE_DATASET} into {dataset}")
    for result in results:
        print(
            f"  {result.table_name:<22}{result.row_count:>12,} rows"
            f"  (source {result.source_last_modified})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
