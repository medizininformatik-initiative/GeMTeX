"""Sanitization suggestion utilities.

This module contains the first, conservative sanitization phase: resolve
structured ``CriticalFinding`` records against the compact SNOMED HDF5 layout
and return suggestion objects. It does not mutate documents or CAS files.
"""

from __future__ import annotations

import dataclasses
import enum
import pathlib
from typing import Optional, Sequence, TextIO, Union

import h5py
import numpy as np

from ..uima_processing import CriticalFinding

ASSOCIATION_TYPE_DESCRIPTIONS = {
    "SAME_AS": "Source concept is considered equivalent to the target concept.",
    "REPLACED_BY": "Source concept was retired and replaced by the target concept.",
    "POSSIBLY_EQUIVALENT_TO": "Source concept may be equivalent to the target concept; manual review is recommended.",
    "WAS_A": "Source concept used to be classified as the target concept; usually broader/less exact.",
    "MOVED_TO": "Concept was moved to another namespace/module and points to its new target.",
    "MOVED_FROM": "Inverse move association; usually not useful for forward replacement suggestions.",
    "ALTERNATIVE": "Alternative target concept exists, but equivalence is not guaranteed.",
}
SUPPORTED_ASSOCIATION_TYPES = tuple(ASSOCIATION_TYPE_DESCRIPTIONS.keys())
DEFAULT_ALLOWED_ASSOCIATION_TYPES = ("SAME_AS", "REPLACED_BY")


def format_association_type_descriptions() -> str:
    return "\n".join(
        f"- {association_type}: {description}"
        for association_type, description in ASSOCIATION_TYPE_DESCRIPTIONS.items()
    )


class SanitizationStatus(str, enum.Enum):
    HISTORICAL_ASSOCIATION_REPLACEMENT = "historical_association_replacement"
    SEMANTIC_BM25_REPLACEMENT = "semantic_bm25_replacement"
    AMBIGUOUS_REPLACEMENT = "ambiguous_replacement"
    NO_POLICY_ACCEPTABLE_CANDIDATE = "no_policy_acceptable_candidate"
    NO_HISTORICAL_ASSOCIATION = "no_historical_association"
    BLACKLISTED_NO_AUTO_SANITIZATION = "blacklisted_no_auto_sanitization"
    NO_REPLACEMENT = "no_replacement"


@dataclasses.dataclass(frozen=True)
class SanitizationCandidate:
    code: str
    fsn: Optional[str]
    association_type: str
    active: bool
    in_whitelist: bool
    in_blacklist: bool
    effective_time: Optional[str] = None
    refset_id: Optional[str] = None

    @property
    def policy_acceptable(self) -> bool:
        return self.active and self.in_whitelist and not self.in_blacklist


@dataclasses.dataclass(frozen=True)
class SanitizationSuggestion:
    finding: CriticalFinding
    status: SanitizationStatus
    replacement_code: Optional[str] = None
    replacement_fsn: Optional[str] = None
    association_type: Optional[str] = None
    reason: str = ""
    candidate_count: int = 0
    candidates: tuple[SanitizationCandidate, ...] = ()


