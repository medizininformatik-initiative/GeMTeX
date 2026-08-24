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
    build_snogit_sidecar,
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
    use_snogit: bool = False,
    snogit_sidecar: pathlib.Path | None = None,
    snogit_zip: pathlib.Path | None = None,
    write_snogit_sidecar: pathlib.Path | None = None,
    snogit_member: tuple[str, ...] = (),
    activate_historical_ancestor_fallback: bool = False,
    ancestor_max_distance: int | None = None,
    ancestor_max_relative_distance: float | None = None,
    log_level: str = "INFO",
):
    """Create sanitization suggestions from a CriticalFindings JSON artifact."""
    set_log_level(log_level)
    if blacklist_suggestions and not semantic_bm25_fallback:
        raise click.UsageError("--blacklist-suggestions requires --semantic-bm25-fallback.")
    if use_snogit and not semantic_bm25_fallback:
        raise click.UsageError("--use-snogit requires --semantic-bm25-fallback.")
    if use_snogit and snogit_sidecar is None and snogit_zip is None:
        raise click.UsageError("--use-snogit requires --snogit-sidecar or --snogit-zip.")

    findings = read_critical_findings_json(critical_findings)
    resolver = SanitizationResolver(
        lists_path,
        allowed_association_types=association_type,
        activate_historical_ancestor_fallback=activate_historical_ancestor_fallback,
        ancestor_max_distance=ancestor_max_distance,
        ancestor_max_relative_distance=ancestor_max_relative_distance,
    )
    suggestions = resolver.suggest_all(findings)
    snogit_sidecar_path = snogit_sidecar
    if semantic_bm25_fallback and use_snogit and snogit_sidecar_path is None:
        if snogit_zip is None:
            raise click.UsageError("--use-snogit without --snogit-sidecar requires --snogit-zip.")
        snogit_sidecar_path = write_snogit_sidecar or output.with_suffix(".snogit-sidecar.hdf5")
        build_result = build_snogit_sidecar(
            hdf5_path=lists_path,
            snogit_zip_path=snogit_zip,
            output_path=snogit_sidecar_path,
            members=snogit_member or None,
        )
        logging.info(
            "SNOGIT sidecar written to '%s' with %s term row(s).",
            build_result.output_path.resolve(),
            f"{build_result.rows_written:,}",
        )
    if semantic_bm25_fallback:
        suggestions = apply_semantic_bm25_fallback(
            suggestions,
            lists_path,
            min_score=bm25_min_score,
            min_lexical_score=bm25_min_lexical_score,
            max_candidates=bm25_max_candidates,
            allow_blacklist_findings=blacklist_suggestions,
            snogit_sidecar_path=snogit_sidecar_path,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as sanitization_report:
        write_sanitization_markdown_report(suggestions, sanitization_report)
    logging.info(f"Sanitization suggestion report written to '{output.resolve()}'.")
