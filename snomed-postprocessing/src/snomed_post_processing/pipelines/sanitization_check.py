"""Sanitization-check pipeline that creates suggestion reports."""

from __future__ import annotations

import logging
import pathlib

import click

from ..cli import set_log_level
from ..findings_io import read_critical_findings_json
from ..sanitization import (
    SanitizationResolver,
    apply_semantic_bm25_fallback,
    write_sanitization_markdown_report,
)


def run_sanitization_check(
    lists_path: pathlib.Path,
    critical_findings: pathlib.Path,
    output: pathlib.Path,
    association_type: tuple[str, ...],
    semantic_bm25_fallback: bool,
    blacklist_suggestions: bool,
    bm25_min_score: float,
    bm25_min_lexical_score: float,
    bm25_max_candidates: int,
    log_level: str,
):
    """Create sanitization suggestions from a CriticalFindings JSON artifact."""
    set_log_level(log_level)
    if blacklist_suggestions and not semantic_bm25_fallback:
        raise click.UsageError("--blacklist-suggestions requires --semantic-bm25-fallback.")

    findings = read_critical_findings_json(critical_findings)
    resolver = SanitizationResolver(
        lists_path,
        allowed_association_types=association_type,
    )
    suggestions = resolver.suggest_all(findings)
    if semantic_bm25_fallback:
        suggestions = apply_semantic_bm25_fallback(
            suggestions,
            lists_path,
            min_score=bm25_min_score,
            min_lexical_score=bm25_min_lexical_score,
            max_candidates=bm25_max_candidates,
            allow_blacklist_findings=blacklist_suggestions,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as sanitization_report:
        write_sanitization_markdown_report(suggestions, sanitization_report)
    logging.info(f"Sanitization suggestion report written to '{output.resolve()}'.")