class SanitizationResolver:
    """Resolve ``CriticalFinding`` objects against a compact SNOMED HDF5 file."""

    def __init__(
        self,
        hdf5_path: Union[str, pathlib.Path],
        allowed_association_types: Sequence[str] = DEFAULT_ALLOWED_ASSOCIATION_TYPES,
    ):
        self.hdf5_path = pathlib.Path(hdf5_path)
        self.allowed_association_types = frozenset(allowed_association_types)
        self._load()

    def _load(self):
        with h5py.File(self.hdf5_path, "r") as h5_file:
            _require_groups(h5_file)
            self.codes = tuple(_decode_array(h5_file["concepts/codes"][:]))
            self.fsn = tuple(_decode_array(h5_file["concepts/fsn"][:]))
            self.active = np.asarray(h5_file["concepts/active"][:], dtype=bool)
            self.code_to_index = {code: idx for idx, code in enumerate(self.codes)}

            self.whitelist_indices = _read_policy_indices(h5_file, "whitelist")
            self.blacklist_indices = _read_policy_indices(h5_file, "blacklist")

            hist = h5_file["historical_associations"]
            self.association_source_index = np.asarray(hist["source_index"][:], dtype=np.int64)
            self.association_target_index = np.asarray(hist["target_index"][:], dtype=np.int64)
            self.association_type_id = np.asarray(hist["association_type_id"][:], dtype=np.int64)
            self.association_types = tuple(_decode_array(hist["association_types"][:]))
            self.association_active = np.asarray(hist["active"][:], dtype=bool)
            self.association_effective_time = tuple(_decode_array(hist["effective_time"][:]))
            self.association_refset_id = tuple(_decode_array(hist["refset_id"][:]))

    def suggest(self, finding: CriticalFinding) -> SanitizationSuggestion:
        if finding.ignored:
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.NO_REPLACEMENT,
                reason="ignored findings are informational and are not sanitized",
            )
        if finding.list_type == "blacklist":
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.BLACKLISTED_NO_AUTO_SANITIZATION,
                reason="automatic sanitization for blacklist findings is disabled",
            )
        if finding.list_type != "whitelist":
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.NO_REPLACEMENT,
                reason=f"unsupported finding list type: {finding.list_type}",
            )
        if not finding.code:
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.NO_REPLACEMENT,
                reason="finding has no SNOMED CT code",
            )

        source_index = self.code_to_index.get(finding.code)
        if source_index is None:
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.NO_HISTORICAL_ASSOCIATION,
                reason="source concept is not present in /concepts",
            )

        candidates = self._historical_candidates(source_index)
        if not candidates:
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.NO_HISTORICAL_ASSOCIATION,
                reason="no active allowed historical association found for source concept",
            )

        acceptable = [candidate for candidate in candidates if candidate.policy_acceptable]
        if not acceptable:
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.NO_POLICY_ACCEPTABLE_CANDIDATE,
                reason="historical associations exist, but no candidate satisfies active/whitelist/blacklist policy",
                candidate_count=len(candidates),
                candidates=tuple(candidates),
            )

        unique_targets = {(candidate.code, candidate.association_type) for candidate in acceptable}
        if len({candidate.code for candidate in acceptable}) > 1:
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.AMBIGUOUS_REPLACEMENT,
                reason="multiple policy-acceptable replacement targets found",
                candidate_count=len(acceptable),
                candidates=tuple(acceptable),
            )

        chosen = acceptable[0]
        if len(unique_targets) > 1:
            # Same replacement code through multiple association types is still
            # deterministic, but expose the ambiguity in the candidate list.
            association_type = ",".join(sorted({candidate.association_type for candidate in acceptable}))
        else:
            association_type = chosen.association_type
        return SanitizationSuggestion(
            finding=finding,
            status=SanitizationStatus.HISTORICAL_ASSOCIATION_REPLACEMENT,
            replacement_code=chosen.code,
            replacement_fsn=chosen.fsn,
            association_type=association_type,
            reason="single policy-acceptable historical association replacement found",
            candidate_count=len(acceptable),
            candidates=tuple(acceptable),
        )

    def suggest_all(self, findings: Sequence[CriticalFinding]) -> list[SanitizationSuggestion]:
        return [self.suggest(finding) for finding in findings]

    def _historical_candidates(self, source_index: int) -> list[SanitizationCandidate]:
        row_indices = np.where(
            (self.association_source_index == source_index) & self.association_active
        )[0]
        candidates: list[SanitizationCandidate] = []
        for row_index in row_indices:
            association_type = self.association_types[int(self.association_type_id[row_index])]
            if association_type not in self.allowed_association_types:
                continue
            target_index = int(self.association_target_index[row_index])
            if target_index < 0 or target_index >= len(self.codes):
                continue
            candidates.append(
                SanitizationCandidate(
                    code=self.codes[target_index],
                    fsn=self.fsn[target_index] or None,
                    association_type=association_type,
                    active=bool(self.active[target_index]),
                    in_whitelist=target_index in self.whitelist_indices,
                    in_blacklist=target_index in self.blacklist_indices,
                    effective_time=self.association_effective_time[row_index] or None,
                    refset_id=self.association_refset_id[row_index] or None,
                )
            )
        return candidates


