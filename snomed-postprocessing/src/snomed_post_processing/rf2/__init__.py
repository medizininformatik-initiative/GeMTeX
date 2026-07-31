"""RF2 ZIP ingestion utilities for enriched SNOMED CT HDF5 files.

The functions in this module read SNOMED CT RF2 release ZIPs directly without
extracting them. The first implementation targets Snapshot files because they
represent the target release state and are sufficient for conservative
historical-association based sanitization.
"""

from __future__ import annotations

import csv
import logging
import pathlib
import re
import zipfile
from dataclasses import dataclass
from io import TextIOWrapper
from typing import Iterable, Optional, Union

import h5py
import numpy as np

from ..utils import _compute_compact_ancestor_arrays

FSN_TYPE_ID = "900000000000003001"
IS_A_TYPE_ID = "116680003"

ASSOCIATION_REFSET_IDS = {
    "900000000000527005": "SAME_AS",
    "900000000000526001": "REPLACED_BY",
    "900000000000523009": "POSSIBLY_EQUIVALENT_TO",
    "900000000000528000": "WAS_A",
    "900000000000525002": "MOVED_TO",
    "900000000000524003": "MOVED_FROM",
    "900000000000530003": "ALTERNATIVE",
}


@dataclass(frozen=True)
class Rf2SnapshotMembers:
    concept: str
    description: str
    association: Optional[str]
    relationship: Optional[str]


@dataclass(frozen=True)
class Rf2IngestionSummary:
    output_path: pathlib.Path
    concept_count: int
    fsn_count: int
    association_count: int
    relationship_parent_count: int
    files: Rf2SnapshotMembers


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


def discover_snapshot_members(zip_path: Union[pathlib.Path, str], language: str = "en") -> Rf2SnapshotMembers:
    """Find the RF2 Snapshot members needed for HDF5 ingestion.

    The function intentionally ignores macOS metadata entries commonly found in
    ZIPs created on macOS.
    """
    zip_path = pathlib.Path(zip_path)
    lang = re.escape(language)
    with zipfile.ZipFile(zip_path) as zf:
        names = [name for name in zf.namelist() if _is_rf2_text_member(name)]

    return Rf2SnapshotMembers(
        concept=_find_unique_member(
            names,
            r"(?:^|/)Snapshot/Terminology/sct2_Concept_Snapshot_[^/]+_\d{8}\.txt$",
        ),
        description=_find_unique_member(
            names,
            rf"(?:^|/)Snapshot/Terminology/sct2_Description_Snapshot-{lang}_[^/]+_\d{{8}}\.txt$",
        ),
        association=_find_unique_member(
            names,
            r"(?:^|/)Snapshot/Refset/Content/der2_cRefset_AssociationSnapshot_[^/]+_\d{8}\.txt$",
            required=False,
        ),
        relationship=_find_unique_member(
            names,
            r"(?:^|/)Snapshot/Terminology/sct2_Relationship_Snapshot_[^/]+_\d{8}\.txt$",
            required=False,
        ),
    )


def _iter_rf2_rows(zf: zipfile.ZipFile, member: str, required_columns: set[str]):
    with zf.open(member) as raw:
        text = TextIOWrapper(raw, encoding="utf-8", newline="")
        reader = csv.DictReader(text, delimiter="\t")
        fieldnames = set(reader.fieldnames or [])
        missing = required_columns - fieldnames
        if missing:
            raise ValueError(
                f"RF2 member {member!r} is missing required columns: {sorted(missing)}"
            )
        yield from reader


def _semantic_tag_from_fsn(fsn: str) -> str:
    match = re.search(r"\(([^()]*)\)\s*$", fsn)
    return match.group(1) if match else ""


def _read_active_concepts(zf: zipfile.ZipFile, member: str) -> set[str]:
    concepts: set[str] = set()
    for row in _iter_rf2_rows(
        zf, member, {"id", "effectiveTime", "active", "moduleId", "definitionStatusId"}
    ):
        if row["active"] == "1":
            concepts.add(row["id"])
    return concepts


def _read_active_fsns(
    zf: zipfile.ZipFile,
    member: str,
    active_concepts: set[str],
) -> dict[str, str]:
    fsns: dict[str, str] = {}
    for row in _iter_rf2_rows(
        zf,
        member,
        {
            "id",
            "effectiveTime",
            "active",
            "moduleId",
            "conceptId",
            "languageCode",
            "typeId",
            "term",
            "caseSignificanceId",
        },
    ):
        if (
            row["active"] == "1"
            and row["typeId"] == FSN_TYPE_ID
            and row["conceptId"] in active_concepts
        ):
            fsns[row["conceptId"]] = row["term"]
    return fsns


def _read_active_associations(
    zf: zipfile.ZipFile,
    member: Optional[str],
) -> list[tuple[str, str, str, str, str]]:
    if member is None:
        return []
    associations = []
    for row in _iter_rf2_rows(
        zf,
        member,
        {
            "id",
            "effectiveTime",
            "active",
            "moduleId",
            "refsetId",
            "referencedComponentId",
            "targetComponentId",
        },
    ):
        if row["active"] != "1":
            continue
        associations.append(
            (
                row["referencedComponentId"],
                row["targetComponentId"],
                ASSOCIATION_REFSET_IDS.get(row["refsetId"], row["refsetId"]),
                row["effectiveTime"],
                row["refsetId"],
            )
        )
    return associations


