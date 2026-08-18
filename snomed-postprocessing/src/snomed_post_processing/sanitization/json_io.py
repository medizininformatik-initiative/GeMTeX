"""JSON read/write helpers for sanitization suggestions."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Optional, Sequence, TextIO, Union

from ..findings_io.mapping import critical_finding_from_dict, critical_finding_to_dict
from .models import SanitizationCandidate, SanitizationStatus, SanitizationSuggestion
from .semantic_models import SemanticBm25Candidate, SemanticBm25Suggestion

SCHEMA = "snomed-post-processing.sanitization-suggestions"
SCHEMA_VERSION = 1


def sanitization_candidate_to_dict(candidate: SanitizationCandidate) -> dict[str, Any]:
    return {
        "type": "structured",
        "code": candidate.code,
        "fsn": candidate.fsn,
        "association_type": candidate.association_type,
        "active": bool(candidate.active),
        "in_whitelist": bool(candidate.in_whitelist),
        "in_blacklist": bool(candidate.in_blacklist),
        "effective_time": candidate.effective_time,
        "refset_id": candidate.refset_id,
    }


def semantic_bm25_candidate_to_dict(candidate: SemanticBm25Candidate) -> dict[str, Any]:
    return {
        "type": "semantic_bm25",
        "code": candidate.code,
        "fsn": candidate.fsn,
        "score": float(candidate.score),
        "lexical_score": float(candidate.lexical_score),
        "semantic_tag": candidate.semantic_tag,
        "active": bool(candidate.active),
        "in_whitelist": bool(candidate.in_whitelist),
        "in_blacklist": bool(candidate.in_blacklist),
    }


def candidate_to_dict(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, SemanticBm25Candidate):
        return semantic_bm25_candidate_to_dict(candidate)
    return sanitization_candidate_to_dict(candidate)


def candidate_from_dict(data: dict[str, Any]) -> SanitizationCandidate | SemanticBm25Candidate:
    if data.get("type") == "semantic_bm25" or "score" in data:
        return SemanticBm25Candidate(
            code=str(data["code"]),
            fsn=str(data.get("fsn", "")),
            score=float(data.get("score", 0.0)),
            lexical_score=float(data.get("lexical_score", 0.0)),
            semantic_tag=None if data.get("semantic_tag") is None else str(data.get("semantic_tag")),
            active=bool(data.get("active", False)),
            in_whitelist=bool(data.get("in_whitelist", False)),
            in_blacklist=bool(data.get("in_blacklist", False)),
        )
    return SanitizationCandidate(
        code=str(data["code"]),
        fsn=None if data.get("fsn") is None else str(data.get("fsn")),
        association_type=str(data.get("association_type", "")),
        active=bool(data.get("active", False)),
        in_whitelist=bool(data.get("in_whitelist", False)),
        in_blacklist=bool(data.get("in_blacklist", False)),
        effective_time=None if data.get("effective_time") is None else str(data.get("effective_time")),
        refset_id=None if data.get("refset_id") is None else str(data.get("refset_id")),
    )


def sanitization_suggestion_to_dict(suggestion: SanitizationSuggestion | SemanticBm25Suggestion) -> dict[str, Any]:
    payload = {
        "type": "semantic_bm25" if isinstance(suggestion, SemanticBm25Suggestion) else "structured",
        "finding": critical_finding_to_dict(suggestion.finding),
        "status": suggestion.status.value if hasattr(suggestion.status, "value") else str(suggestion.status),
        "replacement_code": suggestion.replacement_code,
        "replacement_fsn": suggestion.replacement_fsn,
        "association_type": suggestion.association_type,
        "reason": suggestion.reason,
        "candidate_count": int(suggestion.candidate_count),
        "candidates": [candidate_to_dict(candidate) for candidate in suggestion.candidates],
    }
    if isinstance(suggestion, SemanticBm25Suggestion):
        payload["score"] = float(suggestion.score)
        payload["context_candidates"] = [
            sanitization_candidate_to_dict(candidate)
            for candidate in suggestion.context_candidates
        ]
    else:
        payload["context_candidates"] = []
    return payload


def sanitization_suggestion_from_dict(data: dict[str, Any]) -> SanitizationSuggestion | SemanticBm25Suggestion:
    status = SanitizationStatus(str(data["status"]))
    candidates = tuple(candidate_from_dict(candidate) for candidate in data.get("candidates", []))
    context_candidates = tuple(
        candidate_from_dict(candidate) for candidate in data.get("context_candidates", [])
    )
    is_semantic = data.get("type") == "semantic_bm25" or "score" in data or any(
        isinstance(candidate, SemanticBm25Candidate) for candidate in candidates
    )
    if is_semantic:
        return SemanticBm25Suggestion(
            finding=critical_finding_from_dict(data["finding"]),
            status=status,
            replacement_code=data.get("replacement_code"),
            replacement_fsn=data.get("replacement_fsn"),
            association_type=data.get("association_type"),
            reason=str(data.get("reason", "")),
            score=float(data.get("score", 0.0)),
            candidate_count=int(data.get("candidate_count", len(candidates))),
            candidates=tuple(candidate for candidate in candidates if isinstance(candidate, SemanticBm25Candidate)),
            context_candidates=tuple(candidate for candidate in context_candidates if isinstance(candidate, SanitizationCandidate)),
        )
    return SanitizationSuggestion(
        finding=critical_finding_from_dict(data["finding"]),
        status=status,
        replacement_code=data.get("replacement_code"),
        replacement_fsn=data.get("replacement_fsn"),
        association_type=data.get("association_type"),
        reason=str(data.get("reason", "")),
        candidate_count=int(data.get("candidate_count", len(candidates))),
        candidates=tuple(candidate for candidate in candidates if isinstance(candidate, SanitizationCandidate)),
    )


def sanitization_suggestions_payload(
    suggestions: Sequence[SanitizationSuggestion | SemanticBm25Suggestion],
    *,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "metadata": metadata or {},
        "suggestions": [sanitization_suggestion_to_dict(suggestion) for suggestion in suggestions],
    }


def write_sanitization_suggestions_json(
    suggestions: Sequence[SanitizationSuggestion | SemanticBm25Suggestion],
    output: Union[str, Path, TextIO],
    *,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    payload = sanitization_suggestions_payload(suggestions, metadata=metadata)
    if hasattr(output, "write"):
        json.dump(payload, output, ensure_ascii=False, indent=2)
        return
    with Path(output).open("w", encoding="utf-8") as fi:
        json.dump(payload, fi, ensure_ascii=False, indent=2)


def _read_sanitization_suggestions_payload(input_: Union[str, Path, TextIO]) -> dict[str, Any]:
    if hasattr(input_, "read"):
        payload = json.load(input_)
    else:
        with Path(input_).open("r", encoding="utf-8") as fi:
            payload = json.load(fi)
    if not isinstance(payload, dict):
        raise ValueError("Sanitization suggestions JSON must contain an object payload.")
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"Unsupported sanitization suggestions schema: {payload.get('schema')!r}.")
    if int(payload.get("schema_version", 0)) != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported sanitization suggestions schema version: {payload.get('schema_version')!r}."
        )
    suggestions = payload.get("suggestions")
    if not isinstance(suggestions, list):
        raise ValueError("Sanitization suggestions JSON payload must contain a suggestions list.")
    return payload


def read_sanitization_suggestions_json(input_: Union[str, Path, TextIO]) -> list[SanitizationSuggestion | SemanticBm25Suggestion]:
    payload = _read_sanitization_suggestions_payload(input_)
    return [sanitization_suggestion_from_dict(suggestion) for suggestion in payload["suggestions"]]


def read_sanitization_suggestions_json_with_metadata(
    input_: Union[str, Path, TextIO],
) -> tuple[list[SanitizationSuggestion | SemanticBm25Suggestion], dict[str, Any]]:
    payload = _read_sanitization_suggestions_payload(input_)
    suggestions = [sanitization_suggestion_from_dict(suggestion) for suggestion in payload["suggestions"]]
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return suggestions, metadata


def sanitization_suggestions_json_text(
    suggestions: Sequence[SanitizationSuggestion | SemanticBm25Suggestion],
    *,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    return json.dumps(
        sanitization_suggestions_payload(suggestions, metadata=metadata),
        ensure_ascii=False,
        indent=2,
    )
