"""Data models for the annotation-store import pipeline."""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Optional


@dataclasses.dataclass(frozen=True)
class ExportMetadata:
    """Metadata inferred from an INCEpTION export ZIP filename."""

    site: str
    batch_index: Optional[int]
    batch_total: Optional[int]
    batch_label: Optional[str]


@dataclasses.dataclass(frozen=True)
class CasView:
    """One loaded CAS together with its provenance inside an export ZIP."""

    site: str
    export_path: pathlib.Path
    export_filename: str
    batch_index: Optional[int]
    batch_total: Optional[int]
    batch_label: Optional[str]
    document_name: str
    view_kind: str
    annotator: str
    cas_path: str
    cas: object


@dataclasses.dataclass(frozen=True)
class ConceptMetadata:
    """SNOMED concept metadata used to enrich annotation occurrences."""

    sctid: str
    fsn: Optional[str]
    semantic_tag: Optional[str]
    active: Optional[bool]


@dataclasses.dataclass(frozen=True)
class AnnotationOccurrence:
    """A single span annotation occurrence enriched with SNOMED metadata."""

    layer: str
    begin_offset: int
    end_offset: int
    covered_text: Optional[str]
    sctid: Optional[str]
    fsn: Optional[str]
    semantic_tag: Optional[str]
    active: Optional[bool]
    raw_id: Optional[str]
    literal: Optional[str]
    annotation_hash: str


@dataclasses.dataclass
class AnnotationStoreSummary:
    """Counters and warnings collected during an import run."""

    exports_processed: int = 0
    documents: int = 0
    annotation_views: int = 0
    annotations: int = 0
    known_sctids: int = 0
    unknown_sctids: set[str] = dataclasses.field(default_factory=set)
    failed_cas_members: list[dict] = dataclasses.field(default_factory=list)
    missing_batches: list[dict] = dataclasses.field(default_factory=list)
