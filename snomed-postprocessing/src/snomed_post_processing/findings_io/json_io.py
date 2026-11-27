"""JSON read/write helpers for structured critical findings."""

from __future__ import annotations

import datetime
from io import StringIO
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
    if hasattr(output, "write"):
        _write_critical_findings_payload(findings, output, metadata=metadata)
        return
    with Path(output).open("w", encoding="utf-8") as fi:
        _write_critical_findings_payload(findings, fi, metadata=metadata)


def _write_critical_findings_payload(
    findings: Sequence[CriticalFinding],
    output: TextIO,
    *,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Write findings one at a time instead of duplicating the full list as dictionaries."""
    header = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "metadata": metadata or {},
    }
    output.write("{\n")
    for key, value in header.items():
        output.write(f"  {json.dumps(key)}: ")
        rendered = json.dumps(value, ensure_ascii=False, indent=2)
        output.write(rendered.replace("\n", "\n  "))
        output.write(",\n")
    output.write('  "findings": [')
    for index, finding in enumerate(findings):
        output.write("," if index else "")
        output.write("\n    ")
        rendered = json.dumps(critical_finding_to_dict(finding), ensure_ascii=False, indent=2)
        output.write(rendered.replace("\n", "\n    "))
    output.write("\n  ]\n}\n")


def read_critical_findings_json(input_: Union[str, Path, TextIO]) -> list[CriticalFinding]:
    return read_critical_findings_json_with_metadata(input_)[0]


def read_critical_findings_json_with_metadata(input_: Union[str, Path, TextIO]) -> tuple[list[CriticalFinding], dict[str, Any]]:
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
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("Critical findings metadata must be an object.")
    return [critical_finding_from_dict(finding) for finding in findings], metadata


def critical_findings_json_text(
    findings: Sequence[CriticalFinding],
    *,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    output = StringIO()
    _write_critical_findings_payload(findings, output, metadata=metadata)
    return output.getvalue()
