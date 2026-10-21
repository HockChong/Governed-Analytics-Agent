"""BigQuery clients that impersonate a service account. No key files."""

import google.auth
from google.auth import impersonated_credentials
from google.cloud import bigquery

SCOPES = ["https://www.googleapis.com/auth/bigquery"]


def impersonated_client(project: str, target_sa: str, location: str = "US") -> bigquery.Client:
    """Client acting as `target_sa`, using the caller's application-default credentials."""
    source, _ = google.auth.default(scopes=SCOPES)
    credentials = impersonated_credentials.Credentials(  # type: ignore[no-untyped-call]
        source_credentials=source, target_principal=target_sa, target_scopes=SCOPES
    )
    return bigquery.Client(project=project, credentials=credentials, location=location)
