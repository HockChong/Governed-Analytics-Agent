"""The agent's warehouse identity must not be able to write.

Runs only when AGENT_IMPERSONATE_SA is set and
application-default credentials exist; otherwise skipped (e.g. in CI).
"""

import uuid

import pytest
from google.api_core.exceptions import Forbidden
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery

from core.config import Settings
from tools.bq import impersonated_client

pytestmark = pytest.mark.bq


@pytest.fixture(scope="module")
def agent_client(settings: Settings) -> bigquery.Client:
    if settings.agent_impersonate_sa is None:
        pytest.skip("AGENT_IMPERSONATE_SA not set")
    try:
        return impersonated_client(settings.gcp_project_id, settings.agent_impersonate_sa)
    except DefaultCredentialsError:
        pytest.skip("no application-default credentials")


def test_agent_can_read_public_dataset(agent_client: bigquery.Client) -> None:
    # Positive control: proves the denial below is about permissions, not broken auth.
    job = agent_client.query(
        "select order_id from `bigquery-public-data.thelook_ecommerce.orders` limit 1",
        job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False),
    )
    assert job.total_bytes_processed is not None


def test_agent_cannot_create_table(agent_client: bigquery.Client, settings: Settings) -> None:
    table = f"{settings.bq_dataset}.readonly_probe_{uuid.uuid4().hex[:8]}"
    with pytest.raises(Forbidden, match="bigquery.tables.create"):
        agent_client.query(f"create table {table} as select 1 as x").result()  # noqa: S608
