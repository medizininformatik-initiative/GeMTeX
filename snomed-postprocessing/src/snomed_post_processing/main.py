import datetime
import json
import os
import pickle
import logging
import pathlib
import sys
import re
import zipfile
from typing import Union, Optional

import click
import yaspin

from .snowstorm_funcs import (
    build_endpoint,
    get_branches,
    dump_concept_ids,
    get_root_code,
)
from .release_ingestion import write_snapshot_hdf5_from_rf2_zip
from .utils import (
    DumpMode,
    FilterMode,
    dump_codes_to_hdf5,
    hdf5_has_concepts_extension,
    ListDumpType,
    prompt_for_names,
    get_project_zip,
)
from .uima_processing import (
    CriticalFinding,
    process_inception_zip,
    get_annotator_names,
    create_log_from_results,
)
from .sanitization import (
    SanitizationResolver,
    apply_semantic_bm25_fallback,
    write_sanitization_markdown_report,
)
from .findings_io import read_critical_findings_json, write_critical_findings_json
from .hdf5_handling.metadata import inspect_hdf5_metadata, format_hdf5_metadata_summary
from .cli import (
    click_log_level,
    click_server_options,
    create_concept_id_dump_options,
    log_documents_options,
    suggest_sanitization_options,
)


@click.command()
@log_documents_options
def log_documents(
    process_path: str,
    lists_path: Optional[str],
    ip: str,
    port: Union[int, str],
    use_secure_protocol: bool,
    inception_username: Optional[str],
    inception_password: Optional[str],
    inception_project: Optional[str],
    log_level: str,
    keep_export: bool,
    omit_dump: bool,
    forbid_prompt: bool,
    annotation_type: tuple[str, ...],
    ignore_overlap_type: tuple[str, ...],
    ignore_overlap_mode: str,
):
    """
    Analyzes an INCEpTION project zip file (if PROCESS_PATH points to a local zip file) or a particular project in an INCEpTION instance
    if ip, port, username & password, as well as the project-name are given (then PROCESS_PATH points to the folder where the project should be temporarily exported to).
    Then, it logs all documents that contain erroneous concepts according to the given filter lists in a hdf5 file ("lists-path").
    """
    set_log_level(log_level)

    host = f"http{'s' if use_secure_protocol else ''}://{ip}:{port}"
    use_api = (
        inception_username is not None
        and inception_password is not None
        and inception_project is not None
    )
    try:
        project_zip = get_project_zip(
            process_path,
            host,
            inception_username,
            inception_password,
            inception_project,
            False
        )
    except Exception as e:
        logging.error(f"Error while getting project zip: '{e}'. Exiting.")
        sys.exit(-1)

    default_lists_path = (
        pathlib.Path(__file__).parent.parent.parent / "data" / "gemtex_snomedct_codes_2024-04-01.hdf5"
    ).resolve()
    if lists_path is not None:
        lists_path_tmp = pathlib.Path(lists_path).resolve()
        if lists_path_tmp.exists() and lists_path_tmp.is_file():
            lists_path = lists_path_tmp
        else:
            logging.warning(
                f"The given list doesn't seem to exist or is not a file in hdf5 format: '{lists_path_tmp}'\nUsing default one."
            )
            lists_path = default_lists_path
    else:
        logging.info("No filter list given, using default one.")
        lists_path = default_lists_path

    if not lists_path.exists():
        logging.error(f"The given list doesn't exist: '{lists_path}'. Exiting.")
        sys.exit(-1)

    names_filter = None
    if not forbid_prompt:
        annotator_names, only_ser = get_annotator_names(project_zip)
        if only_ser:
            logging.error(
                "The project only contains UIMA Java Serialized CAS (.ser) files, which are not supported. Please export as JSON CAS or XMI instead."
            )
            sys.exit(-1)

        _res = prompt_for_names(annotator_names)
        if _res and len(_res) > 0:
            names_filter = [n.lower() for n in _res]
    else:
        # If forbid_prompt is set, we still check if the project is processable
        _, only_ser = get_annotator_names(project_zip)
        if only_ser:
            logging.error(
                "The project only contains UIMA Java Serialized CAS (.ser) files, which are not supported. Please export as JSON CAS or XMI instead."
            )
            sys.exit(-1)

    output_path = (
        project_zip.parent
        / f"critical_documents_{datetime.datetime.today().strftime('%d-%m-%Y_%H-%M')}.md"
    )
    output_path_masked = output_path.with_suffix(".masked.md")

    erroneous_doc_count = 0
    dump_dictionary = None if omit_dump else {}
    critical_findings: list[CriticalFinding] = []
    if result := process_inception_zip(
        project_zip,
        annotator_filter=names_filter,
        annotation_types=list(annotation_type),
        ignore_overlap_types=list(ignore_overlap_type),
        ignore_overlap_mode=ignore_overlap_mode,
    ):
        with (
            output_path.open("w", encoding="utf-8") as log_doc,
            output_path_masked.open("w", encoding="utf-8") as log_doc_masked,
        ):
            erroneous_doc_count = create_log_from_results(
                result,
                log_doc,
                log_doc_masked,
                lists_path,
                None,
                dump_dictionary,
                critical_findings=critical_findings,
            )
        with output_path.with_suffix(".json").open("w") as json_file:
            json.dump(dump_dictionary, json_file, ensure_ascii=False, indent=2)

        critical_findings_output_path = output_path.with_name(
            output_path.stem.replace("critical_documents", "critical_findings")
            + ".json"
        )
        write_critical_findings_json(
            critical_findings,
            critical_findings_output_path,
            metadata={
                "command": "log-critical-documents",
                "lists_path": str(lists_path),
                "annotation_types": list(annotation_type),
                "ignore_overlap_types": list(ignore_overlap_type),
                "ignore_overlap_mode": ignore_overlap_mode,
            },
        )
        logging.info(
            f"Critical findings JSON written to '{critical_findings_output_path.resolve()}'."
        )

    if not keep_export and use_api:
        logging.info(
            f"Removing temporary export of project '{project_zip.name}' from filesystem."
        )
        project_zip.unlink()

    print("-- Result --")
    if erroneous_doc_count > 0:
        logging.warning(
            f"{erroneous_doc_count:>4} critical document(s) found. See '{output_path.resolve()}' for details."
        )
    else:
        logging.info("No critical document(s) found.")


