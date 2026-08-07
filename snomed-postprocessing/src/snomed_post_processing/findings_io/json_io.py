"""JSON read/write helpers for structured critical findings."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Optional, Sequence, TextIO, Union

from ..uima_processing import CriticalFinding
from .mapping import critical_finding_from_dict, critical_finding_to_dict

SCHEMA = "snomed-post-processing.critical-findings"
SCHEMA_VERSION = 1


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
