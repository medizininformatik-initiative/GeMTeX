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
from .rf2 import write_snapshot_hdf5_from_rf2_zip
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
    process_inception_zip,
    get_annotator_names,
    create_log_from_results,
)


class ClickUnion(click.ParamType):
    def __init__(self, *types):
        self.types = [t[0] for t in types]
        self.name = f"[{','.join([t[1] for t in types])}]"

    def convert(self, value, param, ctx):
        for _type in self.types:
            try:
                return _type.convert(value, param, ctx)
            except click.BadParameter:
                continue

        self.fail("Didn't match any of the accepted types.")


class ClickEnumChoice(click.ParamType):
    def __init__(self, enum_type):
        self.enum_type = enum_type
        self.choices = [e.name.lower() for e in enum_type]
        self.name = "[" + "|".join(self.choices) + "]"

    def convert(self, value, param, ctx):
        if isinstance(value, self.enum_type):
            return value
        value_normalized = str(value).lower()
        for enum_value in self.enum_type:
            if enum_value.name.lower() == value_normalized:
                return enum_value
        self.fail(
            f"'{value}' is not one of {'/'.join(self.choices)}.", param, ctx
        )


def click_server_options(fnc):
    fnc = click.option(
        "--use-secure_protocol", is_flag=True, help="Whether to use 'https'."
    )(fnc)
    fnc = click.option(
        "--port",
        default=8080,
        help="Port on which the Snowstorm/INCEpTION instance runs.",
    )(fnc)
    fnc = click.option(
        "--ip",
        default="localhost",
        help="The IP address of the Snowstorm/INCEpTION instance.",
    )(fnc)
    return fnc


def click_inception_client_options(fnc):
    fnc = click.option(
        "--inception-project",
        default=None,
        help="The name of the INCEpTION project (URL slug).",
    )(fnc)
    fnc = click.option(
        "--inception-password",
        default=None,
        help="The username for the INCEpTION client (needs to have REMOTE role).",
    )(fnc)
    fnc = click.option(
        "--inception-username",
        default=None,
        help="The username for the INCEpTION client (needs to have REMOTE role).",
    )(fnc)
    return fnc


def click_log_level(fnc):
    fnc = click.option(
        "--log-level",
        default="INFO",
        type=click.Choice(
            ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False
        ),
        help="The log level.",
    )(fnc)
    return fnc


def common_click_args(fnc):
    fnc = click.argument("root_code", default="138875005")(fnc)
    return fnc


