"""HDF5 dump creation pipeline for RF2 release ZIPs and Snowstorm."""

from __future__ import annotations

import datetime
import logging
import os
import pathlib
import pickle
import re
import sys
import zipfile
from typing import Optional, Union

import click
import yaspin
from scttsrapy.api import EndpointBuilder

from ..cli import set_log_level
from ..hdf5_handling.dump import dump_codes_to_hdf5, hdf5_has_concepts_extension
from ..release_ingestion import write_snapshot_hdf5_from_rf2_zip
from ..snomed import DumpMode, FilterMode, ListDumpType
from ..snowstorm import build_endpoint, dump_concept_ids, get_branches, get_root_code


def run_create_concept_id_dump(
    root_code: str,
    rf2_zip: Optional[pathlib.Path],
    output: Optional[pathlib.Path],
    language: str,
    include_ancestors: bool,
    policy_date: Optional[str],
    rf2_view: str,
    write_legacy_policy_groups: bool,
    use_secure_protocol: bool,
    port: Optional[int],
    ip: Optional[str],
    branch: Union[int, str],
    dump_mode: DumpMode,
    filter_list: Union[str, click.File],
    filter_mode: FilterMode,
    not_recursive: bool,
    force_overwrite: bool,
    force_overwrite_concepts: bool,
    memoize_ancestors: bool,
    log_level: str,
):
    """Create a SNOMED CT HDF5 policy dump from an RF2 ZIP or Snowstorm."""
    set_log_level(log_level)

    use_rf2_zip = rf2_zip is not None
    _validate_source_mode(use_rf2_zip, ip, port)

    if use_rf2_zip:
        _run_rf2_zip_dump(
            root_code=root_code,
            rf2_zip=rf2_zip,
            output=output,
            language=language,
            include_ancestors=include_ancestors,
            policy_date=policy_date,
            rf2_view=rf2_view,
            write_legacy_policy_groups=write_legacy_policy_groups,
            dump_mode=dump_mode,
            filter_list=filter_list,
            force_overwrite=force_overwrite,
            force_overwrite_concepts=force_overwrite_concepts,
            memoize_ancestors=memoize_ancestors,
        )
        return

    _run_snowstorm_dump(
        root_code=root_code,
        use_secure_protocol=use_secure_protocol,
        port=port,
        ip=ip,
        branch=branch,
        dump_mode=dump_mode,
        filter_list=filter_list,
        filter_mode=filter_mode,
        not_recursive=not_recursive,
        force_overwrite=force_overwrite,
        force_overwrite_concepts=force_overwrite_concepts,
        memoize_ancestors=memoize_ancestors,
    )


def _validate_source_mode(use_rf2_zip: bool, ip: Optional[str], port: Optional[int]) -> None:
    use_snowstorm = ip is not None or port is not None
    if use_rf2_zip and use_snowstorm:
        logging.error("Use either --zip for RF2 ZIP mode or --ip/--port for Snowstorm mode, not both.")
        sys.exit(-1)
    if not use_rf2_zip and (ip is None or port is None):
        logging.error("Please provide either --zip for RF2 ZIP mode or both --ip and --port for Snowstorm mode.")
        sys.exit(-1)


def _run_rf2_zip_dump(
    *,
    root_code: str,
    rf2_zip: pathlib.Path,
    output: Optional[pathlib.Path],
    language: str,
    include_ancestors: bool,
    policy_date: Optional[str],
    rf2_view: str,
    write_legacy_policy_groups: bool,
    dump_mode: DumpMode,
    filter_list: Union[str, click.File],
    force_overwrite: bool,
    force_overwrite_concepts: bool,
    memoize_ancestors: bool,
) -> None:
    code_filter = _read_optional_filter_list(filter_list)
    blacklist_root_codes, blacklist_filter_tags = _split_rf2_blacklist_filters(code_filter)
    whitelist_root_codes = _rf2_whitelist_roots(root_code, dump_mode, code_filter)
    output = output or _default_rf2_output_path(rf2_zip)

    try:
        summary = write_snapshot_hdf5_from_rf2_zip(
            zip_path=rf2_zip,
            output_path=output,
            language=language,
            rf2_view=rf2_view,
            include_associations=True,
            include_ancestors=include_ancestors,
            whitelist_root_codes=whitelist_root_codes,
            blacklist_filter_tags=blacklist_filter_tags,
            blacklist_root_codes=blacklist_root_codes,
            policy_date=policy_date,
            write_legacy_policy_groups=write_legacy_policy_groups,
            force_overwrite=force_overwrite,
            force_overwrite_concepts=force_overwrite_concepts,
            use_memoization=memoize_ancestors,
        )
    except Exception as e:
        logging.error(f"Error while creating RF2 HDF5 dump: '{e}'. Exiting.")
        sys.exit(-1)

    logging.info(
        f"Created RF2 HDF5 dump at '{summary.output_path}' with {summary.concept_count} concept row(s), "
        f"{summary.association_count} historical association(s), {summary.whitelist_count} whitelist policy concept(s), "
        f"and {summary.blacklist_count} blacklist policy concept(s)."
    )


