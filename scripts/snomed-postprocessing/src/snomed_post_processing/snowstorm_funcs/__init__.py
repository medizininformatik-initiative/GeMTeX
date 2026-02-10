import logging
import sys
from typing import Union, Optional, Iterable

import requests.exceptions
from scttsrapy.api import EndpointBuilder
import scttsrapy.concepts as concepts
import scttsrapy.branching as branching

from ..utils import pprint_json, filter_by_semantic_tag, DumpMode


def build_endpoint(ip: str, port: Union[int, str], use_secure_protocol: bool):
    host = f"http{'s' if use_secure_protocol else ''}://{ip}:{port}"
    endpoint_builder = EndpointBuilder()
    endpoint_builder.set_api_endpoint(host)
    return endpoint_builder, host


def get_branches(endpoint_builder: EndpointBuilder, host: str):
    try:
        branches = branching.all_branches(endpoint_builder=endpoint_builder)
        if not branches.get("success", False):
            logging.error(
                f"Something went wrong:\n{branches.get('content', b'No content').decode('utf-8')}"
            )
            sys.exit(-1)
    except requests.exceptions.ConnectionError as e:
        logging.error(f"Could not connect to Snowstorm Server at '{host}': {e}.")
        sys.exit(-1)

    path_ids = {
        "path": {
            i: d.get("path", "n.a.") for i, d in enumerate(branches.get("content", []))
        }
    }
    path_names = list(path_ids.get("path", {}).values())
    return path_ids, path_names


def dump_concept_ids(
    root_code: str,
    endpoint_builder: EndpointBuilder,
    filter_list: Optional[Iterable] = None,
    dump_mode: DumpMode = DumpMode.VERSION,
):
    concept_children = concepts.get_concept_children(
        root_code, endpoint_builder=endpoint_builder
    )

    is_semantic_tags = False
    if filter_list is not None:
        filter_list = list(filter_list)
        filter_list_int = [f for f in filter_list if f.isdigit()]
        if len(filter_list_int) > len(filter_list):
            filter_list = filter_list_int
        else:
            is_semantic_tags = True
            filter_list = [f for f in filter_list.copy() if not f.isdigit()]

    ## From here replace with logic to recursively get all children, write their id into db(-like)
    if dump_mode == dump_mode.SEMANTIC and filter_list is not None:
        if is_semantic_tags:
            pprint_json(
                # filter_by_semantic_tag(concept_children, tag="disorder", positive=False)
                filter_by_semantic_tag(concept_children, tags=filter_list, positive=False)
            )
    elif dump_mode == dump_mode.VERSION:
        pprint_json(
            concept_children
        )
