from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.config import Settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # `make test` exports .env; tests must not depend on the developer's values.
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def test_settings_require_env() -> None:
    with pytest.raises(ValidationError, match="env"):
        Settings()


@pytest.mark.parametrize("env", ["test", "staging", "prod"])
def test_settings_reject_dev_auth_stub_outside_dev(
    monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.setenv("ENV", env)
    monkeypatch.setenv("DEV_AUTH_STUB", "true")
    with pytest.raises(ValidationError, match="DEV_AUTH_STUB is only allowed when ENV=dev"):
        Settings()


def test_settings_allow_dev_auth_stub_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("DEV_AUTH_STUB", "true")
    assert Settings().dev_auth_stub is True


def test_settings_defaults_match_architecture_budgets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "dev")
    settings = Settings()
    budgets = (settings.max_repairs, settings.max_model_calls, settings.request_budget_s)
    assert budgets == (3, 6, 30.0)
    assert settings.max_bytes_billed == 2_000_000_000
    assert settings.primary_model == "claude-sonnet-5-5"
    assert settings.dev_auth_stub is False


@pytest.mark.parametrize("value", ["0", "3"])
def test_settings_accept_max_repairs_from_0_to_3(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("MAX_REPAIRS", value)
    assert Settings().max_repairs == int(value)


@pytest.mark.parametrize("value", ["-1", "4"])
def test_settings_reject_max_repairs_outside_0_to_3(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("MAX_REPAIRS", value)
    with pytest.raises(ValidationError, match="max_repairs"):
        Settings()


def test_settings_treat_empty_values_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("EVAL_REFERENCE_DATE", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    settings = Settings()
    assert settings.eval_reference_date is None
    assert settings.anthropic_api_key is None


def test_settings_parse_eval_reference_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("EVAL_REFERENCE_DATE", "2024-06-30")
    assert Settings().eval_reference_date == date(2024, 6, 30)


def test_settings_repr_hides_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw-not-real")
    text = repr(Settings())
    assert "sk-test-not-real" not in text
    assert "pw-not-real" not in text


def test_postgres_conninfo_sets_timeout_and_ipv4_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "dev")
    conninfo = Settings().postgres_conninfo()
    assert "connect_timeout=5" in conninfo
    assert "host=127.0.0.1" in conninfo


def test_env_example_documents_every_setting() -> None:
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    documented = {
        line.split("=", 1)[0] for line in lines if "=" in line and not line.startswith("#")
    }
    assert {name.upper() for name in Settings.model_fields} <= documented
