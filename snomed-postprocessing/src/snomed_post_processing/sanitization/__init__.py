"""Sanitization suggestion utilities.

This package contains conservative sanitization phases that resolve structured
``CriticalFinding`` records against SNOMED CT HDF5 data and optionally provide
semantic BM25 fallback suggestions. It does not mutate documents or CAS files.
"""

from __future__ import annotations

from .json_io import (
    read_sanitization_suggestions_json,
    read_sanitization_suggestions_json_with_metadata,
    sanitization_suggestions_json_text,
    sanitization_suggestions_payload,
    sanitization_suggestion_from_dict,
    sanitization_suggestion_to_dict,
    write_sanitization_suggestions_json,
)
from .models import (
    ASSOCIATION_TYPE_DESCRIPTIONS,
    DEFAULT_ALLOWED_ASSOCIATION_TYPES,
    SUPPORTED_ASSOCIATION_TYPES,
    SanitizationCandidate,
    SanitizationStatus,
    SanitizationSuggestion,
    format_association_type_descriptions,
)
from .report import (
    _md,
    _write_grouped_suggestion_table,
    _write_replacement_table,
    _write_unresolved_table,
    write_sanitization_markdown_report,
)
from .resolver import SanitizationResolver, suggest_sanitization
from .semantic_bm25 import (
    SemanticBm25Resolver,
    apply_semantic_bm25_fallback,
    suggest_semantic_bm25,
)
from .semantic_models import SemanticBm25Candidate, SemanticBm25Suggestion

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
    "sanitization_suggestion_to_dict",
    "sanitization_suggestion_from_dict",
    "sanitization_suggestions_payload",
    "write_sanitization_suggestions_json",
    "read_sanitization_suggestions_json",
    "read_sanitization_suggestions_json_with_metadata",
    "sanitization_suggestions_json_text",
    # Backwards-compatible private report helpers.
    "_write_replacement_table",
    "_write_unresolved_table",
    "_write_grouped_suggestion_table",
    "_md",
]
