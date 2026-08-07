"""HDF5 dump writing and ancestor-array helpers."""

from __future__ import annotations

import logging
import pathlib
from collections import deque
from typing import Optional, Union

import h5py
import numpy as np

from .policy import has_concepts_extension
from ..snomed import ListDumpType


def hdf5_has_concepts_extension(fi_path: pathlib.Path) -> bool:
    return has_concepts_extension(fi_path)


def _compute_ancestors_bfs(
    code: str, parent_map: dict[str, set[str]]
) -> dict[str, int]:
    distances = {}
    queue = deque((parent, 1) for parent in sorted(parent_map.get(code, set())))
    while queue:
        ancestor, distance = queue.popleft()
        if ancestor in distances and distances[ancestor] <= distance:
            continue
        distances[ancestor] = distance
        queue.extend(
            (parent, distance + 1)
            for parent in sorted(parent_map.get(ancestor, set()))
        )
    return distances


def _compute_ancestors_memoized(
    code: str,
    parent_map: dict[str, set[str]],
    memo: dict[str, dict[str, int]],
    visiting: Optional[set[str]] = None,
) -> dict[str, int]:
    if code in memo:
        return memo[code]
    if visiting is None:
        visiting = set()
    if code in visiting:
        return {}

    visiting.add(code)
    distances = {}
    for parent in sorted(parent_map.get(code, set())):
        if parent not in distances or distances[parent] > 1:
            distances[parent] = 1
        for ancestor, distance in _compute_ancestors_memoized(
            parent, parent_map, memo, visiting
        ).items():
            candidate_distance = distance + 1
            if (
                ancestor not in distances
                or distances[ancestor] > candidate_distance
            ):
                distances[ancestor] = candidate_distance
    visiting.remove(code)
    memo[code] = distances
    return distances


def _compute_compact_ancestor_arrays(
    id_to_fsn_dict: dict[str, str],
    parent_map: dict[str, set[str]],
    use_memoization: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    all_codes = sorted(
        set(id_to_fsn_dict.keys())
        | set(parent_map.keys())
        | {parent for parents in parent_map.values() for parent in parents}
    )
    ancestor_codes_flat = []
    ancestor_distances_flat = []
    ancestor_index = []

    memo = {} if use_memoization else None
    for code in all_codes:
        start = len(ancestor_codes_flat)
        distances = (
            _compute_ancestors_memoized(code, parent_map, memo)
            if use_memoization
            else _compute_ancestors_bfs(code, parent_map)
        )

        for ancestor, distance in sorted(distances.items(), key=lambda x: (x[1], x[0])):
            ancestor_codes_flat.append(ancestor)
            ancestor_distances_flat.append(distance)
        ancestor_index.append((start, len(ancestor_codes_flat) - start))

    return (
        np.asarray(all_codes, dtype=np.dtypes.StringDType),
        np.asarray(ancestor_index, dtype=np.int64),
        np.asarray(ancestor_codes_flat, dtype=np.dtypes.StringDType),
        np.asarray(ancestor_distances_flat, dtype=np.int32),
    )


def _write_concepts_extension(
    fi: h5py.File,
    id_to_fsn_dict: dict[str, str],
    parent_map: dict[str, set[str]],
    force_overwrite: bool = False,
    use_memoization: bool = False,
):
    if "concepts" in fi:
        if force_overwrite:
            del fi["concepts"]
        else:
            logging.warning(
                "HDF5 concepts extension already exists and 'force_overwrite_concepts' is FALSE. Skipping."
            )
            return

    codes, ancestor_index, ancestor_codes, ancestor_distances = (
        _compute_compact_ancestor_arrays(
            id_to_fsn_dict, parent_map, use_memoization=use_memoization
        )
    )
    concept_group = fi.create_group("concepts")
    fsn = np.asarray(
        [id_to_fsn_dict.get(code, "") for code in codes],
        dtype=np.dtypes.StringDType,
    )

    ds_codes = concept_group.create_dataset("codes", shape=(codes.shape[0],), dtype="T")
    ds_codes[:] = codes
    ds_fsn = concept_group.create_dataset("fsn", shape=(fsn.shape[0],), dtype="T")
    ds_fsn[:] = fsn
    code_to_index = {str(code): idx for idx, code in enumerate(codes.tolist())}
    concept_group.create_dataset("ancestors_index", data=ancestor_index.astype(np.int32))
    concept_group.create_dataset(
        "ancestor_concept_index",
        data=np.asarray([code_to_index[str(code)] for code in ancestor_codes.tolist()], dtype=np.int32),
    )
    concept_group.create_dataset("ancestor_distance", data=ancestor_distances.astype(np.int16))


def dump_codes_to_hdf5(
    fi_path: pathlib.Path,
    codes: set,
    id_to_fsn_dict: dict[str, str],
    list_type: ListDumpType,
    revision: bool = True,
    force_overwrite: bool = False,
    parent_map: Optional[dict[str, set[str]]] = None,
    use_memoization: bool = False,
    force_overwrite_concepts: bool = False,
):
    def _create_dataset(
        fi: h5py.File, name: str, content: Union[set, list, np.ndarray], mappings: dict
    ):
        if name in fi:
            group = fi[f"/{name}"]
        else:
            group = fi.create_group(name)

        _last = (
            sorted(int(k) for k in group.keys())[-1] if len(group.keys()) > 0 else -1
        )
        last_group = group.create_group(str(_last + 1))

        code_data = (
            np.array(sorted(content))
            if not isinstance(content, np.ndarray)
            else content
        )
        fsn_data = np.array(
            [
                mappings.get(code)
                for code in (
                    sorted(content) if not isinstance(content, np.ndarray) else content
                )
            ]
        )

        ds_codes = last_group.create_dataset(
            "codes", shape=(code_data.shape[0],), dtype="T"
        )
        ds_codes[:] = code_data
        fs_codes = last_group.create_dataset(
            "fsn", shape=(fsn_data.shape[0],), dtype="T"
        )
        fs_codes[:] = fsn_data

    dataset_name = list_type.name.lower()
    file_exists = False
    if fi_path.exists():
        file_exists = True

    with h5py.File(str(fi_path.resolve()), "r+" if file_exists else "a") as f:
        dataset_exists = dataset_name in f.keys()

        if file_exists and dataset_exists and not (force_overwrite or revision):
            logging.error(f"Dataset '{dataset_name}' already exists.")
            return

        if not file_exists:
            _create_dataset(f, dataset_name, codes, id_to_fsn_dict)
        else:
            if dataset_exists:
                if force_overwrite:
                    del f[dataset_name]
                    _create_dataset(f, dataset_name, codes, id_to_fsn_dict)
                elif revision:
                    # ToDo: Implement revision
                    logging.warning(
                        f"Dataset '{dataset_name}' already exists and 'force_overwrite' is FALSE. Revision is not yet implemented. Skipping."
                    )
            else:
                _create_dataset(f, dataset_name, codes, id_to_fsn_dict)

        if parent_map is not None:
            _write_concepts_extension(
                f,
                id_to_fsn_dict,
                parent_map,
                force_overwrite=force_overwrite_concepts,
                use_memoization=use_memoization,
            )
