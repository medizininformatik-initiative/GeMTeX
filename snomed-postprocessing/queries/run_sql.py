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
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


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

    if args.format == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif args.format == "csv":
        _print_csv(rows)
    else:
        _print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
