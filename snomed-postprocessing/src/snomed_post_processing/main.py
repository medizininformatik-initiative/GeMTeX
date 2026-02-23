import datetime
import json
import os
import pickle
import sys
import logging
import pathlib
import sys
from email.policy import default
from typing import Union, Optional

import click
import h5py
import yaspin

if __name__ == "__main__":
    sys.path.append(".")
    from snowstorm_funcs import (
        build_endpoint,
        get_branches,
        dump_concept_ids,
        get_root_code,
    )
    from utils import DumpMode, FilterMode, dump_codes_to_hdf5, ListDumpType
    from uima_processing import process_inception_zip, analyze_documents
else:
    from .snowstorm_funcs import (
        build_endpoint,
        get_branches,
        dump_concept_ids,
        get_root_code,
    )
    from .utils import DumpMode, FilterMode, dump_codes_to_hdf5, ListDumpType
    from .uima_processing import process_inception_zip, analyze_documents


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


def common_click_options(fnc):
    fnc = click.option(
        "--use-secure_protocol", is_flag=True, help="Whether to use 'https'."
    )(fnc)
    fnc = click.option(
        "--port", default=8080, help="Port on which the Snowstorm server runs."
    )(fnc)
    fnc = click.option(
        "--ip", default="localhost", help="The IP address of the Snowstorm server."
    )(fnc)
    return fnc


def common_click_args(fnc):
    fnc = click.argument("root_code", default="138875005")(fnc)
    return fnc


@click.command()
@click.argument("zip-file", type=click.Path(exists=True))
@click.option(
    "--lists-path",
    default=None,
    help="The path to the lists file in 'hdf5' format. (default: default lists are used)",
)
def log_documents(zip_file: str, lists_path: Optional[str]):
    """
    Analyzes an INCEpTION project "ZIP_FILE" and logs all documents that contain erroneous concepts
    according to the given filter lists in a hdf5 file ("lists-path").
    """
    project_zip = pathlib.Path(zip_file).resolve()
    default_lists_path = pathlib.Path(
        pathlib.Path(__file__).parent.parent.parent,
        "data",
        "gemtex_snomedct_codes_2024-04-01.hdf5",
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
    output_path = (
        project_zip.parent
        / f"critical_documents_{datetime.datetime.today().strftime('%d-%m-%Y_%H-%M-%S')}.md"
    )

    erroneous_doc_count = 0
    if result := process_inception_zip(project_zip):
        with output_path.open("w", encoding="utf-8") as log_doc:
            with h5py.File(lists_path.open("rb"), "r") as h5_file:
                for ft in [ListDumpType.WHITELIST, ListDumpType.BLACKLIST]:
                    if ft.name.lower() in h5_file.keys():
                        filter_list = h5_file.get(ft.name.lower()).get("0").get("codes")
                        fsn_list = h5_file.get(ft.name.lower()).get("0").get("fsn")
                        erroneous_doc_count += analyze_documents(
                            result,
                            filter_list[:],
                            fsn_list[:],
                            ft,
                            log_doc,
                        )
    if erroneous_doc_count > 0:
        logging.warning(
            f"{erroneous_doc_count:>4} critical document(s) found. See '{output_path.resolve()}' for details."
        )
    else:
        logging.info("No critical document(s) found.")


@click.command()
@common_click_args
@common_click_options
@click.option(
    "--branch",
    default=0,
    type=ClickUnion((click.INT, "int"), (click.STRING, "str")),
    help="The branch (i.e. Release Version) of SNOMED on the server. Defaults to the first one found.",
)
@click.option(
    "--dump-mode",
    default=DumpMode.VERSION,
    type=click.Choice(DumpMode, case_sensitive=False),
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
    type=click.Choice(FilterMode, case_sensitive=False),
    help="'positive': only concepts with specified codes/tags will be returned; 'negative': vice versa concepts with specified codes/tags will not be returned",
)
@click.option(
    "--not-recursive",
    is_flag=True,
    help="If this flag is set, the codes will not be resolved recursively and only the first level children will be returned.",
)
def create_concept_id_dump(
    root_code: str,
    ip: str,
    port: Union[int, str],
    use_secure_protocol: bool,
    branch: Union[int, str],
    dump_mode: DumpMode,
    filter_list: Union[str, click.File],
    filter_mode: FilterMode,
    not_recursive: bool,
):
    """Creates a dump of all concept IDs (if filter-mode == 'version') or only for the ones that match the given filter criteria
    (if a filter-list is given and filter-mode == 'semantic') for a SNOMED CT release version (--branch)."""
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
    if dump_mode == dump_mode.SEMANTIC:
        if len(filter_list) < 1:
            code_filter = None
        else:
            fi = pathlib.Path(filter_list[0])
            if fi.is_file():
                code_filter = fi.read_text(encoding="utf-8").splitlines()
            else:
                if os.sep in str(fi):
                    code_filter = None
                else:
                    code_filter = filter_list
                    if len(filter_list) == 0:
                        code_filter = None

    with yaspin.yaspin(text="Processing...") as spinner:
        if root := get_root_code(root_code, endpoint_builder):
            id_hash_set, id_to_fsn_dict = dump_concept_ids(
                root_concept=root,
                endpoint_builder=endpoint_builder,
                filter_list=code_filter,
                filter_mode=filter_mode,
                dump_mode=dump_mode,
                is_not_recursive=not_recursive,
            )
            codes = set(id_hash_set)
        else:
            logging.error(f"Could not find root code '{root_code}'. Exiting.")
            sys.exit(-1)
    pickle.dump(
        codes, (pathlib.Path(__file__).parent / "dump.pickle").open("wb")
    )  # ToDo: remove later
    hdf5_path = pathlib.Path(
        __file__,
        f"../../../data/gemtex_snomedct_codes_{endpoint_builder.branch.split('/')[-1]}.hdf5",
    ).resolve()
    hdf5_path.parent.mkdir(exist_ok=True, parents=True)
    dump_codes_to_hdf5(
        fi_path=hdf5_path,
        codes=codes,
        id_to_fsn_dict=id_to_fsn_dict,
        list_type=ListDumpType.BLACKLIST
        if dump_mode == DumpMode.SEMANTIC
        else ListDumpType.WHITELIST,
    )


@click.command()
@common_click_options
def list_branches(ip: str, port: Union[int, str], use_secure_protocol: bool):
    """Lists all available branches on the server."""
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


if __name__ == "__main__":
    help_me(["--help"])
