"""HDF5 writer for SNOMED CT release ingestion."""

from __future__ import annotations

import logging
import pathlib
import zipfile
from typing import Iterable, Optional, Union

import h5py
import numpy as np

from ..hdf5_handling.dump import _compute_compact_ancestor_arrays
from .discovery import discover_release_members
from .models import Rf2IngestionSummary
from .readers import (
    _read_active_associations,
    _read_active_parent_map,
    _read_concept_active_state,
    _read_fsns,
    _semantic_tag_from_fsn,
)


def _write_string_dataset(group: h5py.Group, name: str, values: Iterable[str]):
    data = np.asarray(list(values), dtype=np.dtypes.StringDType)
    dataset = group.create_dataset(name, shape=(data.shape[0],), dtype="T")
    dataset[:] = data


def _write_int_dataset(group: h5py.Group, name: str, values: Iterable[int]):
    data = np.asarray(list(values), dtype=np.int64)
    group.create_dataset(name, data=data)


def _descendants_or_self(root_codes: Iterable[str], parent_map: dict[str, set[str]]) -> set[str]:
    children_by_parent: dict[str, set[str]] = {}
    for child, parents in parent_map.items():
        for parent in parents:
            children_by_parent.setdefault(parent, set()).add(child)

    result: set[str] = set()
    stack = list(root_codes)
    while stack:
        code = stack.pop()
        if code in result:
            continue
        result.add(code)
        stack.extend(sorted(children_by_parent.get(code, set())))
    return result


def _categorical_ids(values: list[str]) -> tuple[list[str], list[int]]:
    categories = sorted(set(values))
    category_to_id = {value: idx for idx, value in enumerate(categories)}
    return categories, [category_to_id[value] for value in values]


def _write_legacy_policy_group(
    h5_file: h5py.File,
    group_name: str,
    policy_codes: list[str],
    fsn_by_code: dict[str, str],
    force_overwrite: bool,
):
    group = _replace_group(h5_file, group_name, force_overwrite)
    version_group = group.create_group("0")
    _write_string_dataset(version_group, "codes", policy_codes)
    _write_string_dataset(
        version_group, "fsn", (fsn_by_code.get(code, "") for code in policy_codes)
    )


