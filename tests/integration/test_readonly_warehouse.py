"""The agent's warehouse identity must not be able to write.

Runs only when AGENT_IMPERSONATE_SA is set and
application-default credentials exist; otherwise skipped (e.g. in CI).
"""

import uuid

import google.auth
import pytest
from google.api_core.exceptions import Forbidden
from google.auth import impersonated_credentials
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery

from core.config import Settings

pytestmark = pytest.mark.bq

SCOPES = ["https://www.googleapis.com/auth/bigquery"]


@pytest.fixture(scope="module")
def agent_client(settings: Settings) -> bigquery.Client:
    project = settings.gcp_project_id
    target = settings.agent_impersonate_sa
    if target is None:
        pytest.skip("AGENT_IMPERSONATE_SA not set")
    try:
        source, _ = google.auth.default(scopes=SCOPES)
    except DefaultCredentialsError:
        pytest.skip("no application-default credentials")
    credentials = impersonated_credentials.Credentials(  # type: ignore[no-untyped-call]
        source_credentials=source, target_principal=target, target_scopes=SCOPES
    )
    return bigquery.Client(project=project, credentials=credentials, location="US")


def test_agent_can_read_public_dataset(agent_client: bigquery.Client) -> None:
    # Positive control: proves the denial below is about permissions, not broken auth.
    job = agent_client.query(
        "SELECT order_id FROM `bigquery-public-data.thelook_ecommerce.orders` LIMIT 1",
        job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False),
    )
    assert job.total_bytes_processed is not None


def test_agent_cannot_create_table(agent_client: bigquery.Client, settings: Settings) -> None:
    table = f"{settings.bq_dataset}.readonly_probe_{uuid.uuid4().hex[:8]}"
    with pytest.raises(Forbidden, match="bigquery.tables.create"):
        agent_client.query(f"CREATE TABLE {table} AS SELECT 1 AS x").result()  # noqa: S608
