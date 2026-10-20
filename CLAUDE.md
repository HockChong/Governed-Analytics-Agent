# Governed Analytics Agent

Text-to-SQL analytics agent over BigQuery `bigquery-public-data.thelook_ecommerce`,
modelled with dbt. Full design: docs/architecture.md. Follow it; if you want to
deviate, stop and explain why first.

## Non-negotiable rules

- The model proposes, code decides. Never execute LLM-generated SQL without the
SQL guard (sqlglot AST parse, table/column allowlist, join-graph check,
fan-out rule, forced LIMIT, dry-run byte cap).
Phase 1 guard: parse, single SELECT, allowlist, PII deny, edge exists,
no cross joins, LIMIT, dry-run cap. Phase 2 adds fan-out, key-column and
cardinality checks.
- Read-only warehouse credentials only. No code path may issue DDL or DML.
- Bounded workflow: max 3 repair attempts, max 6 model calls, 30 s budget.
No free-running agent loops, no multi-agent frameworks.
- Golden test questions (evals/golden/) must never be used as retrieval
examples (data/verified_queries/). Do not create or edit golden expected
results without asking me; I label them by hand.
- PII columns (tagged `pii: true` in dbt meta) are never sent to a model and
never stored as sample values.
- No secrets in code or prompts. Use environment variables; document them in
.env.example.



## Stack

Python 3.12, uv, FastAPI, Pydantic v2, sqlglot, dbt-bigquery + MetricFlow,
Postgres 16 + pgvector, Dagster, pytest, ruff, mypy, Docker Compose,
Terraform (GCP), GitHub Actions, OpenTelemetry + Langfuse.

## Repo layout

src/api, src/core (orchestrator, prompts, schemas), src/tools (guard,
retriever, executor, checker), src/ingestion, dbt/, evals/, tests/, infra/,
docs/ (architecture.md, adr/, eval-report.md, runbook.md)

## How to work

- Before a non-trivial change, write a short plan and wait for my OK.
- Write or update tests with every change. Run `make test` and `make lint`
before saying a task is done, and show me the output.
- Small commits with clear messages, one logical change each.
- If a requirement is unclear or a library behaves unexpectedly, ask rather
than guess.
- Never claim a metric or result you have not measured by running code.

