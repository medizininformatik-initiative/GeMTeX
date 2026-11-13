"""Presentation-only preview state; no decisions, storage or pipeline calls."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class CandidatePreview:
    code: str
    fsn: str
    row_id: str
    rank: Optional[int] = None
    score: Optional[float] = None
    selectable: bool = True
    details: Tuple[Tuple[str, object], ...] = ()


@dataclass(frozen=True)
class FindingPreview:
    row_id: str
    suggestion_index: int
    document: str
    annotator: str
    code: str
    text: str
    reason: str
    candidates: Tuple[CandidatePreview, ...] = ()
    status: str = ""
    policy_issue: str = ""
    source_fsn: str = ""
    layer: str = ""
    offset: Optional[Tuple[int, int]] = None
    ignored: bool = False
    candidate_count: int = 0
    retrieval_limits: Tuple[str, ...] = ()
    proposed_code: str = ""


@dataclass
class PreviewState:
    """Create one per page; navigation never stages or approves a decision."""

    findings: Tuple[FindingPreview, ...] = ()
    selected_finding_id: Optional[str] = None
    selected_candidate_id: Optional[str] = None
    source_name: Optional[str] = None
    source_suggestions: Tuple[object, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)
    source_annotators: Tuple[str, ...] = ()

    @property
    def selected_finding(self) -> Optional[FindingPreview]:
        return next((row for row in self.findings if row.row_id == self.selected_finding_id), None)

    def select_finding(self, row_id: str) -> FindingPreview:
        finding = next((row for row in self.findings if row.row_id == row_id), None)
        if finding is None:
            raise ValueError("Unknown finding; select a row from the current preview.")
        if row_id != self.selected_finding_id:
            self.selected_candidate_id = None
        self.selected_finding_id = row_id
        return finding

    def preview_candidate(self, row_id: str) -> CandidatePreview:
        finding = self.selected_finding
        candidate = next((item for item in finding.candidates if item.row_id == row_id), None) if finding else None
        if candidate is None:
            raise ValueError("Unknown candidate for the selected finding.")
        self.selected_candidate_id = row_id
        return candidate