def _read_active_parent_map(
    zf: zipfile.ZipFile,
    member: Optional[str],
    active_concepts: set[str],
) -> dict[str, set[str]]:
    if member is None:
        return {}
    parent_map: dict[str, set[str]] = {}
    for row in _iter_rf2_rows(
        zf,
        member,
        {
            "id",
            "effectiveTime",
            "active",
            "moduleId",
            "sourceId",
            "destinationId",
            "relationshipGroup",
            "typeId",
            "characteristicTypeId",
            "modifierId",
        },
    ):
        if row["active"] != "1" or row["typeId"] != IS_A_TYPE_ID:
            continue
        if row["sourceId"] in active_concepts and row["destinationId"] in active_concepts:
            parent_map.setdefault(row["sourceId"], set()).add(row["destinationId"])
    return parent_map


def _write_string_dataset(group: h5py.Group, name: str, values: Iterable[str]):
    data = np.asarray(list(values), dtype=np.dtypes.StringDType)
    dataset = group.create_dataset(name, shape=(data.shape[0],), dtype="T")
    dataset[:] = data


def _replace_group(h5_file: h5py.File, name: str, force_overwrite: bool) -> h5py.Group:
    if name in h5_file:
        if not force_overwrite:
            raise ValueError(
                f"HDF5 group '/{name}' already exists. Use force_overwrite=True to replace it."
            )
        del h5_file[name]
    return h5_file.create_group(name)


def write_snapshot_hdf5_from_rf2_zip(
    zip_path: Union[pathlib.Path, str],
    output_path: Union[pathlib.Path, str],
    *,
    language: str = "en",
    include_associations: bool = True,
    include_ancestors: bool = False,
    force_overwrite: bool = False,
    use_memoization: bool = False,
) -> Rf2IngestionSummary:
    """Create an enriched HDF5 file from RF2 Snapshot files in a ZIP.

    The output currently writes:

    ```text
    /concepts/codes
    /concepts/fsn
    /concepts/semantic_tag
    /concepts/active
    /historical_associations/source_code
    /historical_associations/target_code
    /historical_associations/association_type
    /historical_associations/effective_time
    /historical_associations/active
    /historical_associations/refset_id
    ```

    If ``include_ancestors`` is true, compact ancestor arrays compatible with
    the existing concept extension are added under `/concepts`.
    """
    zip_path = pathlib.Path(zip_path)
    output_path = pathlib.Path(output_path)
    members = discover_snapshot_members(zip_path, language=language)

    with zipfile.ZipFile(zip_path) as zf:
        logging.info("Reading active RF2 Snapshot concepts from %s", members.concept)
        active_concepts = _read_active_concepts(zf, members.concept)

        logging.info("Reading active RF2 Snapshot FSNs from %s", members.description)
        fsn_by_code = _read_active_fsns(zf, members.description, active_concepts)

        associations = []
        if include_associations:
            logging.info("Reading active RF2 Snapshot associations from %s", members.association)
            associations = _read_active_associations(zf, members.association)

        parent_map: dict[str, set[str]] = {}
        if include_ancestors:
            logging.info("Reading active RF2 Snapshot is-a relationships from %s", members.relationship)
            parent_map = _read_active_parent_map(zf, members.relationship, active_concepts)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(output_path, "a") as h5_file:
        concept_group = _replace_group(h5_file, "concepts", force_overwrite)
        codes = sorted(active_concepts)
        _write_string_dataset(concept_group, "codes", codes)
        _write_string_dataset(concept_group, "fsn", (fsn_by_code.get(code, "") for code in codes))
        _write_string_dataset(
            concept_group,
            "semantic_tag",
            (_semantic_tag_from_fsn(fsn_by_code.get(code, "")) for code in codes),
        )
        concept_group.create_dataset(
            "active", data=np.ones((len(codes),), dtype=bool)
        )

        if include_ancestors:
            ancestor_codes_base, ancestor_index, ancestor_codes, ancestor_distances = (
                _compute_compact_ancestor_arrays(
                    fsn_by_code | {code: "" for code in active_concepts if code not in fsn_by_code},
                    parent_map,
                    use_memoization=use_memoization,
                )
            )
            # Ancestor arrays must align with /concepts/codes. The helper sorts the
            # union of concept and relationship codes, which should equal active concepts
            # after relationship filtering; validate before writing.
            if list(ancestor_codes_base) != codes:
                raise ValueError(
                    "Computed ancestor concept order does not match /concepts/codes."
                )
            concept_group.create_dataset("ancestors_index", data=ancestor_index)
            _write_string_dataset(concept_group, "ancestors_codes", ancestor_codes)
            concept_group.create_dataset("ancestors_distance", data=ancestor_distances)

        if include_associations:
            assoc_group = _replace_group(
                h5_file, "historical_associations", force_overwrite
            )
            _write_string_dataset(assoc_group, "source_code", (a[0] for a in associations))
            _write_string_dataset(assoc_group, "target_code", (a[1] for a in associations))
            _write_string_dataset(assoc_group, "association_type", (a[2] for a in associations))
            _write_string_dataset(assoc_group, "effective_time", (a[3] for a in associations))
            assoc_group.create_dataset(
                "active", data=np.ones((len(associations),), dtype=bool)
            )
            _write_string_dataset(assoc_group, "refset_id", (a[4] for a in associations))

    return Rf2IngestionSummary(
        output_path=output_path,
        concept_count=len(active_concepts),
        fsn_count=len(fsn_by_code),
        association_count=len(associations),
        relationship_parent_count=sum(len(v) for v in parent_map.values()),
        files=members,
    )