@click.command()
@create_concept_id_dump_options
def create_concept_id_dump(
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
    """
    Creates a SNOMED CT concept ID dump based on specified filtering criteria and stores
    the results in an HDF5 file. If an error occurs during HDF5 file creation, the dump will be stored as a pickle file
    to prevent data loss after the potentially long-running process.

    Parameters:
        root_code (str): The root SNOMED CT concept ID to start the dump from.
        ip (str): The IP address of the SNOMED CT server.
        port (Union[int, str]): The port of the SNOMED CT server.
        use_secure_protocol (bool): Indicates whether to use HTTPS for communicating
            with the SNOMED CT server.
        branch (Union[int, str]): The branch or release version of SNOMED CT to use.
            Integer values refer to branch indices, and string values refer to branch names (use 'list_branches' to view all options).
        dump_mode (DumpMode): Determines how the code dump is created. Options are
            versions for whitelisting or semantic for blacklisting specific codes.
        filter_list (Union[str, click.File]): A list of filter values or a file containing
            one filter value per line. Used when dump_mode is semantic.
        filter_mode (FilterMode): Specifies how the filtering is applied. 'positive'
            includes only concepts with specified codes or tags, while 'negative' excludes
            them.
        not_recursive (bool): If True, only the first-level children of the root concept
            are included in the dump without resolving them recursively.
        force_overwrite (bool): If True, overwrites the selected whitelist/blacklist group when creating the dump.
        force_overwrite_concepts (bool): If True, rebuilds the /concepts HDF5 extension.
        log_level (str): The level of logging to use during the operation.

    Raises:
        SystemExit: If the specified branch or root code cannot be found on the SNOMED CT
            server, the operation terminates.

    Notes:
        - The function dynamically determines the SNOMED branch if not specified or uses
          the first available branch by default.
        - Filters are applied when `dump_mode` is semantic, and the corresponding filter
          values are validated for existence in a file or as direct inputs.
        - String filters refer to SNOMED CT semantic tags and will be evaluated for each concept,
          while integer filters refer to SNOMED CT codes and all their subsequent child concepts.
        - If an error occurs during HDF5 file creation, the dump is saved in a pickle file
          and logs the error details.
    """
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
                pathlib.Path(__file__).parent.parent.parent
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

    hdf5_path = pathlib.Path(
        __file__,
        f"../../../data/gemtex_snomedct_codes_{endpoint_builder.branch.split('/')[-1]}.hdf5",
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


@click.command(name="suggest-sanitization")
@suggest_sanitization_options
def suggest_sanitization_cli(
    lists_path: pathlib.Path,
    critical_findings: pathlib.Path,
    output: pathlib.Path,
    association_type: tuple[str, ...],
    semantic_bm25_fallback: bool,
    blacklist_suggestions: bool,
    bm25_min_score: float,
    bm25_min_lexical_score: float,
    bm25_max_candidates: int,
    log_level: str,
):
    """Create sanitization suggestions from a CriticalFindings JSON artifact."""
    set_log_level(log_level)
    if blacklist_suggestions and not semantic_bm25_fallback:
        raise click.UsageError("--blacklist-suggestions requires --semantic-bm25-fallback.")

    findings = read_critical_findings_json(critical_findings)
    resolver = SanitizationResolver(
        lists_path,
        allowed_association_types=association_type,
    )
    suggestions = resolver.suggest_all(findings)
    if semantic_bm25_fallback:
        suggestions = apply_semantic_bm25_fallback(
            suggestions,
            lists_path,
            min_score=bm25_min_score,
            min_lexical_score=bm25_min_lexical_score,
            max_candidates=bm25_max_candidates,
            allow_blacklist_findings=blacklist_suggestions,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as sanitization_report:
        write_sanitization_markdown_report(suggestions, sanitization_report)
    logging.info(f"Sanitization suggestion report written to '{output.resolve()}'.")


@click.command()
@click.argument(
    "hdf5_path",
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
)
@click.option(
    "--markdown",
    is_flag=True,
    help="Render the metadata summary as Markdown.",
)
def summarize_hdf5(hdf5_path: pathlib.Path, markdown: bool):
    """Print a concise metadata summary for a SNOMED postprocessing HDF5 file."""
    summary = inspect_hdf5_metadata(hdf5_path)
    click.echo(format_hdf5_metadata_summary(summary, markdown=markdown))


@click.command()
@click_server_options
@click_log_level
def list_branches(
    ip: str, port: Union[int, str], use_secure_protocol: bool, log_level: str
):
    """Lists all available branches on the server."""
    set_log_level(log_level)
    endpoint_builder, host = build_endpoint(ip, port, use_secure_protocol)
    path_ids, _ = get_branches(endpoint_builder, host)
    pad = len(max([str(x) for x in path_ids.get("path").keys()], key=len))
    for _id, path in path_ids.get("path").items():
        print(f"{str(_id).ljust(pad, ' ')} : {path}")


@click.command()
def help_me():
    """Please use one of the following commands:

    \b
     * log-critical-documents
     * create-concepts-dump
     * summarize-hdf5
     * suggest-sanitization
     * list-branches

    Each command has a '--help' option that provides further information, e.g. 'log-critical-documents --help'
    """
    print(
        "Please use one of the following commands:"
        "\n\n * log-critical-documents"
        "\n * create-concepts-dump"
        "\n * summarize-hdf5"
        "\n * suggest-sanitization"
        "\n * list-branches"
        "\n\nEach command has a '--help' option that provides further information, e.g. 'log-critical-documents --help'"
    )


def set_log_level(log_level: str):
    log_level_ = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }.get(log_level.lower(), logging.INFO)
    logging.basicConfig(level=log_level_)


if __name__ == "__main__":
    help_me(["--help"])
