import google.auth
import pytest
from google.auth import impersonated_credentials
from google.auth.credentials import AnonymousCredentials

from tools.bq import SCOPES, impersonated_client

TARGET_SA = "agent-readonly@test-project.iam.gserviceaccount.com"


@pytest.fixture
def requested_scopes(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Stub application-default credentials; record the scopes each call asks for."""
    calls: list[list[str]] = []

    def fake_default(scopes: list[str]) -> tuple[AnonymousCredentials, None]:
        calls.append(scopes)
        return AnonymousCredentials(), None  # type: ignore[no-untyped-call]

    monkeypatch.setattr(google.auth, "default", fake_default)
    return calls


def test_impersonated_client_acts_as_target_service_account(
    requested_scopes: list[list[str]],
) -> None:
    client = impersonated_client("test-project", TARGET_SA)

    credentials = client._credentials
    assert isinstance(credentials, impersonated_credentials.Credentials)
    assert credentials.service_account_email == TARGET_SA
    assert requested_scopes == [SCOPES]


def test_impersonated_client_uses_given_project_and_location(
    requested_scopes: list[list[str]],
) -> None:
    client = impersonated_client("test-project", TARGET_SA, location="EU")

    assert client.project == "test-project"
    assert client.location == "EU"


def test_scopes_are_bigquery_only() -> None:
    assert SCOPES == ["https://www.googleapis.com/auth/bigquery"]
