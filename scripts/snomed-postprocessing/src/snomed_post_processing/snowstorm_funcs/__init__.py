import logging
import sys
from typing import Union, Optional, Iterable

import requests.exceptions
from scttsrapy.api import EndpointBuilder
import scttsrapy.concepts as concepts
import scttsrapy.branching as branching

if __name__.find(".snowstorm_funcs") != -1:
    from ..utils import filter_by_semantic_tag, DumpMode, return_codes, FilterMode
else:
    from utils import filter_by_semantic_tag, DumpMode, return_codes, FilterMode

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
    filter_mode: FilterMode = FilterMode.POSITIVE,
    dump_mode: DumpMode = DumpMode.VERSION,
    is_not_recursive: bool = False,
    up_to_including: int = -1,
    iteration: int = 0,
    id_hash_set: set = None,
) -> set[str]:
    if id_hash_set is None:
        id_hash_set = set()
    if root_code in id_hash_set:
        return id_hash_set
    if (is_not_recursive and iteration >= 2) or (not is_not_recursive and up_to_including != -1 and iteration >= (up_to_including + 1)):
        return id_hash_set

    concept_children = concepts.get_concept_children(
        root_code, endpoint_builder=endpoint_builder
    )

    id_hash_set.add(root_code)
    is_semantic_tags = False
    if filter_list is not None:
        filter_list = list(filter_list)
        filter_list_int = [f for f in filter_list if f.isdigit()]
        if len(filter_list_int) > round(len(filter_list) / 2):
            filter_list = filter_list_int
        else:
            is_semantic_tags = True
            filter_list = [f for f in filter_list.copy() if not f.isdigit()]

    iteration += 1
    if dump_mode == dump_mode.SEMANTIC and filter_list is not None:
        if is_semantic_tags:
            for code in return_codes(
                    filter_by_semantic_tag(concept_children, tags=filter_list, positive=filter_mode==FilterMode.POSITIVE)
            ):
                id_hash_set.update(dump_concept_ids(code, endpoint_builder, filter_list, filter_mode, dump_mode, is_not_recursive, up_to_including, iteration, id_hash_set))
        else:
            # Filter not by tags but by codes
            raise NotImplementedError("Filtering by codes is not yet implemented; only filtering by semantic tags.")
    else:
        for code in return_codes(concept_children):
            id_hash_set.update(dump_concept_ids(code, endpoint_builder, filter_list, filter_mode, dump_mode, is_not_recursive, up_to_including, iteration, id_hash_set))

    return set(id_hash_set)