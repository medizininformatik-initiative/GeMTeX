#!/usr/bin/env python3
"""Run a SQL file against a SQLite database using Python's stdlib sqlite3.

Usage:
  uv run python queries/run_sql.py DB.sqlite queries/annotation-store/query.sql
  uv run python queries/run_sql.py --param n=20 DB.sqlite queries/annotation-store/top_sctids.sql
  uv run python queries/run_sql.py --format json DB.sqlite query.sql
  uv run python queries/run_sql.py --format csv DB.sqlite query.sql > result.csv

SQL files can define default named parameters in comments:
  -- @param n=50
CLI --param values override these defaults.

SQL files can also request optional Python post-processing, e.g.:
  -- @partial_bin covered_text_bin
  -- @post_limit n
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Iterable

_PARAM_DEFAULT_RE = re.compile(r"^\s*--\s*@param\s+([^=\s]+)=(.*)$")
_PARTIAL_BIN_RE = re.compile(r"^\s*--\s*@partial_bin\s+(.*)$")
_POST_LIMIT_RE = re.compile(r"^\s*--\s*@post_limit\s+([^\s]+)\s*$")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a SQL file against a SQLite database.")
    parser.add_argument("database", type=Path, help="SQLite database path.")
    parser.add_argument("sql_file", type=Path, help="SQL file to execute.")
    parser.add_argument(
        "--format",
        choices=("table", "json", "csv"),
        default="table",
        help="Output format for result rows. Default: table.",
    )
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Bind a named SQL parameter. Can be repeated. Example: --param n=20 for SQL 'limit :n'.",
    )
    return parser.parse_args()


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
    return "<null>" if value is None else str(value)


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


def main() -> int:
    args = _parse_args()
    if not args.database.is_file():
        print(f"Database not found: {args.database}", file=sys.stderr)
        return 2
    if not args.sql_file.is_file():
        print(f"SQL file not found: {args.sql_file}", file=sys.stderr)
        return 2

    sql = args.sql_file.read_text(encoding="utf-8")
    try:
        params = _parse_sql_param_defaults(sql)
        params.update(_parse_params(args.param))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        with sqlite3.connect(args.database) as con:
            con.row_factory = sqlite3.Row
            cursor = con.execute(sql, params)
            rows = _rows_as_dicts(cursor.fetchall()) if cursor.description else []
    except sqlite3.Error as exc:
        print(f"SQLite error: {exc}", file=sys.stderr)
        return 1

    try:
        rows = _apply_post_processing(rows, sql, params)
    except (KeyError, ValueError) as exc:
        print(f"Post-processing error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif args.format == "csv":
        _print_csv(rows)
    else:
        _print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