def suggest_sanitization(
    finding: CriticalFinding,
    hdf5_path: Union[str, pathlib.Path],
    allowed_association_types: Sequence[str] = DEFAULT_ALLOWED_ASSOCIATION_TYPES,
) -> SanitizationSuggestion:
    return SanitizationResolver(hdf5_path, allowed_association_types).suggest(finding)


def write_sanitization_markdown_report(
    suggestions: Sequence[SanitizationSuggestion],
    output_file: TextIO,
    title: str = "Sanitization Suggestions",
):
    """Write a standalone Markdown report for sanitization suggestions."""
    output_file.write(f"# {title}\n\n")
    output_file.write(
        "This report is suggestion-only. It is generated from structured critical findings and SNOMED CT historical associations; it does not modify source documents.\n\n"
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
            "Status",
            "Replacement Code",
            "Replacement FSN",
            "Association",
        ),
        row_builder=lambda suggestion: (
            suggestion.finding.document,
            suggestion.finding.code or "",
            suggestion.finding.covered_text,
            suggestion.status.value,
            suggestion.replacement_code or "",
            suggestion.replacement_fsn or "",
            suggestion.association_type or "",
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
        columns=("Document", "Source Code", "Covered Text", "Status"),
        row_builder=lambda suggestion: (
            suggestion.finding.document,
            suggestion.finding.code or "",
            suggestion.finding.covered_text,
            suggestion.status.value,
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


def _md(value: str) -> str:
    return (
        str(value)
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("|", "\\|")
    )


def _require_groups(h5_file: h5py.File):
    required_paths = [
        "concepts/codes",
        "concepts/fsn",
        "concepts/active",
        "policy_views/whitelist/0/concept_index",
        "policy_views/blacklist/0/concept_index",
        "historical_associations/source_index",
        "historical_associations/target_index",
        "historical_associations/association_type_id",
        "historical_associations/association_types",
        "historical_associations/effective_time",
        "historical_associations/active",
        "historical_associations/refset_id",
    ]
    missing = [path for path in required_paths if path not in h5_file]
    if missing:
        raise ValueError(
            "HDF5 file is not sanitization-ready; missing compact dataset(s): "
            + ", ".join(missing)
        )


def _read_policy_indices(h5_file: h5py.File, policy: str) -> frozenset[int]:
    return frozenset(int(idx) for idx in h5_file[f"policy_views/{policy}/0/concept_index"][:])


def _decode_array(values) -> list[str]:
    decoded = []
    for value in values:
        if isinstance(value, (bytes, bytearray)):
            decoded.append(value.decode("utf-8"))
        else:
            decoded.append(str(value))
    return decoded


from .semantic_bm25 import (  # noqa: E402  # imported late to avoid circular initialization
    SemanticBm25Candidate,
    SemanticBm25Resolver,
    SemanticBm25Suggestion,
    apply_semantic_bm25_fallback,
    suggest_semantic_bm25,
)

__all__ = [
    "ASSOCIATION_TYPE_DESCRIPTIONS",
    "SUPPORTED_ASSOCIATION_TYPES",
    "DEFAULT_ALLOWED_ASSOCIATION_TYPES",
    "format_association_type_descriptions",
    "SanitizationStatus",
    "SanitizationCandidate",
    "SanitizationSuggestion",
    "SanitizationResolver",
    "suggest_sanitization",
    "write_sanitization_markdown_report",
    "SemanticBm25Candidate",
    "SemanticBm25Resolver",
    "SemanticBm25Suggestion",
    "apply_semantic_bm25_fallback",
    "suggest_semantic_bm25",
]
