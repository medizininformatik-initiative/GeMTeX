"""Read-only adapter for existing suggestions JSON; no generation or policy checks."""
from __future__ import annotations

import io
import math
import uuid
from dataclasses import fields

from .state import CandidatePreview, FindingPreview, PreviewState

MAX_SUGGESTIONS_BYTES = 50 * 1024 * 1024


class SuggestionsPreviewError(ValueError):
    """Safe user-facing import error, without embedding uploaded content."""


def _candidates(candidates, finding_id: str, role: str) -> tuple[CandidatePreview, ...]:
    result = []
    rank, group_score = 0, None
    labels = {"code": "SCTID", "fsn": "FSN", "in_whitelist": "In inclusion list",
              "in_blacklist": "In exclusion list"}
    for position, candidate in enumerate(candidates):
        score = getattr(candidate, "score", None)
        # Display the saved order; same competition-rank tolerance as Streamlit.
        # Diagnostic candidates are a separate group and do not compete for rank.
        if score is None or group_score is None or not math.isclose(score, group_score, rel_tol=1e-9, abs_tol=1e-9):
            rank, group_score = position + 1, score
        result.append(CandidatePreview(
            code=str(candidate.code), fsn=candidate.fsn or "",
            row_id=f"{finding_id}:{role}:{position}",
            rank=rank if role == "selectable" else None, score=score,
            selectable=role == "selectable",
            details=tuple((labels.get(item.name, item.name.replace("_", " ").capitalize()),
                           getattr(candidate, item.name)) for item in fields(candidate)),
        ))
    return tuple(result)


def load_suggestions_preview(content: bytes, filename: str = "suggestions.json") -> PreviewState:
    """Parse atomically, inherit saved scope, and preserve the backend objects.

    Each successful import gets a new snapshot identity. Duplicates remain
    separate rows, indexed against the original, unfiltered suggestions tuple.
    Metadata is retained server-side, never used to open paths or run pipelines.
    """
    if len(content) > MAX_SUGGESTIONS_BYTES:
        raise SuggestionsPreviewError("Suggestions JSON exceeds the 50 MiB upload limit.")
    from snomed_post_processing.sanitization.json_io import read_sanitization_suggestions_json_with_metadata
    from snomed_post_processing.terminology import policy_label, suggestion_status_label
    from snomed_post_processing.uima_processing.scope import annotator_in_scope, normalize_annotators

    try:
        suggestions, metadata = read_sanitization_suggestions_json_with_metadata(
            io.StringIO(content.decode("utf-8-sig"))
        )
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        raise SuggestionsPreviewError(
            "Invalid sanitization suggestions JSON. Use suggestions JSON, not findings or reviewed decisions."
        ) from None
    saved_scope = metadata.get("annotators")
    if saved_scope is not None and (
        not isinstance(saved_scope, list) or any(not isinstance(name, str) for name in saved_scope)
    ):
        raise SuggestionsPreviewError("Saved metadata.annotators must be a list of annotator names.")
    scope = normalize_annotators(saved_scope)
    snapshot = uuid.uuid4().hex
    rows = []
    for index, suggestion in enumerate(suggestions):
        finding = suggestion.finding
        if not annotator_in_scope(finding.annotator, scope):
            continue
        row_id = f"{snapshot}:{index}"
        rows.append(FindingPreview(
            row_id=row_id, suggestion_index=index, document=finding.document,
            annotator=finding.annotator, code=finding.code or "", text=finding.covered_text,
            reason=suggestion.reason,
            candidates=_candidates(suggestion.candidates, row_id, "selectable")
            + _candidates(suggestion.context_candidates, row_id, "context"),
            status=suggestion_status_label(suggestion.status.value).replace("_", " "),
            policy_issue=policy_label(finding.list_type), source_fsn=finding.fsn or "",
            layer=finding.layer or "", offset=finding.offset, ignored=finding.ignored,
            candidate_count=suggestion.candidate_count,
            retrieval_limits=tuple(getattr(suggestion, "retrieval_limits", ())),
            proposed_code="" if suggestion.replacement_code is None else str(suggestion.replacement_code),
        ))
    return PreviewState(findings=tuple(rows), source_name=filename, is_demo=False,
                        source_suggestions=tuple(suggestions), metadata=metadata, source_annotators=scope)
