#!/usr/bin/env python3
"""Compatibility wrapper for the Click-based SQLite query runner.

Prefer the installed project script:

  uv run sql-query DB.sqlite queries/annotation-store/query.sql
"""

from snomed_post_processing.cli.query_runner import cli


if __name__ == "__main__":
    cli()
