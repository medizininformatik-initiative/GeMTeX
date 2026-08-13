"""Central HDF5 policy-file access helpers.

This module keeps knowledge of the SNOMED postprocessing HDF5 layout in one
place. Higher-level code should prefer these helpers over opening HDF5 files and
addressing datasets directly.
"""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Optional, Union

import h5py
import numpy as np


POLICY_VIEW_VERSION = "0"
POLICIES = ("whitelist", "blacklist")


@dataclasses.dataclass(frozen=True)
class PolicyData:
    """Policy concept codes and FSNs for one policy list."""

    codes: np.ndarray
    fsn: np.ndarray
    source: str


@dataclasses.dataclass(frozen=True)
class ConceptsData:
    """Compact /concepts data used by sanitization and policy views."""

    codes: tuple[str, ...]
    fsn: tuple[str, ...]
    active: np.ndarray
    code_to_index: dict[str, int]


@dataclasses.dataclass(frozen=True)
class HistoricalAssociationsData:
    """Compact /historical_associations data."""

    source_index: np.ndarray
    target_index: np.ndarray
    association_type_id: np.ndarray
    association_types: tuple[str, ...]
    active: np.ndarray
    effective_time: tuple[str, ...]
    refset_id: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class AncestorsData:
    """Compact active ancestor arrays under /concepts."""

    ancestor_index: np.ndarray
    ancestor_concept_index: np.ndarray
    ancestor_distance: np.ndarray


@dataclasses.dataclass(frozen=True)
class HistoricalIsARelationshipsData:
    """Inactive is-a relationship states used for historical ancestor fallback."""

    source_index: np.ndarray
    parent_index: np.ndarray
    effective_time: tuple[str, ...]


def has_concepts_extension(path: Union[str, pathlib.Path]) -> bool:
    path = pathlib.Path(path)
    if not path.exists() or not path.is_file():
        return False
    with h5py.File(path, "r") as h5_file:
        return "concepts" in h5_file


def read_policy_data(
    h5_file: h5py.File,
    policy: str,
    *,
    version: str = POLICY_VIEW_VERSION,
) -> Optional[PolicyData]:
    """Read policy codes/FSNs from legacy groups or compact policy views.

    Legacy layout is preferred for backwards compatibility when both layouts are
    present. Returns ``None`` if the requested policy is absent.
    """
    if policy in h5_file:
        group = h5_file[policy]
        if version in group and "codes" in group[version]:
            return PolicyData(
                codes=group[version]["codes"][:],
                fsn=group[version]["fsn"][:] if "fsn" in group[version] else np.asarray([], dtype="S"),
                source=f"/{policy}/{version}",
            )

    compact_path = f"policy_views/{policy}/{version}/concept_index"
    if compact_path in h5_file and "concepts/codes" in h5_file:
        concept_indices = h5_file[compact_path][:]
        concepts = h5_file["concepts"]
        return PolicyData(
            codes=concepts["codes"][:][concept_indices],
            fsn=concepts["fsn"][:][concept_indices] if "fsn" in concepts else np.asarray([], dtype="S"),
            source=f"/policy_views/{policy}/{version}",
        )

    return None


def require_paths(h5_file: h5py.File, paths: list[str], *, purpose: str) -> None:
    missing = [path for path in paths if path not in h5_file]
    if missing:
        raise ValueError(
            f"HDF5 file is not {purpose}; missing compact dataset(s): "
            + ", ".join(missing)
        )


def require_sanitization_ready(h5_file: h5py.File) -> None:
    require_paths(
        h5_file,
        [
            "concepts/codes",
            "concepts/fsn",
            "concepts/active",
            "policy_views/whitelist/0/concept_index",
            "policy_views/blacklist/0/concept_index",
            "historical_associations/source_index",
            "historical_associations/target_index",
            "historical_associations/association_type_id",
            "historical_associations/association_types",
            "historical_associations/effective_time",
            "historical_associations/active",
            "historical_associations/refset_id",
        ],
        purpose="sanitization-ready",
    )


