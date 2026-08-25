"""Data models for SNOMED CT release ingestion."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Rf2ReleaseMembers:
    concept: str
    description: str
    association: Optional[str]
    relationship: Optional[str]
    release_date: str
    view: str


# Backwards-compatible alias for existing callers/tests.
Rf2SnapshotMembers = Rf2ReleaseMembers


@dataclass(frozen=True)
class Rf2IngestionSummary:
    output_path: pathlib.Path
    concept_count: int
    fsn_count: int
    association_count: int
    relationship_parent_count: int
    whitelist_count: int
    blacklist_count: int
    files: Rf2ReleaseMembers
