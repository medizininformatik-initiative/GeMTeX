"""JSON serialization helpers for structured critical findings."""

from __future__ import annotations

import dataclasses
import datetime
import json
from pathlib import Path
from typing import Any, Optional, Sequence, TextIO, Union

from ..uima_processing import CriticalFinding, IgnoreOverlap

SCHEMA = "snomed-post-processing.critical-findings"
SCHEMA_VERSION = 1


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


def critical_findings_payload(
    findings: Sequence[CriticalFinding],
    *,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "metadata": metadata or {},
        "findings": [critical_finding_to_dict(finding) for finding in findings],
    }


def write_critical_findings_json(
    findings: Sequence[CriticalFinding],
    output: Union[str, Path, TextIO],
    *,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    payload = critical_findings_payload(findings, metadata=metadata)
    if hasattr(output, "write"):
        json.dump(payload, output, ensure_ascii=False, indent=2)
        return
    with Path(output).open("w", encoding="utf-8") as fi:
        json.dump(payload, fi, ensure_ascii=False, indent=2)


def read_critical_findings_json(input_: Union[str, Path, TextIO]) -> list[CriticalFinding]:
    if hasattr(input_, "read"):
        payload = json.load(input_)
    else:
        with Path(input_).open("r", encoding="utf-8") as fi:
            payload = json.load(fi)
    if not isinstance(payload, dict):
        raise ValueError("Critical findings JSON must contain an object payload.")
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"Unsupported critical findings schema: {payload.get('schema')!r}.")
    if int(payload.get("schema_version", 0)) != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported critical findings schema version: {payload.get('schema_version')!r}."
        )
    findings = payload.get("findings")
    if not isinstance(findings, list):
        raise ValueError("Critical findings JSON payload must contain a findings list.")
    return [critical_finding_from_dict(finding) for finding in findings]


def critical_findings_json_text(
    findings: Sequence[CriticalFinding],
    *,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    return json.dumps(
        critical_findings_payload(findings, metadata=metadata),
        ensure_ascii=False,
        indent=2,
    )


def _offset_tuple(value: Any) -> tuple[int, int]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"Offset must be a two-element sequence, got: {value!r}")
    return (int(value[0]), int(value[1]))
