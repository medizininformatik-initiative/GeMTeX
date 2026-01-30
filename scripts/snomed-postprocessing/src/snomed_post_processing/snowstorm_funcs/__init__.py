import logging
import sys
from typing import Union

import requests.exceptions
from scttsrapy.api import EndpointBuilder
import scttsrapy.concepts as concepts
import scttsrapy.branching as branching

from ..utils import pprint_json, filter_by_semantic_tag


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


def dump_concept_ids(root_code: str, endpoint_builder: EndpointBuilder):
    concept_children = concepts.get_concept_children(
        root_code, endpoint_builder=endpoint_builder
    )
    pprint_json(
        filter_by_semantic_tag(concept_children, tag="disorder", positive=False)
    )
