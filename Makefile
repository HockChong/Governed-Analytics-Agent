-include .env
export

PYTHONPATH := src
DBT_DIRS = --project-dir dbt --profiles-dir dbt

.PHONY: install test test-integration lint format up down migrate snapshot dbt-debug dbt-parse dbt-build

install:
	uv sync

# Deselects by marker, so it stays offline even when .env holds real credentials.
test:
	uv run pytest -m "not bq and not integration"

test-integration:
	uv run pytest -m "bq or integration"

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src tests scripts

up:
	docker compose up -d --wait

down:
	docker compose down

migrate:
	uv run python -m core.migrations

# One-off copy of thelook_ecommerce. `make snapshot FORCE=1` overwrites an existing one.
snapshot:
	uv run python scripts/snapshot.py $(if $(FORCE),--force,)

dbt-debug:
	uv run dbt debug $(DBT_DIRS)

dbt-parse:
	uv run dbt parse $(DBT_DIRS)

dbt-build:
	uv run dbt build $(DBT_DIRS)
