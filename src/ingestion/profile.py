"""Profile snapshot tables to inform dbt descriptions: nulls, distinct counts, ranges.

PII columns (config.meta.pii in sources.yml) get null and distinct counts only.
No min, max or top values are ever selected for them, so no PII value is fetched.
"""

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

import yaml
from google.cloud import bigquery
from pydantic import BaseModel, ConfigDict

from core.errors import ProfileError

DataType = Literal["int64", "float64", "string", "timestamp", "geography"]

TOP_VALUES_MAX_DISTINCT = 25
DISPLAY_MAX_CHARS = 40
LABELS = {"component": "profile"}

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
_TABLE_ID = re.compile(r"^[a-z0-9-]+\.[a-z0-9_]+\.[a-z0-9_]+$")
# BigQuery reports legacy names (INTEGER, FLOAT) for tables copied from public data.
_BIGQUERY_TYPES: dict[str, frozenset[str]] = {
    "int64": frozenset({"INTEGER", "INT64"}),
    "float64": frozenset({"FLOAT", "FLOAT64"}),
    "string": frozenset({"STRING"}),
    "timestamp": frozenset({"TIMESTAMP"}),
    "geography": frozenset({"GEOGRAPHY"}),
}

ResultRow = Mapping[str, object]


class ColumnSpec(BaseModel):
    """A source column as declared in sources.yml."""

    model_config = ConfigDict(frozen=True)

    name: str
    data_type: DataType
    pii: bool


class ColumnProfile(BaseModel):
    """Measured facts about one column; value fields stay None for PII columns."""

    model_config = ConfigDict(frozen=True)

    name: str
    data_type: DataType
    pii: bool
    null_count: int
    distinct_count: int | None = None
    min_value: str | None = None
    max_value: str | None = None
    future_count: int | None = None
    top_values: list[tuple[str | None, int]] = []


class TableProfile(BaseModel):
    """Measured facts about one snapshot table."""

    model_config = ConfigDict(frozen=True)

    table_name: str
    row_count: int
    columns: list[ColumnProfile]


def load_column_specs(sources_yml: Path) -> dict[str, list[ColumnSpec]]:
    """Read declared columns per table, with PII flags from config.meta.pii."""
    document = yaml.safe_load(sources_yml.read_text(encoding="utf-8"))
    return {
        table["name"]: [
            ColumnSpec(
                name=column["name"],
                data_type=column["data_type"],
                pii=column.get("config", {}).get("meta", {}).get("pii") is True,
            )
            for column in table["columns"]
        ]
        for table in document["sources"][0]["tables"]
    }


def check_schema_matches(
    table_name: str, declared: Sequence[ColumnSpec], actual: Sequence[tuple[str, str]]
) -> None:
    """Raise ProfileError unless the warehouse columns and types match sources.yml."""
    declared_names = {column.name for column in declared}
    actual_types = dict(actual)
    undeclared = sorted(set(actual_types) - declared_names)
    missing = sorted(declared_names - set(actual_types))
    if undeclared or missing:
        raise ProfileError(f"{table_name}: undeclared {undeclared}, missing {missing}")
    for column in declared:
        if actual_types[column.name] not in _BIGQUERY_TYPES[column.data_type]:
            raise ProfileError(
                f"{table_name}.{column.name}: declared {column.data_type},"
                f" warehouse has {actual_types[column.name]}"
            )


def profile_query(table_id: str, columns: Sequence[ColumnSpec]) -> str:
    """Build one query returning row count and per-column stats, aliased c<index>_<stat>."""
    expressions = ["count(*) as row_count"]
    for index, column in enumerate(columns):
        quoted = _quote(column.name)
        prefix = f"c{index}"
        expressions.append(f"countif({quoted} is null) as {prefix}_nulls")
        # GEOGRAPHY supports neither DISTINCT nor MIN/MAX.
        if column.data_type == "geography":
            continue
        expressions.append(f"count(distinct {quoted}) as {prefix}_distinct")
        if column.pii:
            continue
        expressions.append(f"cast(min({quoted}) as string) as {prefix}_min")
        expressions.append(f"cast(max({quoted}) as string) as {prefix}_max")
        if column.data_type == "timestamp":
            expressions.append(f"countif({quoted} > @snapshot_at) as {prefix}_future")
    select_list = ",\n  ".join(expressions)
    return f"select\n  {select_list},\nfrom `{_checked_table_id(table_id)}`"


def top_values_candidates(
    columns: Sequence[ColumnSpec], distinct_counts: Mapping[str, int]
) -> list[str]:
    """Non-PII string columns with few enough distinct values to list them all."""
    return [
        column.name
        for column in columns
        if column.data_type == "string"
        and not column.pii
        and distinct_counts.get(column.name, TOP_VALUES_MAX_DISTINCT + 1) <= TOP_VALUES_MAX_DISTINCT
    ]


def top_values_query(table_id: str, column: ColumnSpec) -> str:
    """Build a value-count query for one non-PII column."""
    if column.pii:
        raise ProfileError(f"refusing to list values of PII column {column.name}")
    quoted = _quote(column.name)
    return (
        f"select\n  {quoted} as value,\n  count(*) as row_count,\n"
        f"from `{_checked_table_id(table_id)}`\n"
        "group by value\norder by row_count desc"
    )


