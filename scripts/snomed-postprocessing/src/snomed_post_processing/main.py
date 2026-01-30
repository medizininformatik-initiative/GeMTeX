import logging
import sys
from typing import Union

import click

from .snowstorm_funcs import build_endpoint, get_branches, dump_concept_ids


class ClickUnion(click.ParamType):
    def __init__(self, *types):
        self.types = types

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
    pass


@click.command()
@common_click_args
@common_click_options
@click.option(
    "--branch",
    default=0,
    type=ClickUnion(click.INT, click.STRING),
    help="The branch (i.e. Release Version) of SNOMED on the server. Defaults to the first one found.",
)
def create_concept_id_dump(
    root_code: str,
    ip: str,
    port: Union[int, str],
    use_secure_protocol: bool,
    branch: Union[int, str],
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

    ## From here replace with logic to recursively get all children, write their id into db(-like)
    dump_concept_ids(root_code, endpoint_builder)


@click.command()
@common_click_options
def list_branches(ip: str, port: Union[int, str], use_secure_protocol: bool):
    endpoint_builder, host = build_endpoint(ip, port, use_secure_protocol)
    path_ids, _ = get_branches(endpoint_builder, host)
    pad = len(max([str(x) for x in path_ids.get("path").keys()], key=len))
    for _id, path in path_ids.get("path").items():
        print(f"{str(_id).ljust(pad, ' ')} : {path}")


if __name__ == "__main__":
    pass
