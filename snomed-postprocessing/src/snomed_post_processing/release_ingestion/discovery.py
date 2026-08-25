"""Discovery of relevant files inside SNOMED CT RF2 release ZIPs."""

from __future__ import annotations

import pathlib
import re
import zipfile
from typing import Iterable, Optional, Union

from .models import Rf2ReleaseMembers


def _is_rf2_text_member(name: str) -> bool:
    return (
        name.endswith(".txt")
        and not name.startswith("__MACOSX/")
        and "/._" not in name
        and not pathlib.PurePosixPath(name).name.startswith("._")
    )


def _find_unique_member(
    names: Iterable[str],
    pattern: str,
    required: bool = True,
) -> Optional[str]:
    regex = re.compile(pattern)
    matches = sorted(name for name in names if regex.search(name))
    if not matches:
        if required:
            raise FileNotFoundError(f"No RF2 ZIP member matched pattern: {pattern}")
        return None
    if len(matches) > 1:
        raise ValueError(
            "Multiple RF2 ZIP members matched pattern "
            f"{pattern!r}: {matches}. Please make matching more specific."
        )
    return matches[0]


def discover_release_members(
    zip_path: Union[pathlib.Path, str], language: str = "en", view: str = "Snapshot"
) -> Rf2ReleaseMembers:
    """Find the RF2 release members needed for HDF5 ingestion.

    The function intentionally ignores macOS metadata entries commonly found in
    ZIPs created on macOS.
    """
    zip_path = pathlib.Path(zip_path)
    lang = re.escape(language)
    view_normalized = view.capitalize()
    if view_normalized not in {"Snapshot", "Full"}:
        raise ValueError("RF2 view must be either 'Snapshot' or 'Full'.")
    with zipfile.ZipFile(zip_path) as zf:
        names = [name for name in zf.namelist() if _is_rf2_text_member(name)]

    concept = _find_unique_member(
        names,
        rf"(?:^|/){view_normalized}/Terminology/sct2_Concept_{view_normalized}_[^/]+_\d{{8}}\.txt$",
    )
    release_match = re.search(r"_(\d{8})\.txt$", concept)
    if release_match is None:
        raise ValueError(f"Could not infer RF2 release date from concept member: {concept}")
    return Rf2ReleaseMembers(
        concept=concept,
        description=_find_unique_member(
            names,
            rf"(?:^|/){view_normalized}/Terminology/sct2_Description_{view_normalized}-{lang}_[^/]+_\d{{8}}\.txt$",
        ),
        association=_find_unique_member(
            names,
            rf"(?:^|/){view_normalized}/Refset/Content/der2_cRefset_Association{view_normalized}_[^/]+_\d{{8}}\.txt$",
            required=False,
        ),
        relationship=_find_unique_member(
            names,
            rf"(?:^|/){view_normalized}/Terminology/sct2_Relationship_{view_normalized}_[^/]+_\d{{8}}\.txt$",
            required=False,
        ),
        release_date=release_match.group(1),
        view=view_normalized.lower(),
    )


def discover_snapshot_members(zip_path: Union[pathlib.Path, str], language: str = "en") -> Rf2ReleaseMembers:
    """Find the RF2 Snapshot members needed for HDF5 ingestion."""
    return discover_release_members(zip_path, language=language, view="Snapshot")


def discover_full_members(zip_path: Union[pathlib.Path, str], language: str = "en") -> Rf2ReleaseMembers:
    """Find the RF2 Full members needed for HDF5 ingestion."""
    return discover_release_members(zip_path, language=language, view="Full")
