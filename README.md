# Governed Analytics Agent

Text-to-SQL analytics agent over BigQuery `bigquery-public-data.thelook_ecommerce`,
modelled with dbt. Every model-generated query passes a deterministic SQL guard and
runs with read-only credentials. Design: [docs/architecture.md](docs/architecture.md).

Status: Phase 1 (MVP) in progress. No results are reported yet.

## Quick start (local dev)

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), Docker, GNU make and the
gcloud CLI.

```sh
cp .env.example .env               # then fill in values
gcloud auth application-default login
make install
make up                            # Postgres 16 + pgvector on localhost:5433
make migrate
make test
make lint
```
