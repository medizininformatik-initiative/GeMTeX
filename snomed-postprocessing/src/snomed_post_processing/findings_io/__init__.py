"""JSON serialization helpers for structured critical findings."""

from .json_io import (
    SCHEMA,
    SCHEMA_VERSION,
    critical_findings_json_text,
    critical_findings_payload,
    read_critical_findings_json,
    write_critical_findings_json,
)
from .mapping import (
    _offset_tuple,
    critical_finding_from_dict,
    critical_finding_to_dict,
    ignore_overlap_from_dict,
    ignore_overlap_to_dict,
)

__all__ = [
    "SCHEMA",
    "SCHEMA_VERSION",
    "ignore_overlap_to_dict",
    "ignore_overlap_from_dict",
    "critical_finding_to_dict",
    "critical_finding_from_dict",
    "critical_findings_payload",
    "write_critical_findings_json",
    "read_critical_findings_json",
    "critical_findings_json_text",
    "_offset_tuple",
]
