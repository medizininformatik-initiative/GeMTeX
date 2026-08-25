"""Data models for UIMA/INCEpTION processing."""

from __future__ import annotations

import dataclasses
from typing import Optional

import numpy as np


@dataclasses.dataclass
class IgnoreOverlap:
    layer: str
    offset: tuple[int, int]
    text: str


@dataclasses.dataclass
class DocumentAnnotations:
    snomed_codes: np.ndarray
    offsets: np.ndarray
    text: np.ndarray
    layers: np.ndarray
    length: int
    ignore_mask: np.ndarray = dataclasses.field(default_factory=lambda: np.asarray([], dtype=bool))
    ignore_overlaps: list[list[IgnoreOverlap]] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class CriticalFinding:
    annotator: str
    document: str
    code: Optional[str]
    covered_text: str
    offset: tuple[int, int]
    list_type: str
    reason: str
    layer: Optional[str] = None
    fsn: Optional[str] = None
    ignored: bool = False
    ignore_overlaps: tuple[IgnoreOverlap, ...] = ()


@dataclasses.dataclass
class TemporaryContainer:
    max_length: int
    documents: dict[str, DocumentAnnotations]


@dataclasses.dataclass
class TemporaryCorpus:
    annotators: dict[str, TemporaryContainer]
