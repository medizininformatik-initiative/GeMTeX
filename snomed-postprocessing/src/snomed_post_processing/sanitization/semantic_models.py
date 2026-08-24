"""Data models for semantic BM25 sanitization suggestions."""

from __future__ import annotations

import dataclasses
from typing import Optional

from ..uima_processing import CriticalFinding
from .models import SanitizationCandidate, SanitizationStatus


@dataclasses.dataclass(frozen=True)
class SemanticBm25Candidate:
    """A single policy-acceptable BM25 replacement candidate."""

    code: str
    fsn: str
    score: float
    lexical_score: float
    semantic_tag: Optional[str]
    active: bool
    in_whitelist: bool
    in_blacklist: bool
    source: str = "snomed_fsn"
    matched_term: Optional[str] = None
    source_member: Optional[str] = None

    @property
    def policy_acceptable(self) -> bool:
        return self.active and self.in_whitelist and not self.in_blacklist


@dataclasses.dataclass(frozen=True)
class SemanticBm25Suggestion:
    """Suggestion produced by :class:`SemanticBm25Resolver`."""

    finding: CriticalFinding
    status: SanitizationStatus
    replacement_code: Optional[str] = None
    replacement_fsn: Optional[str] = None
    association_type: Optional[str] = None
    reason: str = ""
    score: float = 0.0
    candidate_count: int = 0
    candidates: tuple[SemanticBm25Candidate, ...] = ()
    context_candidates: tuple[SanitizationCandidate, ...] = ()


@dataclasses.dataclass(frozen=True)
class Bm25Hit:
    """A scored document hit from :class:`BM25Index`."""

    document_id: int
    score: float
    matched_query_tokens: tuple[str, ...]
