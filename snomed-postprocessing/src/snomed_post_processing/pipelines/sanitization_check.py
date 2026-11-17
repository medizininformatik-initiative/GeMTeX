"""Sanitization-check pipeline that creates suggestion reports."""

from __future__ import annotations

import logging
import pathlib

import click
import h5py

from ..cli import set_log_level
from ..findings_io import read_critical_findings_json_with_metadata
from ..hdf5_handling.metadata import inspect_hdf5_metadata
from ..hdf5_handling.policy import read_blacklist_rule_file, resolve_blacklist_rule_indices
from ..sanitization import (
    SanitizationResolver,
    apply_semantic_bm25_fallback,
    write_sanitization_markdown_report,
    write_sanitization_suggestions_json,
)
from ..sanitization_context import masked_suggestions_csv


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
    bm25_semantic_tag_boost_percent: float = 10.0,
):
    """Write Markdown, restorable JSON and identity-masked CSV suggestion reports."""
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

    json_output = output.with_suffix(".json")
    csv_output = output.with_suffix(".masked.csv")
    output_paths = {path.resolve() for path in (output, json_output, csv_output)}
    input_paths = {path.resolve() for path in (lists_path, critical_findings, use_snogit_cache, custom_blacklist)
                   if path is not None}
    if len(output_paths) != 3 or output_paths & input_paths:
        raise click.BadParameter("Markdown, JSON and CSV outputs must be distinct and must not overwrite input files.",
                                 param_hint="--output")

    runtime_blacklist_indices = frozenset()
    if custom_blacklist is not None:
        runtime_blacklist_rules = read_blacklist_rule_file(custom_blacklist)
        with h5py.File(lists_path, "r") as h5_file:
            runtime_blacklist_indices = resolve_blacklist_rule_indices(
                h5_file,
                runtime_blacklist_rules,
            )
        logging.info(
            "Resolved custom release exclusion list '%s' to %d concept(s).",
            custom_blacklist,
            len(runtime_blacklist_indices),
        )

    findings, findings_metadata = read_critical_findings_json_with_metadata(critical_findings)
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
            semantic_tag_boost_percent=bm25_semantic_tag_boost_percent,
            allow_blacklist_findings=blacklist_suggestions,
            snogit_sidecar_path=use_snogit_cache,
            target_view=target_view,
            release_exclude_blacklist=enforce_embedded_blacklist,
            runtime_blacklist_indices=runtime_blacklist_indices,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as sanitization_report:
        write_sanitization_markdown_report(suggestions, sanitization_report)
    summary = inspect_hdf5_metadata(lists_path)
    metadata = {
        **findings_metadata,
        "source": "suggest-sanitization",
        "command": "suggest-sanitization",
        "critical_findings_path": str(critical_findings),
        "lists_path": str(lists_path),
        "hdf5_file_name": lists_path.name,
        "hdf5_release_date": summary.concepts_release_date,
        "hdf5_policy_date": summary.concepts_policy_date,
        "hdf5_rf2_view": summary.concepts_rf2_view,
        "finding_count": len(findings),
        "suggestion_count": len(suggestions),
        "settings": {
            "target_view": target_view,
            "enforce_embedded_blacklist": enforce_embedded_blacklist,
            "custom_blacklist_path": str(custom_blacklist) if custom_blacklist is not None else None,
            "custom_blacklist_concepts": len(runtime_blacklist_indices),
            "allowed_association_types": list(association_type),
            "historical_ancestor_fallback": activate_historical_ancestor_fallback,
            "ancestor_max_distance": ancestor_max_distance,
            "ancestor_max_relative_distance": ancestor_max_relative_distance,
            "semantic_bm25_fallback": semantic_bm25_fallback,
            "blacklist_bm25_suggestions": blacklist_suggestions,
            "bm25_min_score": bm25_min_score,
            "bm25_min_lexical_score": bm25_min_lexical_score,
            "bm25_max_candidates": bm25_max_candidates,
            "bm25_semantic_tag_boost_percent": bm25_semantic_tag_boost_percent,
            "bm25_fsn_semantic_tags_excluded": True,
            "snogit_bm25": use_snogit_cache is not None,
            "snogit_cache_path": str(use_snogit_cache) if use_snogit_cache is not None else None,
        },
    }
    write_sanitization_suggestions_json(suggestions, json_output, metadata=metadata)
    csv_output.write_bytes(masked_suggestions_csv(suggestions))
    for path in (output, json_output, csv_output):
        logging.info("Sanitization suggestion report written to '%s'.", path.resolve())
