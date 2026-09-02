"""Filename and document-name helpers for annotation-store imports."""

from __future__ import annotations

import pathlib
import re
from typing import Optional

from .models import ExportMetadata

_EXPORT_RE = re.compile(
    r"^(?P<site>.+?)(?:_flat)?_XMI_(?P<batch_index>\d+)-(?P<batch_total>\d+)\.zip$",
    re.IGNORECASE,
)
_CAS_SUFFIXES = (".xmi", ".json", ".zip", ".ser")


def parse_export_filename(path: pathlib.Path, site_override: Optional[str] = None) -> ExportMetadata:
    """Infer site and optional batch metadata from an export ZIP filename."""
    filename = pathlib.Path(path).name
    match = _EXPORT_RE.match(filename)
    if match:
        site = site_override or match.group("site")
        batch_index = int(match.group("batch_index"))
        batch_total = int(match.group("batch_total"))
        return ExportMetadata(
            site=site,
            batch_index=batch_index,
            batch_total=batch_total,
            batch_label=f"{batch_index}-{batch_total}",
        )

    return ExportMetadata(
        site=site_override or pathlib.Path(path).stem,
        batch_index=None,
        batch_total=None,
        batch_label=None,
    )


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
