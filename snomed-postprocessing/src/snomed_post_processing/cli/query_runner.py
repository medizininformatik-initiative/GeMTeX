#!/usr/bin/env python3
"""Run a SQL file against a SQLite database using Python's stdlib sqlite3.

Usage:
  uv run sql-query DB.sqlite queries/annotation-store/query.sql
  uv run sql-query --param n=20 DB.sqlite queries/annotation-store/top_sctids.sql
  uv run sql-query --format json DB.sqlite query.sql
  uv run sql-query --format csv DB.sqlite query.sql > result.csv

SQL files can define default named parameters in comments:
  -- @param n=50
CLI --param values override these defaults.

SQL files can also request optional Python post-processing, e.g.:
  -- @partial_bin covered_text_bin
  -- @sort_by order
  -- @post_limit n
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Iterable

import click

_PARAM_DEFAULT_RE = re.compile(r"^\s*--\s*@param\s+([^=\s]+)=(.*)$")
_PARTIAL_BIN_RE = re.compile(r"^\s*--\s*@partial_bin\s+(.*)$")
_POST_LIMIT_RE = re.compile(r"^\s*--\s*@post_limit\s+([^\s]+)\s*$")
_SORT_BY_RE = re.compile(r"^\s*--\s*@sort_by\s+([^\s]+)\s*$")


def _rows_as_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def _parse_sql_param_defaults(sql: str) -> dict[str, object]:
    values = []
    for line in sql.splitlines():
        match = _PARAM_DEFAULT_RE.match(line)
        if match:
            values.append(f"{match.group(1)}={match.group(2).strip()}")
    return _parse_params(values)


def _parse_params(values: list[str]) -> dict[str, object]:
    params: dict[str, object] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid --param value '{value}'. Expected NAME=VALUE.")
        name, raw = value.split("=", 1)
        name = name.strip()
        if name.startswith(":"):
            name = name[1:]
        if not name:
            raise ValueError(f"Invalid --param value '{value}'. Parameter name is empty.")
        params[name] = _coerce_param_value(raw)
    return params


def _coerce_param_value(value: str) -> object:
    lower = value.lower()
    if lower in {"null", "none"}:
        return None
    if lower in {"true", "yes", "on"}:
        return True
    if lower in {"false", "no", "off"}:
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _is_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_partial_bin_directive(text: str) -> dict[str, str]:
    """Parse a partial-bin directive.

    Shorthand:
      -- @partial_bin covered_text_bin

    Full form:
      -- @partial_bin column=covered_text_bin group_by=semantic_tag
    """
    result = {
        "enabled_param": "partial_binning",
        "variants_column": "covered_text_variants",
        "count_column": "annotation_count",
    }
    parts = text.split()
    if len(parts) == 1 and "=" not in parts[0]:
        result["column"] = parts[0]
        return result
    for part in parts:
        if "=" not in part:
            raise ValueError(f"Invalid directive part '{part}'. Expected KEY=VALUE or shorthand column name.")
        key, value = part.split("=", 1)
        result[key.strip()] = value.strip()
    if "column" not in result:
        raise ValueError("@partial_bin requires a column name.")
    return result


def _partial_bin_directives(sql: str) -> list[dict[str, str]]:
    directives = []
    for line in sql.splitlines():
        match = _PARTIAL_BIN_RE.match(line)
        if match:
            directives.append(_parse_partial_bin_directive(match.group(1)))
    return directives


def _post_limit_param(sql: str) -> str | None:
    for line in sql.splitlines():
        match = _POST_LIMIT_RE.match(line)
        if match:
            return match.group(1)
    return None


def _sort_by_param(sql: str) -> str | None:
    for line in sql.splitlines():
        match = _SORT_BY_RE.match(line)
        if match:
            return match.group(1)
    return None


def _apply_post_processing(rows: list[dict], sql: str, params: dict[str, object]) -> list[dict]:
    for directive in _partial_bin_directives(sql):
        enabled_param = directive.get("enabled_param")
        if enabled_param and not _is_truthy(params.get(enabled_param)):
            continue
        column = directive["column"]
        variants_column = directive.get("variants_column")
        count_column = directive.get("count_column", "annotation_count")
        group_by = [value for value in directive.get("group_by", "").split(",") if value]
        if not group_by and rows:
            group_by = [
                key
                for key in rows[0].keys()
                if key not in {column, variants_column, count_column}
            ]
        rows = _partial_bin_rows(
            rows,
            column=column,
            group_by=group_by,
            variants_column=variants_column,
            count_column=count_column,
            match_mode=directive.get("match", "boundary"),
        )
    sort_param = _sort_by_param(sql)
    if sort_param is not None:
        rows = _sort_rows(rows, params.get(sort_param, "count"))

    limit_param = _post_limit_param(sql)
    if limit_param is not None:
        limit = params.get(limit_param)
        if isinstance(limit, int) and limit >= 0:
            rows = rows[:limit]
    return rows


def _partial_bin_rows(
    rows: list[dict], *, column: str, group_by: list[str], variants_column: str | None, count_column: str, match_mode: str
) -> list[dict]:
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        grouped.setdefault(tuple(row.get(col) for col in group_by), []).append(row)

    merged_rows = []
    for group_rows in grouped.values():
        bin_values = sorted(
            {row.get(column) for row in group_rows if row.get(column) is not None},
            key=lambda value: (len(str(value)), str(value)),
        )
        merged: dict[str, dict] = {}
        variant_sets: dict[str, set[str]] = {}
        for row in group_rows:
            source = row.get(column)
            target = _partial_bin_target(str(source), bin_values, match_mode=match_mode) if source is not None else source
            key = "<NULL-BIN>" if target is None else str(target)
            if key not in merged:
                merged_row = dict(row)
                merged_row[column] = target
                merged_row[count_column] = 0
                merged[key] = merged_row
                variant_sets[key] = set()
            merged[key][count_column] += int(row.get(count_column) or 0)
            if variants_column:
                _add_variants(variant_sets[key], row.get(variants_column))
        for key, row in merged.items():
            if variants_column:
                row[variants_column] = ",".join(sorted(variant_sets[key], key=str.lower))
            merged_rows.append(row)

    return sorted(merged_rows, key=lambda row: (-int(row.get(count_column) or 0), *(str(row.get(col) or "") for col in row.keys())))


def _sort_rows(rows: list[dict], order_value: object) -> list[dict]:
    if not rows:
        return rows
    order = str(order_value or "count").strip().lower()
    alias_specs = {
        "count": "-annotation_count,semantic_tag,sctid,covered_text_bin",
        "annotation_count": "-annotation_count,semantic_tag,sctid,covered_text_bin",
        "semantic_tag": "semantic_tag,-annotation_count,sctid,covered_text_bin",
        "covered_text": "covered_text_bin,-annotation_count,semantic_tag,sctid",
        "covered_text_bin": "covered_text_bin,-annotation_count,semantic_tag,sctid",
        "semantic_tag_covered_text": "semantic_tag,covered_text_bin,-annotation_count,sctid",
        "sctid": "sctid,-annotation_count,semantic_tag,covered_text_bin",
        "fsn": "fsn,-annotation_count,semantic_tag,sctid,covered_text_bin",
    }
    spec = alias_specs.get(order, order)
    terms = [term.strip() for term in spec.split(",") if term.strip()]
    sorted_rows = list(rows)
    for term in reversed(terms):
        descending = term.startswith("-")
        column = term[1:] if descending else term.lstrip("+")
        if column not in rows[0]:
            continue
        sorted_rows.sort(key=lambda row, col=column: _sort_value(row.get(col)), reverse=descending)
    return sorted_rows


def _sort_value(value: object) -> tuple[int, object]:
    if value is None:
        return (1, "")
    if isinstance(value, (int, float)):
        return (0, value)
    return (0, str(value).lower())


def _partial_bin_target(source: str, candidates: list[object], *, match_mode: str) -> str:
    matches = [
        str(candidate)
        for candidate in candidates
        if _candidate_matches_source(str(candidate), source, match_mode=match_mode)
    ]
    if not matches:
        return source
    return sorted(matches, key=lambda value: (len(value), value))[0]


def _candidate_matches_source(candidate: str, source: str, *, match_mode: str) -> bool:
    if match_mode == "substring":
        return candidate.lower() in source.lower()
    if match_mode != "boundary":
        raise ValueError(f"Unsupported partial-bin match mode: {match_mode}")
    return re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", source, flags=re.IGNORECASE) is not None


def _add_variants(variants: set[str], value: object) -> None:
    if value is None:
        return
    for part in str(value).split(","):
        if part:
            variants.add(part)


def _format_table_value(value) -> str:
    if value is None:
        return "<null>"
    return str(value).replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")


def _info_lines(sql_file: Path, rows: list[dict], sql: str, params: dict[str, object]) -> list[str]:
    lines = [
        f"Query: {sql_file}",
        f"Rows shown: {len(rows)}",
    ]
    if "n" in params:
        limit_kind = "post-processing limit" if _post_limit_param(sql) == "n" else "SQL/query limit"
        lines.append(f"Limit n: {params['n']} ({limit_kind})")
    if params:
        rendered = ", ".join(f"{key}={_format_table_value(value)}" for key, value in sorted(params.items()))
        lines.append(f"Parameters: {rendered}")
    return lines


def _print_info(lines: list[str], *, stream) -> None:
    for line in lines:
        print(f"# {line}", file=stream)


def _print_table(rows: list[dict]) -> None:
    if not rows:
        print("(no rows)")
        return

    columns = list(rows[0].keys())
    widths = {
        column: max(len(str(column)), *(_format_table_value(row[column]).__len__() for row in rows))
        for column in columns
    }
    header = "  ".join(column.ljust(widths[column]) for column in columns)
    separator = "  ".join("-" * widths[column] for column in columns)
    print(header)
    print(separator)
    for row in rows:
        print("  ".join(_format_table_value(row[column]).ljust(widths[column]) for column in columns))


def _print_csv(rows: list[dict]) -> None:
    if not rows:
        return
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument(
    "database",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.argument(
    "sql_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(("table", "json", "csv")),
    default="table",
    show_default=True,
    help="Output format for result rows.",
)
@click.option(
    "--param",
    "param_values",
    multiple=True,
    metavar="NAME=VALUE",
    help="Bind a named SQL parameter. Can be repeated. Example: --param n=20 for SQL 'limit :n'.",
)
@click.option(
    "--no-info",
    is_flag=True,
    help="Do not print query metadata. By default table metadata goes to stdout; JSON/CSV metadata goes to stderr.",
)
def cli(
    database: Path,
    sql_file: Path,
    output_format: str,
    param_values: tuple[str, ...],
    no_info: bool,
) -> None:
    """Run SQL_FILE against DATABASE."""
    sql = sql_file.read_text(encoding="utf-8")
    try:
        params = _parse_sql_param_defaults(sql)
        params.update(_parse_params(list(param_values)))
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--param") from exc

    try:
        with sqlite3.connect(database) as con:
            con.row_factory = sqlite3.Row
            cursor = con.execute(sql, params)
            rows = _rows_as_dicts(cursor.fetchall()) if cursor.description else []
    except sqlite3.Error as exc:
        raise click.ClickException(f"SQLite error: {exc}") from exc

    try:
        rows = _apply_post_processing(rows, sql, params)
    except (KeyError, ValueError) as exc:
        raise click.ClickException(f"Post-processing error: {exc}") from exc

    if not no_info:
        info = _info_lines(sql_file, rows, sql, params)
        _print_info(info, stream=sys.stdout if output_format == "table" else sys.stderr)

    if output_format == "json":
        click.echo(json.dumps(rows, ensure_ascii=False, indent=2))
    elif output_format == "csv":
        _print_csv(rows)
    else:
        _print_table(rows)


if __name__ == "__main__":
    cli()
