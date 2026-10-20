-include .env
export

DBT_DIRS = --project-dir dbt --profiles-dir dbt

.PHONY: install test lint format dbt-debug dbt-parse

install:
	uv sync

test:
	uv run pytest

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src tests

dbt-debug:
	uv run dbt debug $(DBT_DIRS)

dbt-parse:
	uv run dbt parse $(DBT_DIRS)