def profile_snapshot(
    client: bigquery.Client,
    dataset: str,
    specs: Mapping[str, Sequence[ColumnSpec]],
    *,
    snapshot_at: datetime,
    max_bytes_billed: int,
) -> list[TableProfile]:
    """Profile every declared table in `dataset` after checking its schema."""
    profiles: list[TableProfile] = []
    for table_name, columns in specs.items():
        table_id = f"{dataset}.{table_name}"
        table = client.get_table(table_id)
        check_schema_matches(
            table_name, columns, [(field.name, field.field_type) for field in table.schema]
        )
        parameters = [bigquery.ScalarQueryParameter("snapshot_at", "TIMESTAMP", snapshot_at)]
        (row,) = _run(client, profile_query(table_id, columns), max_bytes_billed, parameters)
        column_profiles = [
            _column_profile(column, row, index) for index, column in enumerate(columns)
        ]
        distinct_counts = {
            profile.name: profile.distinct_count
            for profile in column_profiles
            if profile.distinct_count is not None
        }
        listable = set(top_values_candidates(columns, distinct_counts))
        column_profiles = [
            _with_top_values(client, table_id, column, profile, max_bytes_billed)
            if column.name in listable
            else profile
            for column, profile in zip(columns, column_profiles, strict=True)
        ]
        profiles.append(
            TableProfile(
                table_name=table_name,
                row_count=_as_int(row["row_count"]),
                columns=column_profiles,
            )
        )
    return profiles


def render_markdown(
    profiles: Sequence[TableProfile], *, snapshot_id: str, snapshot_at: datetime
) -> str:
    """Render profiles as a Markdown document for docs/data-profile.md."""
    lines = [
        "# Snapshot data profile",
        "",
        f"Generated by `make profile` from snapshot `{snapshot_id}`"
        f" (taken {snapshot_at.isoformat()}). Do not edit by hand.",
        "PII columns show null and distinct counts only. "
        "`future` counts timestamps after the snapshot time.",
    ]
    for table in profiles:
        lines += [
            "",
            f"## {table.table_name}",
            "",
            f"{table.row_count:,} rows.",
            "",
            "| column | type | nulls | distinct | min | max | notes |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        lines += [_column_row(column) for column in table.columns]
        listed = [column for column in table.columns if column.top_values]
        if listed:
            lines += ["", "Values (count):", ""]
            lines += [
                f"- `{column.name}`: "
                + ", ".join(f"{_display(value)} ({count:,})" for value, count in column.top_values)
                for column in listed
            ]
    return "\n".join(lines) + "\n"


def _quote(name: str) -> str:
    # Names come from sources.yml, but they are interpolated into SQL, so check them.
    if not _IDENTIFIER.match(name):
        raise ProfileError(f"unsafe identifier: {name!r}")
    return f"`{name}`"


def _checked_table_id(table_id: str) -> str:
    if not _TABLE_ID.match(table_id):
        raise ProfileError(f"unsafe table identifier: {table_id!r}")
    return table_id


def _run(
    client: bigquery.Client,
    sql: str,
    max_bytes_billed: int,
    parameters: list[bigquery.ScalarQueryParameter] | None = None,
) -> list[ResultRow]:
    job_config = bigquery.QueryJobConfig(
        query_parameters=parameters or [],
        maximum_bytes_billed=max_bytes_billed,
        labels=LABELS,
    )
    return [cast(ResultRow, row) for row in client.query(sql, job_config=job_config).result()]


def _column_profile(column: ColumnSpec, row: ResultRow, index: int) -> ColumnProfile:
    prefix = f"c{index}"
    return ColumnProfile(
        name=column.name,
        data_type=column.data_type,
        pii=column.pii,
        null_count=_as_int(row[f"{prefix}_nulls"]),
        distinct_count=_optional_int(row.get(f"{prefix}_distinct")),
        min_value=_optional_str(row.get(f"{prefix}_min")),
        max_value=_optional_str(row.get(f"{prefix}_max")),
        future_count=_optional_int(row.get(f"{prefix}_future")),
    )


def _with_top_values(
    client: bigquery.Client,
    table_id: str,
    column: ColumnSpec,
    profile: ColumnProfile,
    max_bytes_billed: int,
) -> ColumnProfile:
    rows = _run(client, top_values_query(table_id, column), max_bytes_billed)
    top_values = [(_optional_str(row["value"]), _as_int(row["row_count"])) for row in rows]
    return profile.model_copy(update={"top_values": top_values})


def _column_row(column: ColumnProfile) -> str:
    notes = []
    if column.pii:
        notes.append("pii")
    if column.future_count:
        notes.append(f"{column.future_count:,} future")
    cells = [
        column.name,
        column.data_type,
        f"{column.null_count:,}",
        "—" if column.distinct_count is None else f"{column.distinct_count:,}",
        _display(column.min_value) if column.min_value is not None else "—",
        _display(column.max_value) if column.max_value is not None else "—",
        ", ".join(notes),
    ]
    return "| " + " | ".join(cells) + " |"


def _display(value: str | None) -> str:
    if value is None:
        return "null"
    shortened = value if len(value) <= DISPLAY_MAX_CHARS else value[: DISPLAY_MAX_CHARS - 1] + "…"
    return shortened.replace("|", "\\|")


def _as_int(value: object) -> int:
    if not isinstance(value, int):
        raise ProfileError(f"expected an integer from BigQuery, got {value!r}")
    return value


def _optional_int(value: object) -> int | None:
    return None if value is None else _as_int(value)


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)
