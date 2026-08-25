"""Mapping between CriticalFinding dataclasses and JSON-compatible dicts."""

from __future__ import annotations

from typing import Any

from ..uima_processing import CriticalFinding, IgnoreOverlap


def ignore_overlap_to_dict(overlap: IgnoreOverlap) -> dict[str, Any]:
    return {
        "layer": overlap.layer,
        "offset": [int(overlap.offset[0]), int(overlap.offset[1])],
        "text": overlap.text,
    }


def ignore_overlap_from_dict(data: dict[str, Any]) -> IgnoreOverlap:
    return IgnoreOverlap(
        layer=str(data.get("layer", "")),
        offset=_offset_tuple(data.get("offset", (0, 0))),
        text=str(data.get("text", "")),
    )


def critical_finding_to_dict(finding: CriticalFinding) -> dict[str, Any]:
    return {
        "annotator": finding.annotator,
        "document": finding.document,
        "code": finding.code,
        "covered_text": finding.covered_text,
        "offset": [int(finding.offset[0]), int(finding.offset[1])],
        "list_type": finding.list_type,
        "reason": finding.reason,
        "layer": finding.layer,
        "fsn": finding.fsn,
        "ignored": bool(finding.ignored),
        "ignore_overlaps": [
            ignore_overlap_to_dict(overlap) for overlap in finding.ignore_overlaps
        ],
    }


def critical_finding_from_dict(data: dict[str, Any]) -> CriticalFinding:
    return CriticalFinding(
        annotator=str(data["annotator"]),
        document=str(data["document"]),
        code=None if data.get("code") is None else str(data.get("code")),
        covered_text=str(data.get("covered_text", "")),
        offset=_offset_tuple(data.get("offset", (0, 0))),
        list_type=str(data["list_type"]),
        reason=str(data["reason"]),
        layer=None if data.get("layer") is None else str(data.get("layer")),
        fsn=None if data.get("fsn") is None else str(data.get("fsn")),
        ignored=bool(data.get("ignored", False)),
        ignore_overlaps=tuple(
            ignore_overlap_from_dict(overlap)
            for overlap in data.get("ignore_overlaps", [])
        ),
    )


def _offset_tuple(value: Any) -> tuple[int, int]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"Offset must be a two-element sequence, got: {value!r}")
    return (int(value[0]), int(value[1]))