@click.command()
@click.argument("process_path", type=click.STRING)
@click.option(
    "--lists-path",
    default=None,
    help="The path to the lists file in 'hdf5' format. (default: default lists are used)",
)
@click_server_options
@click_inception_client_options
@click_log_level
@click.option(
    "--keep-export",
    is_flag=True,
    help="Keeps the temporary exported INCEpTION project (when using client) after processing.",
)
@click.option(
    "--omit-dump",
    is_flag=True,
    help="Omits the creation of a dump of all concepts in the project and their respective offsets (if not omitted, it is saved alongside the log file).",
)
@click.option(
    "--forbid-prompt",
    is_flag=True,
    help="Forbids prompting the user to select the annotators to log manually (instead of all). Use this flag for e.g. 'docker', when you don't want to mess with providing prompt answers.",
)
@click.option(
    "--annotation-type",
    multiple=True,
    default=("gemtex.Concept",),
    show_default=True,
    help="Target annotation layer/type to check for SNOMED CT codes. Can be provided multiple times.",
)
@click.option(
    "--ignore-overlap-type",
    multiple=True,
    default=("webanno.custom.No_Human",),
    show_default=True,
    help="Annotation layer/type whose overlapping spans suppress faulty-code findings on target annotations. Can be provided multiple times.",
)
@click.option(
    "--ignore-overlap-mode",
    default="overlap",
    show_default=True,
    type=click.Choice(["overlap", "covered-by", "contains", "exact"], case_sensitive=False),
    help="How target annotations must match ignore-overlap annotations to be ignored.",
)
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
                result, log_doc, log_doc_masked, lists_path, None, dump_dictionary
            )
        with output_path.with_suffix(".json").open("w") as json_file:
            json.dump(dump_dictionary, json_file, ensure_ascii=False, indent=2)

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
@common_click_args
@click.option(
    "--zip",
    "rf2_zip",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
    help="Path to a SNOMED CT RF2 release ZIP. If provided, HDF5 is generated from the release ZIP instead of Snowstorm.",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(dir_okay=False, path_type=pathlib.Path),
    help="Output HDF5 path for RF2 ZIP mode. Defaults to data/gemtex_snomedct_codes_<release-date>.hdf5 when the date can be inferred.",
)
@click.option(
    "--language",
    default="en",
    show_default=True,
    help="RF2 description language used in ZIP mode, e.g. 'en'.",
)
@click.option(
    "--include-ancestors",
    is_flag=True,
    help="In RF2 ZIP mode, compute compact ancestor arrays under /concepts. Historical associations are included by default.",
)
@click.option(
    "--policy-date",
    default=None,
    help="Policy date as YYYYMMDD for RF2 ZIP mode. Snapshot mode currently requires this to equal the Snapshot release date.",
)
@click.option(
    "--write-legacy-policy-groups",
    is_flag=True,
    help="In RF2 ZIP mode, additionally write legacy /whitelist or /blacklist groups for older code.",
)
@click.option(
    "--use-secure_protocol", is_flag=True, help="Whether to use 'https' for Snowstorm mode."
)
@click.option(
    "--port",
    default=None,
    type=click.INT,
    help="Snowstorm port. Required together with --ip when --zip is not used.",
)
@click.option(
    "--ip",
    default=None,
    help="Snowstorm IP/host. Required together with --port when --zip is not used.",
)
@click.option(
    "--branch",
    default=0,
    type=ClickUnion((click.INT, "int"), (click.STRING, "str")),
    help="The branch (i.e. Release Version) of SNOMED on the server. Defaults to the first one found.",
)
@click.option(
    "--dump-mode",
    default=DumpMode.VERSION,
    type=ClickEnumChoice(DumpMode),
    help="Whether to whitelist ('version') or blacklist ('semantic') a code dump.",
)
@click.option(
    "--filter-list",
    "-fl",
    default=None,
    type=ClickUnion((click.STRING, "str"), (click.File, "file")),
    multiple=True,
    help="When \"dump-mode == 'semantic'\", either multiple arguments of codes (or semantic tags) or a file that contains a code (semantic tag) per line.",
)
@click.option(
    "--filter-mode",
    default=FilterMode.POSITIVE,
    type=ClickEnumChoice(FilterMode),
    help="'positive': only concepts with specified codes/tags will be returned; 'negative': vice versa concepts with specified codes/tags will not be returned",
)
@click.option(
    "--not-recursive",
    is_flag=True,
    help="If this flag is set, the codes will not be resolved recursively and only the first level children will be returned.",
)
@click.option(
    "--force-overwrite",
    is_flag=True,
    help="If this flag is set, the selected whitelist/blacklist HDF5 group will be overwritten.",
)
@click.option(
    "--force-overwrite-concepts",
    is_flag=True,
    help="If this flag is set, an existing /concepts HDF5 extension will be rebuilt. Independent from --force-overwrite.",
)
@click.option(
    "--memoize-ancestors",
    is_flag=True,
    help="Use memoization when computing the compact ancestor/distance HDF5 extension. Disabled by default.",
)
@click_log_level
def create_concept_id_dump(
    root_code: str,
    rf2_zip: Optional[pathlib.Path],
    output: Optional[pathlib.Path],
    language: str,
    include_ancestors: bool,
    policy_date: Optional[str],
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
        pickle_path = hdf5_path.with_suffix(f"-{dump_mode.name.lower()}.pickle")
        logging.error(f"Dumping as pickle file: '{pickle_path}'.")
        pickle.dump(codes, open(pickle_path, "wb"))


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
     * list-branches

    Each command has a '--help' option that provides further information, e.g. 'log-critical-documents --help'
    """
    print(
        "Please use one of the following commands:"
        "\n\n * log-critical-documents"
        "\n * create-concepts-dump"
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
