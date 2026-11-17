"""Framework-neutral suggestion overview and identity-masked CSV export."""
from typing import Any

import pandas as pd

from .terminology import policy_label


SUGGESTION_OVERVIEW_COLUMNS = (
    "#", "Document", "Annotator", "Source code", "Covered text", "Offset", "Issue", "Status",
    "Replacement code", "Replacement FSN", "Reason", "Top candidates",
    "Diagnostic candidates (not selectable)", "Retrieval limits",
)


def suggestion_overview_row(index: int, suggestion: Any) -> dict[str, Any]:
    finding = suggestion.finding
    status = getattr(suggestion, "status", "")
    return {
        "#": index,
        "Document": finding.document,
        "Annotator": finding.annotator,
        "Source code": finding.code or "",
        "Covered text": finding.covered_text,
        "Offset": ", ".join(map(str, finding.offset)),
        "Issue": policy_label(getattr(finding, "list_type", "")),
        "Status": getattr(status, "value", str(status)),
        "Replacement code": getattr(suggestion, "replacement_code", None) or "",
        "Replacement FSN": getattr(suggestion, "replacement_fsn", None) or "",
        "Reason": getattr(suggestion, "reason", "") or "",
        "Top candidates": _candidate_summary(getattr(suggestion, "candidates", ())),
        "Diagnostic candidates (not selectable)": _candidate_summary(getattr(suggestion, "context_candidates", ())),
        "Retrieval limits": ", ".join(getattr(suggestion, "retrieval_limits", ())),
    }


def _candidate_summary(candidates: Any) -> str:
    parts = []
    for candidate in tuple(candidates or ())[:3]:
        code = getattr(candidate, "code", "")
        fsn = getattr(candidate, "fsn", None) or ""
        association = getattr(candidate, "association_type", None)
        source = getattr(candidate, "source", None)
        score = getattr(candidate, "score", None)
        source_hint = source or association or "candidate"
        score_hint = f", score {float(score):.2f}" if score is not None else ""
        parts.append(f"{code} — {fsn} ({source_hint}{score_hint})")
    return " | ".join(parts)


def masked_suggestions_csv(suggestions) -> bytes:
    rows = [suggestion_overview_row(index, item) for index, item in enumerate(suggestions, start=1)]
    return masked_overview_csv(pd.DataFrame(rows, columns=SUGGESTION_OVERVIEW_COLUMNS))


def masked_overview_csv(overview_df: pd.DataFrame) -> bytes:
    masked = overview_df.copy()
    for column, prefix in (("Document", "document"), ("Annotator", "annotator")):
        aliases = {name: f"{prefix}-{index}" for index, name in enumerate(masked[column].unique(), start=1)}
        masked[column] = masked[column].map(aliases)
    return masked.to_csv(index=False).encode("utf-8-sig")