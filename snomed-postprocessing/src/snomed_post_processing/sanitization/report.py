"""Markdown reporting for sanitization suggestions."""

from __future__ import annotations

from typing import Sequence, TextIO

from .models import SanitizationStatus, SanitizationSuggestion


def write_sanitization_markdown_report(
    suggestions: Sequence[SanitizationSuggestion],
    output_file: TextIO,
    title: str = "Sanitization Suggestions",
):
    """Write a standalone Markdown report for sanitization suggestions."""
    output_file.write(f"# {title}\n\n")
    output_file.write(
        "This report is suggestion-only. It is generated from structured critical findings, SNOMED CT historical associations, and optional fallback mechanisms; it does not modify source documents.\n\n"
    )
    output_file.write("## Summary\n\n")
    output_file.write("| Status | Count |\n")
    output_file.write("| --: | --: |\n")
    counts: dict[SanitizationStatus, int] = {status: 0 for status in SanitizationStatus}
    for suggestion in suggestions:
        counts[suggestion.status] = counts.get(suggestion.status, 0) + 1
    for status, count in counts.items():
        if count:
            output_file.write(f"| {status.value} | {count} |\n")
    if not suggestions:
        output_file.write("| no_findings | 0 |\n")
    output_file.write("\n")

    actionable = [suggestion for suggestion in suggestions if not suggestion.finding.ignored]
    replacement_suggestions = [
        suggestion for suggestion in actionable if suggestion.replacement_code is not None
    ]
    unresolved = [
        suggestion for suggestion in actionable if suggestion.replacement_code is None
    ]
    ignored = [suggestion for suggestion in suggestions if suggestion.finding.ignored]
    _write_replacement_table(output_file, "Replacement suggestions", replacement_suggestions)
    _write_unresolved_table(output_file, "Findings without replacement", unresolved)
    _write_unresolved_table(output_file, "Ignored findings", ignored)


def _write_replacement_table(
    output_file: TextIO,
    heading: str,
    suggestions: Sequence[SanitizationSuggestion],
):
    _write_grouped_suggestion_table(
        output_file,
        heading,
        suggestions,
        columns=(
            "Document",
            "Source Code",
            "Covered Text",
            "Original FSN",
            "Status",
            "Replacement Code",
            "Replacement FSN",
            "Association",
            "Candidates / context",
        ),
        row_builder=lambda suggestion: (
            suggestion.finding.document,
            suggestion.finding.code or "",
            suggestion.finding.covered_text,
            suggestion.finding.fsn or "",
            suggestion.status.value,
            suggestion.replacement_code or "",
            suggestion.replacement_fsn or "",
            suggestion.association_type or "",
            _format_candidates(suggestion),
        ),
    )


def _write_unresolved_table(
    output_file: TextIO,
    heading: str,
    suggestions: Sequence[SanitizationSuggestion],
):
    _write_grouped_suggestion_table(
        output_file,
        heading,
        suggestions,
        columns=("Document", "Source Code", "Covered Text", "Original FSN", "Status", "Candidates / context"),
        row_builder=lambda suggestion: (
            suggestion.finding.document,
            suggestion.finding.code or "",
            suggestion.finding.covered_text,
            suggestion.finding.fsn or "",
            suggestion.status.value,
            _format_candidates(suggestion),
        ),
    )


def _write_grouped_suggestion_table(
    output_file: TextIO,
    heading: str,
    suggestions: Sequence[SanitizationSuggestion],
    columns: tuple[str, ...],
    row_builder,
):
    output_file.write(f"## {heading}\n\n")
    if not suggestions:
        output_file.write("_No entries._\n\n")
        return

    for annotator in sorted({suggestion.finding.annotator for suggestion in suggestions}):
        output_file.write(f"### {_md(annotator)}\n\n")
        output_file.write("| " + " | ".join(columns) + " |\n")
        output_file.write("| " + " | ".join(["--:"] * len(columns)) + " |\n")
        for suggestion in suggestions:
            if suggestion.finding.annotator != annotator:
                continue
            output_file.write(
                "| "
                + " | ".join(_md(value) for value in row_builder(suggestion))
                + " |\n"
            )
        output_file.write("\n")


def _format_candidates(suggestion) -> str:
    parts = []
    context_candidates = getattr(suggestion, "context_candidates", ()) or ()
    if context_candidates:
        parts.append(
            "Nearest rejected ancestor: "
            + _format_candidate_list(context_candidates)
        )
    candidates = getattr(suggestion, "candidates", ()) or ()
    if candidates:
        label = "BM25 candidates" if suggestion.association_type == "BM25" else "Candidates"
        parts.append(label + ": " + _format_candidate_list(candidates))
    return " / ".join(parts)


def _format_candidate_list(candidates) -> str:
    return "; ".join(_format_candidate(candidate) for candidate in candidates)


def _format_candidate(candidate) -> str:
    text = f"{candidate.code} — {candidate.fsn or ''}"
    if getattr(candidate, "source", "snomed_fsn") == "snogit":
        matched_term = getattr(candidate, "matched_term", None)
        if matched_term:
            text += f" [SNOGIT: {matched_term}]"
        else:
            text += " [SNOGIT]"
    return text


def _md(value: str) -> str:
    return (
        str(value)
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("|", "\\|")
    )
