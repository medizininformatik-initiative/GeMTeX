"""Sanitization-check pipeline that creates suggestion reports."""

from __future__ import annotations

import logging
import pathlib

import click
import h5py

from ..cli import set_log_level
from ..findings_io import read_critical_findings_json
from ..hdf5_handling.policy import read_blacklist_rule_file, resolve_blacklist_rule_indices
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
    use_snogit_cache: pathlib.Path | None = None,
    activate_historical_ancestor_fallback: bool = False,
    ancestor_max_distance: int | None = None,
    ancestor_max_relative_distance: float | None = None,
    target_view: str = "policy",
    enforce_embedded_blacklist: bool = False,
    custom_blacklist: pathlib.Path | None = None,
    log_level: str = "INFO",
):
    """Create sanitization suggestions from a CriticalFindings JSON artifact."""
    set_log_level(log_level)
    if blacklist_suggestions and not semantic_bm25_fallback:
        raise click.UsageError("--blacklist-suggestions requires --semantic-bm25-fallback.")
    target_view = target_view.lower()
    if target_view not in {"policy", "release"}:
        raise click.UsageError("--target-view must be one of: policy, release.")
    if custom_blacklist is not None and target_view != "release":
        raise click.UsageError("--custom-blacklist can only be used with --target-view release.")
    if use_snogit_cache is not None and not semantic_bm25_fallback:
        raise click.UsageError("--use-snogit-cache requires --semantic-bm25-fallback.")

    runtime_blacklist_indices = frozenset()
    if custom_blacklist is not None:
        runtime_blacklist_rules = read_blacklist_rule_file(custom_blacklist)
        with h5py.File(lists_path, "r") as h5_file:
            runtime_blacklist_indices = resolve_blacklist_rule_indices(
                h5_file,
                runtime_blacklist_rules,
            )
        logging.info(
            "Resolved custom release blacklist '%s' to %d concept(s).",
            custom_blacklist,
            len(runtime_blacklist_indices),
        )

    findings = read_critical_findings_json(critical_findings)
    resolver = SanitizationResolver(
        lists_path,
        allowed_association_types=association_type,
        activate_historical_ancestor_fallback=activate_historical_ancestor_fallback,
        ancestor_max_distance=ancestor_max_distance,
        ancestor_max_relative_distance=ancestor_max_relative_distance,
        target_view=target_view,
        release_exclude_blacklist=enforce_embedded_blacklist,
        runtime_blacklist_indices=runtime_blacklist_indices,
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
            snogit_sidecar_path=use_snogit_cache,
            target_view=target_view,
            release_exclude_blacklist=enforce_embedded_blacklist,
            runtime_blacklist_indices=runtime_blacklist_indices,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as sanitization_report:
        write_sanitization_markdown_report(suggestions, sanitization_report)
    logging.info(f"Sanitization suggestion report written to '{output.resolve()}'.")
