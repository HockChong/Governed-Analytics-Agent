"""Profile the snapshot tables declared in dbt/models/sources.yml.

Run via `make profile`. Writes docs/data-profile.md.
Exit codes: 0 done, 1 schema drift or unsafe identifier, 2 configuration missing.
"""

import sys
from datetime import datetime
from pathlib import Path

from core.config import Settings
from core.errors import ProfileError
from ingestion.profile import load_column_specs, profile_snapshot, render_markdown
from ingestion.snapshot import METADATA_TABLE
from tools.bq import impersonated_client

ROOT = Path(__file__).resolve().parents[1]
SOURCES_YML = ROOT / "dbt" / "models" / "sources.yml"
OUTPUT = ROOT / "docs" / "data-profile.md"


def main() -> int:
    """Profile every declared table and write the Markdown report."""
    settings = Settings()
    if settings.dbt_impersonate_sa is None:
        print("profile refused: DBT_IMPERSONATE_SA is not set", file=sys.stderr)
        return 2
    client = impersonated_client(settings.gcp_project_id, settings.dbt_impersonate_sa)
    dataset = f"{settings.gcp_project_id}.{settings.snapshot_dataset}"

    # list_rows reads table storage directly: no query job, no bytes billed.
    metadata = next(iter(client.list_rows(f"{dataset}.{METADATA_TABLE}", max_results=1)))
    snapshot_id = str(metadata["snapshot_id"])
    snapshot_at = metadata["snapshot_at"]
    if not isinstance(snapshot_at, datetime):
        print(f"profile refused: bad snapshot_at {snapshot_at!r}", file=sys.stderr)
        return 1

    try:
        profiles = profile_snapshot(
            client,
            dataset,
            load_column_specs(SOURCES_YML),
            snapshot_at=snapshot_at,
            max_bytes_billed=settings.max_bytes_billed,
        )
    except ProfileError as error:
        print(f"profile refused: {error}", file=sys.stderr)
        return 1
    OUTPUT.write_text(
        render_markdown(profiles, snapshot_id=snapshot_id, snapshot_at=snapshot_at),
        encoding="utf-8",
    )
    print(f"profiled {len(profiles)} tables from snapshot {snapshot_id} into {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