def _read_optional_filter_list(filter_list: Union[str, click.File]) -> Optional[list[str]]:
    if len(filter_list) == 0:
        return None
    code_filter = _read_filter_list(filter_list, semantic_safety=False)
    if not code_filter:
        logging.error("RF2 ZIP mode got an empty filter list.")
        sys.exit(-1)
    return code_filter


def _read_required_semantic_filter_list(filter_list: Union[str, click.File]) -> list[str]:
    if len(filter_list) < 1:
        logging.error(
            "Semantic dump mode requires at least one '--filter-list' entry or a valid filter-list file. Exiting to avoid creating a full blacklist."
        )
        sys.exit(-1)

    code_filter = _read_filter_list(filter_list, semantic_safety=True)
    if len(code_filter) == 0:
        logging.error(
            "Semantic dump mode got an empty filter list. Exiting to avoid creating a full blacklist."
        )
        sys.exit(-1)

    logging.info(f"Using filter list: '{[c for c in code_filter]}'.")
    return code_filter


def _read_filter_list(
    filter_list: Union[str, click.File],
    *,
    semantic_safety: bool,
) -> list[str]:
    fi = pathlib.Path(filter_list[0])
    if fi.is_file():
        return [
            line.strip()
            for line in fi.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    if os.sep in str(fi):
        message = f"Filter-list path does not exist or is not a file: '{fi}'."
        if semantic_safety:
            message += " Exiting to avoid creating a full blacklist."
        logging.error(message)
        sys.exit(-1)
    return [str(item).strip() for item in filter_list if str(item).strip()]


def _split_rf2_blacklist_filters(code_filter: Optional[list[str]]) -> tuple[list[str], list[str]]:
    if not code_filter:
        return [], []
    return (
        [item for item in code_filter if item.isdigit()],
        [item for item in code_filter if not item.isdigit()],
    )


def _rf2_whitelist_roots(
    root_code: str,
    dump_mode: DumpMode,
    code_filter: Optional[list[str]],
) -> Optional[list[str]]:
    if dump_mode != DumpMode.SEMANTIC:
        return [root_code]
    if not code_filter:
        logging.error(
            "RF2 semantic blacklist mode requires at least one '--filter-list' entry or a valid filter-list file."
        )
        sys.exit(-1)
    return None


def _default_rf2_output_path(rf2_zip: pathlib.Path) -> pathlib.Path:
    release_date = _detect_rf2_release_date(rf2_zip)
    return (
        pathlib.Path(__file__).parents[3]
        / "data"
        / f"gemtex_snomedct_codes_{release_date}.hdf5"
    ).resolve()


def _detect_rf2_release_date(rf2_zip: pathlib.Path) -> str:
    with zipfile.ZipFile(rf2_zip) as zf:
        for member_name in zf.namelist():
            release_match = re.search(r"_(\d{8})\.txt$", member_name)
            if release_match:
                return release_match.group(1)

    release_match = re.search(r"(\d{8})(?:T\d{6}Z)?", rf2_zip.name)
    if release_match:
        return release_match.group(1)
    return datetime.datetime.today().strftime("%Y%m%d")


def _run_snowstorm_dump(
    *,
    root_code: str,
    use_secure_protocol: bool,
    port: int,
    ip: str,
    branch: Union[int, str],
    dump_mode: DumpMode,
    filter_list: Union[str, click.File],
    filter_mode: FilterMode,
    not_recursive: bool,
    force_overwrite: bool,
    force_overwrite_concepts: bool,
    memoize_ancestors: bool,
) -> None:
    endpoint_builder, host = build_endpoint(ip, port, use_secure_protocol)
    _select_snowstorm_branch(endpoint_builder, host, branch)

    code_filter = None
    if dump_mode == DumpMode.SEMANTIC:
        code_filter = _read_required_semantic_filter_list(filter_list)

    hdf5_path = _snowstorm_hdf5_path(endpoint_builder)
    concepts_extension_exists = hdf5_has_concepts_extension(hdf5_path)
    collect_parent_map = force_overwrite_concepts or not concepts_extension_exists
    if not collect_parent_map:
        logging.info(
            f"HDF5 concepts extension already exists in '{hdf5_path}'. Skipping parent-map collection during traversal."
        )

    codes, id_to_fsn_dict, parent_map = _collect_snowstorm_codes(
        root_code=root_code,
        endpoint_builder=endpoint_builder,
        code_filter=code_filter,
        filter_mode=filter_mode,
        dump_mode=dump_mode,
        not_recursive=not_recursive,
        collect_parent_map=collect_parent_map,
    )
    _write_snowstorm_hdf5(
        hdf5_path=hdf5_path,
        codes=codes,
        id_to_fsn_dict=id_to_fsn_dict,
        parent_map=parent_map if collect_parent_map else None,
        dump_mode=dump_mode,
        force_overwrite=force_overwrite,
        force_overwrite_concepts=force_overwrite_concepts,
        memoize_ancestors=memoize_ancestors,
    )


def _select_snowstorm_branch(
    endpoint_builder: EndpointBuilder,
    host: str,
    branch: Union[int, str],
) -> None:
    path_ids, path_names = get_branches(endpoint_builder, host)

    if isinstance(branch, int):
        path = path_ids.get("path", {}).get(branch, None)
    elif isinstance(branch, str):
        path = branch if branch in path_names else None
    else:
        path = None

    if path is None:
        fallback_path = path_ids.get("path", {}).get(0, None)
        if fallback_path is None:
            logging.error(f"Could not find branch '{branch}'. Exiting.")
            sys.exit(-1)
        logging.warning(
            f"Branch not found: '{branch}'. Trying to use first one found '{fallback_path}'."
        )
        path = fallback_path
    else:
        logging.info(f"Using branch: '{path}'.")

    endpoint_builder.set_branch(path)


def _snowstorm_hdf5_path(endpoint_builder: EndpointBuilder) -> pathlib.Path:
    return (
        pathlib.Path(__file__).parents[3]
        / "data"
        / f"gemtex_snomedct_codes_{endpoint_builder.branch.split('/')[-1]}.hdf5"
    ).resolve()


def _collect_snowstorm_codes(
    *,
    root_code: str,
    endpoint_builder: EndpointBuilder,
    code_filter: Optional[list[str]],
    filter_mode: FilterMode,
    dump_mode: DumpMode,
    not_recursive: bool,
    collect_parent_map: bool,
):
    with yaspin.yaspin(text="Processing..."):
        root = get_root_code(root_code, endpoint_builder)
        if root is None:
            logging.error(f"Could not find root code '{root_code}'. Exiting.")
            sys.exit(-1)
        id_hash_set, id_to_fsn_dict, parent_map = dump_concept_ids(
            root_concept=root,
            endpoint_builder=endpoint_builder,
            filter_list=code_filter,
            filter_mode=filter_mode,
            dump_mode=dump_mode,
            is_not_recursive=not_recursive,
            collect_parent_map=collect_parent_map,
        )
    return set(id_hash_set), id_to_fsn_dict, parent_map


def _write_snowstorm_hdf5(
    *,
    hdf5_path: pathlib.Path,
    codes: set,
    id_to_fsn_dict: dict,
    parent_map: Optional[dict],
    dump_mode: DumpMode,
    force_overwrite: bool,
    force_overwrite_concepts: bool,
    memoize_ancestors: bool,
) -> None:
    hdf5_path.parent.mkdir(exist_ok=True, parents=True)
    try:
        dump_codes_to_hdf5(
            fi_path=hdf5_path,
            codes=codes,
            id_to_fsn_dict=id_to_fsn_dict,
            list_type=ListDumpType.BLACKLIST
            if dump_mode == DumpMode.SEMANTIC
            else ListDumpType.WHITELIST,
            revision=not force_overwrite,
            force_overwrite=force_overwrite,
            parent_map=parent_map,
            use_memoization=memoize_ancestors,
            force_overwrite_concepts=force_overwrite_concepts,
        )
    except Exception as e:
        logging.error(f"Error while creating hdf5 dump: '{e}'. Exiting.")
        pickle_path = hdf5_path.with_name(
            f"{hdf5_path.stem}-{dump_mode.name.lower()}.pickle"
        )
        logging.error(f"Dumping as pickle file: '{pickle_path}'.")
        with pickle_path.open("wb") as pickle_fi:
            pickle.dump(codes, pickle_fi)
