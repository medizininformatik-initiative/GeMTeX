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

from ..cli import set_log_level
from ..release_ingestion import write_snapshot_hdf5_from_rf2_zip
from ..snowstorm_funcs import build_endpoint, dump_concept_ids, get_branches, get_root_code
from ..utils import (
    DumpMode,
    FilterMode,
    ListDumpType,
    dump_codes_to_hdf5,
    hdf5_has_concepts_extension,
)


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
    use_snowstorm = ip is not None or port is not None
    if use_rf2_zip and use_snowstorm:
        logging.error("Use either --zip for RF2 ZIP mode or --ip/--port for Snowstorm mode, not both.")
        sys.exit(-1)
    if not use_rf2_zip and (ip is None or port is None):
        logging.error("Please provide either --zip for RF2 ZIP mode or both --ip and --port for Snowstorm mode.")
        sys.exit(-1)

    if use_rf2_zip:
        code_filter = None
        if len(filter_list) > 0:
            fi = pathlib.Path(filter_list[0])
            if fi.is_file():
                code_filter = [
                    line.strip()
                    for line in fi.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            else:
                if os.sep in str(fi):
                    logging.error(f"Filter-list path does not exist or is not a file: '{fi}'.")
                    sys.exit(-1)
                code_filter = [str(item).strip() for item in filter_list if str(item).strip()]
            if not code_filter:
                logging.error("RF2 ZIP mode got an empty filter list.")
                sys.exit(-1)

        blacklist_root_codes = []
        blacklist_filter_tags = []
        if code_filter:
            blacklist_root_codes = [item for item in code_filter if item.isdigit()]
            blacklist_filter_tags = [item for item in code_filter if not item.isdigit()]

        if dump_mode == DumpMode.SEMANTIC:
            if not code_filter:
                logging.error(
                    "RF2 semantic blacklist mode requires at least one '--filter-list' entry or a valid filter-list file."
                )
                sys.exit(-1)
            whitelist_root_codes = None
        else:
            whitelist_root_codes = [root_code]

        if output is None:
            release_date = None
            with zipfile.ZipFile(rf2_zip) as zf:
                for member_name in zf.namelist():
                    release_match = re.search(r"_(\d{8})\.txt$", member_name)
                    if release_match:
                        release_date = release_match.group(1)
                        break
            if release_date is None:
                release_match = re.search(r"(\d{8})(?:T\d{6}Z)?", rf2_zip.name)
                release_date = release_match.group(1) if release_match else datetime.datetime.today().strftime("%Y%m%d")
            output = (
                pathlib.Path(__file__).parents[3]
                / "data"
                / f"gemtex_snomedct_codes_{release_date}.hdf5"
            ).resolve()

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
        return

    endpoint_builder, host = build_endpoint(ip, port, use_secure_protocol)
    path_ids, path_names = get_branches(endpoint_builder, host)

    if isinstance(branch, int):
        path = path_ids.get("path", {}).get(branch, None)
    elif isinstance(branch, str):
        if branch not in path_names:
            path = None
        else:
            path = branch
    else:
        path = None

    if path is None:
        _p = path_ids.get("path", {}).get(0, None)
        if _p is None:
            logging.error(f"Could not find branch '{branch}'. Exiting.")
            sys.exit(-1)
        logging.warning(
            f"Branch not found: '{branch}'. Trying to use first one found '{_p}'."
        )
        path = _p
    else:
        logging.info(f"Using branch: '{path}'.")

    endpoint_builder.set_branch(path)

    code_filter = None
    if dump_mode == DumpMode.SEMANTIC:
        if len(filter_list) < 1:
            logging.error(
                "Semantic dump mode requires at least one '--filter-list' entry or a valid filter-list file. Exiting to avoid creating a full blacklist."
            )
            sys.exit(-1)

        fi = pathlib.Path(filter_list[0])
        if fi.is_file():
            code_filter = [
                line.strip()
                for line in fi.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            if os.sep in str(fi):
                logging.error(
                    f"Filter-list path does not exist or is not a file: '{fi}'. Exiting to avoid creating a full blacklist."
                )
                sys.exit(-1)
            code_filter = [str(item).strip() for item in filter_list if str(item).strip()]

        if len(code_filter) == 0:
            logging.error(
                "Semantic dump mode got an empty filter list. Exiting to avoid creating a full blacklist."
            )
            sys.exit(-1)

        logging.info(f"Using filter list: '{[c for c in code_filter]}'.")

    hdf5_path = (
        pathlib.Path(__file__).parents[3]
        / "data"
        / f"gemtex_snomedct_codes_{endpoint_builder.branch.split('/')[-1]}.hdf5"
    ).resolve()
    concepts_extension_exists = hdf5_has_concepts_extension(hdf5_path)
    collect_parent_map = force_overwrite_concepts or not concepts_extension_exists
    if not collect_parent_map:
        logging.info(
            f"HDF5 concepts extension already exists in '{hdf5_path}'. Skipping parent-map collection during traversal."
        )

    with yaspin.yaspin(text="Processing..."):
        if root := get_root_code(root_code, endpoint_builder):
            id_hash_set, id_to_fsn_dict, parent_map = dump_concept_ids(
                root_concept=root,
                endpoint_builder=endpoint_builder,
                filter_list=code_filter,
                filter_mode=filter_mode,
                dump_mode=dump_mode,
                is_not_recursive=not_recursive,
                collect_parent_map=collect_parent_map,
            )
            codes = set(id_hash_set)
        else:
            logging.error(f"Could not find root code '{root_code}'. Exiting.")
            sys.exit(-1)
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
            parent_map=parent_map if collect_parent_map else None,
            use_memoization=memoize_ancestors,
            force_overwrite_concepts=force_overwrite_concepts,
        )
    except Exception as e:
        logging.error(f"Error while creating hdf5 dump: '{e}'. Exiting.")
        pickle_path = hdf5_path.with_name(
            f"{hdf5_path.stem}-{dump_mode.name.lower()}.pickle"
        )
        logging.error(f"Dumping as pickle file: '{pickle_path}'.")
        pickle.dump(codes, open(pickle_path, "wb"))
