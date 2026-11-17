"""Filename and document-name helpers for annotation-store imports."""

from __future__ import annotations

import pathlib
import re
from typing import Optional

from .models import ExportMetadata

_EXPORT_WITH_BATCH_RE = re.compile(
    r"^(?P<site>.+?)(?:_flat)?_(?:XMI|JSON)_(?P<batch_index>\d+)-(?P<batch_total>\d+)(?:[_-].+)?\.zip$",
    re.IGNORECASE,
)
_EXPORT_WITHOUT_BATCH_RE = re.compile(
    r"^(?P<site>.+?)(?:_flat)?_(?:XMI|JSON)(?:[_-].+)?\.zip$",
    re.IGNORECASE,
)
_CAS_SUFFIXES = (".xmi", ".json", ".zip", ".ser")


def parse_export_filename(
    path: pathlib.Path,
    site_override: Optional[str] = None,
    batch_index_override: Optional[int] = None,
    batch_total_override: Optional[int] = None,
) -> ExportMetadata:
    """Infer site and optional batch metadata from an export ZIP filename.

    Preferred filename forms are `<site>_XMI_<part>-<total>.zip`,
    `<site>_JSON_<part>-<total>.zip`, `<site>_flat_XMI_<part>-<total>.zip`,
    and `<site>_flat_JSON_<part>-<total>.zip`. A descriptive suffix after the batch
    marker is tolerated, e.g. `berlin_XMI_1-3_reviewed.zip`. Explicit CLI
    overrides take precedence over parsed batch values.
    """
    filename = pathlib.Path(path).name
    match = _EXPORT_WITH_BATCH_RE.match(filename)
    if match:
        site = site_override or match.group("site")
        parsed_batch_index = int(match.group("batch_index"))
        parsed_batch_total = int(match.group("batch_total"))
        batch_index = batch_index_override if batch_index_override is not None else parsed_batch_index
        batch_total = batch_total_override if batch_total_override is not None else parsed_batch_total
        return ExportMetadata(
            site=site,
            batch_index=batch_index,
            batch_total=batch_total,
            batch_label=_batch_label(batch_index, batch_total),
        )

    site_match = _EXPORT_WITHOUT_BATCH_RE.match(filename)
    site = site_override or (site_match.group("site") if site_match else pathlib.Path(path).stem)
    return ExportMetadata(
        site=site,
        batch_index=batch_index_override,
        batch_total=batch_total_override,
        batch_label=_batch_label(batch_index_override, batch_total_override),
    )


def _batch_label(batch_index: Optional[int], batch_total: Optional[int]) -> Optional[str]:
    if batch_index is None or batch_total is None:
        return None
    return f"{batch_index}-{batch_total}"


def normalize_document_name(name: str) -> str:
    """Return a canonical document name without CAS/container suffixes."""
    path = pathlib.PurePosixPath(str(name))
    value = path.name
    changed = True
    while changed:
        changed = False
        lower = value.lower()
        for suffix in _CAS_SUFFIXES:
            if lower.endswith(suffix):
                value = value[: -len(suffix)]
                changed = True
                break
    return value


def view_kind_from_cas_path(cas_path: str, *, fallback_flat_layout: bool = False) -> str:
    """Classify an INCEpTION CAS member as annotation, curation, or flat."""
    if fallback_flat_layout:
        return "flat"
    first = pathlib.PurePosixPath(cas_path).parts[0].lower()
    if first in {"annotation", "annotation_ser"}:
        return "annotation"
    if first in {"curation", "curation_ser"}:
        return "curation"
    return "flat"
