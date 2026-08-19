"""JSON read/write helpers for reviewed sanitization decisions."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Optional, Sequence, TextIO, Union

SCHEMA = "snomed-post-processing.sanitization-decisions"
SCHEMA_VERSION = 1


def sanitization_decisions_payload(
    decisions: Sequence[dict[str, Any]],
    *,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "metadata": metadata or {},
        "decisions": list(decisions),
    }


def sanitization_decisions_json_text(
    decisions: Sequence[dict[str, Any]],
    *,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    return json.dumps(
        sanitization_decisions_payload(decisions, metadata=metadata),
        ensure_ascii=False,
        indent=2,
    )


def write_sanitization_decisions_json(
    decisions: Sequence[dict[str, Any]],
    output: Union[str, Path, TextIO],
    *,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    payload = sanitization_decisions_payload(decisions, metadata=metadata)
    if hasattr(output, "write"):
        json.dump(payload, output, ensure_ascii=False, indent=2)
        return
    with Path(output).open("w", encoding="utf-8") as fi:
        json.dump(payload, fi, ensure_ascii=False, indent=2)


def read_sanitization_decisions_json(input_: Union[str, Path, TextIO]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if hasattr(input_, "read"):
        payload = json.load(input_)
    else:
        with Path(input_).open("r", encoding="utf-8") as fi:
            payload = json.load(fi)
    if not isinstance(payload, dict):
        raise ValueError("Sanitization decisions JSON must contain an object payload.")
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"Unsupported sanitization decisions schema: {payload.get('schema')!r}.")
    if int(payload.get("schema_version", 0)) != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported sanitization decisions schema version: {payload.get('schema_version')!r}."
        )
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        raise ValueError("Sanitization decisions JSON payload must contain a decisions list.")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return decisions, metadata
