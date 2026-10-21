"""Runtime settings, read from environment variables (documented in .env.example)."""

from datetime import date
from typing import Literal

from psycopg.conninfo import make_conninfo
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Empty values in .env (e.g. EVAL_REFERENCE_DATE=) mean "unset", not "".
    model_config = SettingsConfigDict(env_ignore_empty=True)

    # No default: a missing ENV must not silently become "dev".
    env: Literal["dev", "test", "staging", "prod"]
    # Trusts X-User / X-Role headers instead of OIDC. Only allowed when env == "dev".
    dev_auth_stub: bool = False

    gcp_project_id: str = "governed-analytics-dev"
    bq_dataset: str = "thelook_dbt"
    snapshot_dataset: str = "thelook_snapshot"
    dbt_impersonate_sa: str | None = None
    agent_impersonate_sa: str | None = None

    # 127.0.0.1, not localhost: on Windows "localhost" tries ::1 first, which hangs
    # because compose publishes on IPv4 only.
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5433
    postgres_user: str = "agent"
    postgres_password: SecretStr | None = None
    postgres_db: str = "governed_analytics"

    anthropic_api_key: SecretStr | None = None
    primary_model: str = "claude-sonnet-5-5"
    # Placeholder for Phase 4 routing; not used yet.
    small_model: str = "claude-haiku-5-5"

    # Workflow budgets (architecture section 4).
    max_repairs: int = Field(default=3, ge=0, le=3)
    max_model_calls: int = Field(default=6, ge=1, le=6)
    request_budget_s: float = Field(default=30.0, gt=0, le=30.0)
    bq_timeout_s: float = Field(default=20.0, gt=0)
    max_bytes_billed: int = Field(default=2_000_000_000, gt=0, le=2_000_000_000)
    row_limit: int = Field(default=1000, ge=1, le=10_000)

    # Anchors "last week" etc. in eval runs; None means today.
    eval_reference_date: date | None = None

    @model_validator(mode="after")
    def _dev_auth_stub_only_in_dev(self) -> "Settings":
        if self.dev_auth_stub and self.env != "dev":
            raise ValueError(f"DEV_AUTH_STUB is only allowed when ENV=dev, not ENV={self.env}")
        return self

    def postgres_conninfo(self, dbname: str | None = None) -> str:
        password = self.postgres_password.get_secret_value() if self.postgres_password else None
        return make_conninfo(
            host=self.postgres_host,
            port=self.postgres_port,
            user=self.postgres_user,
            password=password,
            dbname=dbname or self.postgres_db,
            connect_timeout=5,
        )
