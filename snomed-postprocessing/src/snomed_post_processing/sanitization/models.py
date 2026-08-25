"""Data models and constants for sanitization suggestions."""

from __future__ import annotations

import dataclasses
import enum
from typing import Optional

from ..uima_processing import CriticalFinding


ASSOCIATION_TYPE_DESCRIPTIONS = {
    "SAME_AS": "Source concept is considered equivalent to the target concept.",
    "REPLACED_BY": "Source concept was retired and replaced by the target concept.",
    "POSSIBLY_EQUIVALENT_TO": "Source concept may be equivalent to the target concept; manual review is recommended.",
    "WAS_A": "Source concept used to be classified as the target concept; usually broader/less exact.",
    "MOVED_TO": "Concept was moved to another namespace/module and points to its new target.",
    "MOVED_FROM": "Inverse move association; usually not useful for forward replacement suggestions.",
    "ALTERNATIVE": "Alternative target concept exists, but equivalence is not guaranteed.",
    "PARTIALLY_EQUIVALENT_TO": "Source concept is partially equivalent to the target concept; manual review is recommended.",
    "POSSIBLY_REPLACED_BY": "Source concept may have been replaced by the target concept; manual review is recommended.",
    "REFERS_TO": "Source concept refers to the target concept; not necessarily a safe replacement.",
    "SIMILAR_TO": "Source concept is similar to the target concept; equivalence is not guaranteed.",
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
    NEAREST_TARGET_ANCESTOR = "nearest_target_ancestor"
    NEAREST_HISTORICAL_ANCESTOR = "nearest_historical_ancestor"
    AMBIGUOUS_REPLACEMENT = "ambiguous_replacement"
    AMBIGUOUS_ANCESTOR = "ambiguous_ancestor"
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
