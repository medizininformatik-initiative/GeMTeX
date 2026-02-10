import sys
import logging
import pathlib
import sys
from typing import Union

import click
import yaspin

if __name__ == "__main__":
    sys.path.append(".")
    from snowstorm_funcs import build_endpoint, get_branches, dump_concept_ids
    from utils import DumpMode, FilterMode, dump_codes_to_hdf5, ListDumpType
else:
    from .snowstorm_funcs import build_endpoint, get_branches, dump_concept_ids
    from .utils import DumpMode, FilterMode, dump_codes_to_hdf5, ListDumpType


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
@common_click_args
@common_click_options
def log_documents():
    # input uima json/xmi
    # dkpro-cassis
    pass


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
    "--filter-list", '-fl',
    default=None,
    type=ClickUnion((click.STRING, "str"), (click.File, "file")),
    multiple=True,
    help="When \"dump-mode == 'semantic'\", either multiple arguments of codes (or semantic tags) or a file that contains a code (semantic tag) per line.",
)
@click.option(
    "--filter-mode",
    default=FilterMode.POSITIVE,
    type=click.Choice(FilterMode, case_sensitive=False),
    help="'positive': only concepts with specified codes/tags will be returned; 'negative': vice versa concepts with specified codes/tags will not be returned"
)
@click.option(
    "--not-recursive",
    is_flag=True,
    help="If this flag is set, the codes will not be resolved recursively and only the first level children will be returned."
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
        elif pathlib.Path(filter_list[0]).is_file():
            code_filter = (
                pathlib.Path(filter_list[0]).read_text(encoding="utf-8").splitlines()
            )
        else:
            code_filter = filter_list
            if len(filter_list) == 0:
                code_filter = None

    with yaspin.yaspin(text="Processing...") as spinner:
        codes = dump_concept_ids(
            root_code=root_code,
            endpoint_builder=endpoint_builder,
            filter_list=code_filter,
            filter_mode=filter_mode,
            dump_mode=dump_mode,
            is_not_recursive=not_recursive,
        )
    hdf5_path = pathlib.Path(__file__, "../../../data/test.hdf5").resolve()
    hdf5_path.parent.mkdir(exist_ok=True, parents=True)
    dump_codes_to_hdf5(hdf5_path, codes, ListDumpType.BLACKLIST)


@click.command()
@common_click_options
def list_branches(ip: str, port: Union[int, str], use_secure_protocol: bool):
    endpoint_builder, host = build_endpoint(ip, port, use_secure_protocol)
    path_ids, _ = get_branches(endpoint_builder, host)
    pad = len(max([str(x) for x in path_ids.get("path").keys()], key=len))
    for _id, path in path_ids.get("path").items():
        print(f"{str(_id).ljust(pad, ' ')} : {path}")


if __name__ == "__main__":
    # create_concept_id_dump(["--ip", "nlp-prod", "--port", "9021", "--filter-list", "social concept", "--filter-list", "procedure", "--filter-list", "physical force", "--filter-list", "body structure", "--dump-mode", "semantic", "--filter-mode", "positive", "--not-recursive"])
    # create_concept_id_dump(["--ip", "nlp-prod", "--port", "9021", "--filter-list", "./config/blacklist_filter_codes.txt", "--dump-mode", "semantic", "--filter-mode", "negative"])
    # create_concept_id_dump(["--ip", "nlp-prod", "--port", "9021", "--dump-mode", "version"])
    create_concept_id_dump(["--ip", "nlp-prod", "--port", "9021", "--dump-mode", "semantic", "--not-recursive"])
    # create_concept_id_dump(["--ip", "nlp-prod", "--port", "9021", "--dump-mode", "version", "298011007"])