def _write_policy_view(
    policy_views_group: h5py.Group,
    policy_name: str,
    concept_indices: list[int],
    *,
    root_codes: Optional[Iterable[str]] = None,
    filter_tags: Optional[Iterable[str]] = None,
    filter_mode: str = "positive",
    policy_date: Optional[str] = None,
    release_date: Optional[str] = None,
    rf2_view: str = "snapshot",
    force_overwrite: bool = False,
):
    if policy_name in policy_views_group:
        if not force_overwrite:
            raise ValueError(
                f"HDF5 policy view '/policy_views/{policy_name}' already exists. Use --force-overwrite to replace it."
            )
        del policy_views_group[policy_name]
    group = policy_views_group.create_group(policy_name).create_group("0")
    _write_int_dataset(group, "concept_index", concept_indices)
    _write_string_dataset(group, "root_codes", root_codes or [])
    _write_string_dataset(group, "filter_tags", filter_tags or [])
    group.attrs["filter_mode"] = filter_mode
    group.attrs["storage"] = "concept_index"
    group.attrs["rf2_view"] = rf2_view
    if policy_date is not None:
        group.attrs["policy_date"] = policy_date
    if release_date is not None:
        group.attrs["release_date"] = release_date


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
    rf2_view: str = "snapshot",
    include_associations: bool = True,
    include_ancestors: bool = False,
    whitelist_root_codes: Optional[Iterable[str]] = None,
    blacklist_filter_tags: Optional[Iterable[str]] = None,
    blacklist_root_codes: Optional[Iterable[str]] = None,
    policy_date: Optional[str] = None,
    write_legacy_policy_groups: bool = False,
    force_overwrite: bool = False,
    force_overwrite_concepts: bool = False,
    use_memoization: bool = False,
) -> Rf2IngestionSummary:
    """Create an enriched HDF5 file from RF2 Snapshot files in a ZIP.

    The output currently writes:

    ```text
    /concepts/codes
    /concepts/fsn
    /concepts/semantic_tag_id
    /concepts/semantic_tags
    /concepts/active
    /historical_associations/source_index
    /historical_associations/target_index
    /historical_associations/association_type_id
    /historical_associations/association_types
    /historical_associations/effective_time
    /historical_associations/active
    /historical_associations/refset_id
    /policy_views/whitelist/0/concept_index
    /policy_views/blacklist/0/concept_index
    ```

    If ``include_ancestors`` is true, compact ancestor arrays compatible with
    the existing concept extension are added under `/concepts`.
    """
    zip_path = pathlib.Path(zip_path)
    output_path = pathlib.Path(output_path)
    rf2_view = rf2_view.lower()
    if rf2_view not in {"snapshot", "full"}:
        raise ValueError("rf2_view must be either 'snapshot' or 'full'.")
    members = discover_release_members(zip_path, language=language, view=rf2_view)
    if rf2_view == "snapshot" and policy_date is not None and policy_date != members.release_date:
        raise ValueError(
            "RF2 Snapshot mode can only create policy views for the Snapshot release date "
            f"{members.release_date}; got policy_date={policy_date}. Use a matching Snapshot "
            "or RF2 Full reconstruction for earlier policy dates."
        )
    if rf2_view == "full" and policy_date is not None and policy_date > members.release_date:
        raise ValueError(
            f"RF2 Full mode cannot reconstruct future policy_date={policy_date} from release_date={members.release_date}."
        )
    policy_date = policy_date or members.release_date
    reconstruct_latest = rf2_view == "full"
    whitelist_root_codes = list(whitelist_root_codes or [])
    blacklist_filter_tags = list(blacklist_filter_tags or [])
    blacklist_root_codes = list(blacklist_root_codes or [])

    with zipfile.ZipFile(zip_path) as zf:
        logging.info("Reading RF2 %s concept active state from %s", members.view, members.concept)
        concept_active = _read_concept_active_state(
            zf,
            members.concept,
            policy_date=policy_date,
            reconstruct_latest=reconstruct_latest,
        )
        active_concepts = {code for code, active in concept_active.items() if active}

        associations = []
        if include_associations:
            logging.info("Reading active RF2 %s associations from %s", members.view, members.association)
            associations = _read_active_associations(
                zf,
                members.association,
                policy_date=policy_date,
                reconstruct_latest=reconstruct_latest,
            )

        parent_map: dict[str, set[str]] = {}
        need_relationships = include_ancestors or bool(whitelist_root_codes) or bool(blacklist_root_codes)
        if need_relationships:
            logging.info("Reading active RF2 %s is-a relationships from %s", members.view, members.relationship)
            parent_map = _read_active_parent_map(
                zf,
                members.relationship,
                active_concepts,
                policy_date=policy_date,
                reconstruct_latest=reconstruct_latest,
            )

        all_concept_codes = active_concepts | {a[0] for a in associations} | {a[1] for a in associations}
        logging.info("Reading RF2 %s FSNs from %s", members.view, members.description)
        fsn_by_code = _read_fsns(
            zf,
            members.description,
            all_concept_codes,
            policy_date=policy_date,
            reconstruct_latest=reconstruct_latest,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(output_path, "a") as h5_file:
        if "concepts" in h5_file and not force_overwrite_concepts:
            concept_group = h5_file["concepts"]
            existing_policy_date = concept_group.attrs.get("policy_date")
            existing_release_date = concept_group.attrs.get("release_date")
            existing_rf2_view = concept_group.attrs.get("rf2_view")
            if existing_policy_date is not None and existing_policy_date != policy_date:
                raise ValueError(
                    f"Existing /concepts policy_date={existing_policy_date!r} does not match requested policy_date={policy_date!r}. Use --force-overwrite-concepts to rebuild it."
                )
            if existing_release_date is not None and existing_release_date != members.release_date:
                raise ValueError(
                    f"Existing /concepts release_date={existing_release_date!r} does not match RF2 release_date={members.release_date!r}. Use --force-overwrite-concepts to rebuild it."
                )
            if existing_rf2_view is not None and existing_rf2_view != rf2_view:
                raise ValueError(
                    f"Existing /concepts rf2_view={existing_rf2_view!r} does not match requested rf2_view={rf2_view!r}. Use --force-overwrite-concepts to rebuild it."
                )
            codes = [code.decode("utf-8") if isinstance(code, bytes) else str(code) for code in concept_group["codes"][:]]
            code_to_index = {code: idx for idx, code in enumerate(codes)}
            missing_codes = sorted(all_concept_codes - set(codes))
            if missing_codes:
                raise ValueError(
                    f"Existing /concepts group is missing {len(missing_codes)} code(s) needed for this RF2 run. Use --force-overwrite-concepts to rebuild it."
                )
            fsn_values = [fsn.decode("utf-8") if isinstance(fsn, bytes) else str(fsn) for fsn in concept_group["fsn"][:]]
            if "semantic_tag_id" in concept_group and "semantic_tags" in concept_group:
                semantic_tags_existing = [tag.decode("utf-8") if isinstance(tag, bytes) else str(tag) for tag in concept_group["semantic_tags"][:]]
                semantic_tag_values = [semantic_tags_existing[idx] for idx in concept_group["semantic_tag_id"][:]]
            else:
                semantic_tag_values = [_semantic_tag_from_fsn(fsn) for fsn in fsn_values]
            logging.warning("HDF5 concepts group already exists and force_overwrite_concepts is FALSE. Reusing it.")
        else:
            concept_group = _replace_group(h5_file, "concepts", force_overwrite_concepts)
            codes = sorted(all_concept_codes)
            code_to_index = {code: idx for idx, code in enumerate(codes)}
            fsn_values = [fsn_by_code.get(code, "") for code in codes]
            semantic_tag_values = [_semantic_tag_from_fsn(fsn) for fsn in fsn_values]
            semantic_tags, semantic_tag_ids = _categorical_ids(semantic_tag_values)
            _write_string_dataset(concept_group, "codes", codes)
            _write_string_dataset(concept_group, "fsn", fsn_values)
            _write_int_dataset(concept_group, "semantic_tag_id", semantic_tag_ids)
            _write_string_dataset(concept_group, "semantic_tags", semantic_tags)
            concept_group.create_dataset(
                "active", data=np.asarray([concept_active.get(code, False) for code in codes], dtype=bool)
            )
            concept_group.attrs["policy_date"] = policy_date
            concept_group.attrs["release_date"] = members.release_date
            concept_group.attrs["rf2_view"] = rf2_view

        new_ancestor_datasets = {"ancestors_index", "ancestor_concept_index", "ancestor_distance"}
        if include_ancestors:
            for legacy_dataset_name in ("ancestors_codes", "ancestors_distance"):
                if legacy_dataset_name in concept_group:
                    del concept_group[legacy_dataset_name]
        if include_ancestors and not new_ancestor_datasets.issubset(concept_group.keys()):
            for dataset_name in (
                "ancestors_index",
                "ancestor_concept_index",
                "ancestor_distance",
                "ancestors_codes",
                "ancestors_distance",
            ):
                if dataset_name in concept_group:
                    del concept_group[dataset_name]
            ancestor_codes_base, ancestor_index, ancestor_codes, ancestor_distances = (
                _compute_compact_ancestor_arrays(
                    {code: fsn_by_code.get(code, "") for code in all_concept_codes},
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
            ancestor_code_to_index = {code: idx for idx, code in enumerate(codes)}
            concept_group.create_dataset("ancestors_index", data=ancestor_index.astype(np.int32))
            concept_group.create_dataset(
                "ancestor_concept_index",
                data=np.asarray([ancestor_code_to_index[str(code)] for code in ancestor_codes], dtype=np.int32),
            )
            concept_group.create_dataset("ancestor_distance", data=ancestor_distances.astype(np.int16))

        if include_associations and "historical_associations" not in h5_file:
            assoc_group = h5_file.create_group("historical_associations")
            association_types, association_type_ids = _categorical_ids([a[2] for a in associations])
            _write_int_dataset(assoc_group, "source_index", (code_to_index[a[0]] for a in associations))
            _write_int_dataset(assoc_group, "target_index", (code_to_index[a[1]] for a in associations))
            _write_int_dataset(assoc_group, "association_type_id", association_type_ids)
            _write_string_dataset(assoc_group, "association_types", association_types)
            _write_string_dataset(assoc_group, "effective_time", (a[3] for a in associations))
            assoc_group.create_dataset(
                "active", data=np.ones((len(associations),), dtype=bool)
            )
            _write_string_dataset(assoc_group, "refset_id", (a[4] for a in associations))

        whitelist_codes: list[str] = []
        blacklist_codes: list[str] = []
        if whitelist_root_codes or blacklist_filter_tags or blacklist_root_codes:
            policy_views_group = (
                h5_file["policy_views"]
                if "policy_views" in h5_file
                else h5_file.create_group("policy_views")
            )
            if whitelist_root_codes:
                whitelist_code_set = _descendants_or_self(whitelist_root_codes, parent_map) & active_concepts
                whitelist_codes = sorted(whitelist_code_set)
                _write_policy_view(
                    policy_views_group,
                    "whitelist",
                    [code_to_index[code] for code in whitelist_codes],
                    root_codes=whitelist_root_codes,
                    filter_mode="descendants_or_self",
                    policy_date=policy_date,
                    release_date=members.release_date,
                    rf2_view=rf2_view,
                    force_overwrite=force_overwrite,
                )
                if write_legacy_policy_groups:
                    _write_legacy_policy_group(
                        h5_file, "whitelist", whitelist_codes, fsn_by_code, force_overwrite
                    )
            if blacklist_filter_tags or blacklist_root_codes:
                blacklist_filter_tags_set = set(blacklist_filter_tags)
                blacklist_code_set = {
                    code
                    for code, tag in zip(codes, semantic_tag_values)
                    if concept_active.get(code, False) and tag in blacklist_filter_tags_set
                }
                blacklist_code_set.update(
                    _descendants_or_self(blacklist_root_codes, parent_map) & active_concepts
                )
                blacklist_codes = sorted(blacklist_code_set)
                _write_policy_view(
                    policy_views_group,
                    "blacklist",
                    [code_to_index[code] for code in blacklist_codes],
                    root_codes=blacklist_root_codes,
                    filter_tags=sorted(blacklist_filter_tags_set),
                    filter_mode="semantic_tag_or_descendants_positive",
                    policy_date=policy_date,
                    release_date=members.release_date,
                    rf2_view=rf2_view,
                    force_overwrite=force_overwrite,
                )
                if write_legacy_policy_groups:
                    _write_legacy_policy_group(
                        h5_file, "blacklist", blacklist_codes, fsn_by_code, force_overwrite
                    )

    return Rf2IngestionSummary(
        output_path=output_path,
        concept_count=len(codes),
        fsn_count=len(fsn_by_code),
        association_count=len(associations),
        relationship_parent_count=sum(len(v) for v in parent_map.values()),
        whitelist_count=len(whitelist_codes),
        blacklist_count=len(blacklist_codes),
        files=members,
    )