def require_bm25_ready(h5_file: h5py.File) -> None:
    require_paths(
        h5_file,
        [
            "concepts/codes",
            "concepts/fsn",
            "concepts/active",
            "policy_views/whitelist/0/concept_index",
            "policy_views/blacklist/0/concept_index",
        ],
        purpose="BM25-sanitization-ready",
    )


def has_active_ancestor_arrays(h5_file: h5py.File) -> bool:
    return all(
        path in h5_file
        for path in (
            "concepts/ancestors_index",
            "concepts/ancestor_concept_index",
            "concepts/ancestor_distance",
        )
    )


def has_historical_is_a_relationships(h5_file: h5py.File) -> bool:
    return all(
        path in h5_file
        for path in (
            "historical_is_a/source_index",
            "historical_is_a/parent_index",
            "historical_is_a/effective_time",
        )
    )


def read_concepts(h5_file: h5py.File) -> ConceptsData:
    require_paths(
        h5_file,
        ["concepts/codes", "concepts/fsn", "concepts/active"],
        purpose="concepts-ready",
    )
    codes = tuple(decode_array(h5_file["concepts/codes"][:]))
    fsn = tuple(decode_array(h5_file["concepts/fsn"][:]))
    active = np.asarray(h5_file["concepts/active"][:], dtype=bool)
    return ConceptsData(
        codes=codes,
        fsn=fsn,
        active=active,
        code_to_index={code: idx for idx, code in enumerate(codes)},
    )


def read_policy_indices(
    h5_file: h5py.File,
    policy: str,
    *,
    version: str = POLICY_VIEW_VERSION,
) -> frozenset[int]:
    return frozenset(
        int(idx) for idx in h5_file[f"policy_views/{policy}/{version}/concept_index"][:]
    )


def read_active_ancestors(h5_file: h5py.File) -> AncestorsData:
    require_paths(
        h5_file,
        [
            "concepts/ancestors_index",
            "concepts/ancestor_concept_index",
            "concepts/ancestor_distance",
        ],
        purpose="active-ancestor-ready",
    )
    concepts = h5_file["concepts"]
    return AncestorsData(
        ancestor_index=np.asarray(concepts["ancestors_index"][:], dtype=np.int64),
        ancestor_concept_index=np.asarray(concepts["ancestor_concept_index"][:], dtype=np.int64),
        ancestor_distance=np.asarray(concepts["ancestor_distance"][:], dtype=np.int64),
    )


def read_historical_associations(h5_file: h5py.File) -> HistoricalAssociationsData:
    require_paths(
        h5_file,
        [
            "historical_associations/source_index",
            "historical_associations/target_index",
            "historical_associations/association_type_id",
            "historical_associations/association_types",
            "historical_associations/effective_time",
            "historical_associations/active",
            "historical_associations/refset_id",
        ],
        purpose="historical-association-ready",
    )
    hist = h5_file["historical_associations"]
    return HistoricalAssociationsData(
        source_index=np.asarray(hist["source_index"][:], dtype=np.int64),
        target_index=np.asarray(hist["target_index"][:], dtype=np.int64),
        association_type_id=np.asarray(hist["association_type_id"][:], dtype=np.int64),
        association_types=tuple(decode_array(hist["association_types"][:])),
        active=np.asarray(hist["active"][:], dtype=bool),
        effective_time=tuple(decode_array(hist["effective_time"][:])),
        refset_id=tuple(decode_array(hist["refset_id"][:])),
    )


def read_historical_is_a_relationships(h5_file: h5py.File) -> HistoricalIsARelationshipsData:
    require_paths(
        h5_file,
        [
            "historical_is_a/source_index",
            "historical_is_a/parent_index",
            "historical_is_a/effective_time",
        ],
        purpose="historical-is-a-ready",
    )
    group = h5_file["historical_is_a"]
    return HistoricalIsARelationshipsData(
        source_index=np.asarray(group["source_index"][:], dtype=np.int64),
        parent_index=np.asarray(group["parent_index"][:], dtype=np.int64),
        effective_time=tuple(decode_array(group["effective_time"][:])),
    )


def decode_array(values) -> list[str]:
    decoded = []
    for value in values:
        if isinstance(value, (bytes, bytearray)):
            decoded.append(value.decode("utf-8"))
        else:
            decoded.append(str(value))
    return decoded
