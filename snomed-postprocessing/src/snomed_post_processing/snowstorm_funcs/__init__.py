import logging
import sys
from typing import Union, Optional, Iterable, Tuple

import requests.exceptions
from scttsrapy.api import EndpointBuilder
import scttsrapy.concepts as concepts
import scttsrapy.branching as branching

if __name__.find(".snowstorm_funcs") != -1:
    from ..utils import filter_by_semantic_tag, DumpMode, return_codes, FilterMode, FilterLists
else:
    from utils import filter_by_semantic_tag, DumpMode, return_codes, FilterMode, FilterLists


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


def get_root_code(code: str, endpoint_builder: EndpointBuilder):
    response = return_codes(
        concepts.get_concept(code, endpoint_builder=endpoint_builder)
    )
    if len(response) == 0:
        return None
    return response[0]


def dump_concept_ids(
    root_code: str,
    fsn_term: str,
    endpoint_builder: EndpointBuilder,
    filter_list: Optional[Union[Iterable, FilterLists]] = None,
    filter_mode: FilterMode = FilterMode.POSITIVE,
    dump_mode: DumpMode = DumpMode.VERSION,
    is_not_recursive: bool = False,
    up_to_including: int = -1,
    iteration: int = 0,
    id_hash_set: set = None,
    id_to_fsn_dict: dict = None,
) -> Tuple[set[str], dict[str, str]]:
    """
    Dumps concept IDs and their fully specified names (FSNs) with configurable filtering and recursion.

    The function retrieves a set of concept IDs and a dictionary mapping concept IDs to their
    fully specified names (FSNs). It utilizes hierarchical relationships of concepts and applies
    filters based on semantic tags or inclusion/exclusion lists. Recursive exploration of child
    concepts is optionally limited by specified parameters.

    Parameters:
        root_code (str): The concept identifier to start dumping IDs from.
        fsn_term (str): The fully specified name (FSN) of the root concept.
        endpoint_builder (EndpointBuilder): An instance responsible for constructing and managing
            API endpoint interactions.
        filter_list (Optional[Iterable]): A list of filters for the concepts, which can be either
            semantic tags or concept codes.
        filter_mode (FilterMode): Determines whether the filtering should include
            (FilterMode.POSITIVE) or exclude (FilterMode.NEGATIVE) the concepts provided in
            the filter_list. Defaults to FilterMode.POSITIVE.
        dump_mode (DumpMode): Specifies the mode of dumping concepts, such as version-based
            or semantic tag-based filtering.
        is_not_recursive (bool): If True, recursion into child concepts is restricted.
        up_to_including (int): Limits the recursion depth to a specified level. A value of -1
            disables this constraint.
        iteration (int): Tracks the current recursion depth.
        id_hash_set (set): A set of concept IDs accumulated during the dumping process. Defaults to
            an empty set if None is provided.
        id_to_fsn_dict (dict): A dictionary mapping concept IDs to their FSNs, populated dynamically.
            Defaults to an empty dictionary if None is provided.

    Returns:
        Tuple[set[str], dict[str, str]]: A tuple containing:
            - A set of unique concept IDs encountered during traversal.
            - A dictionary mapping concept IDs to their corresponding FSNs.

    Raises:
        NotImplementedError: If filtering by concept codes (as opposed to semantic tags)
            is requested but not implemented.
    """
    if id_hash_set is None:
        id_hash_set = set()
    if id_to_fsn_dict is None:
        id_to_fsn_dict = {}
    if root_code in id_hash_set:
        return id_hash_set, id_to_fsn_dict
    if root_code not in id_to_fsn_dict:
        id_to_fsn_dict[root_code] = fsn_term
    if (is_not_recursive and iteration >= 2) or (
        not is_not_recursive
        and up_to_including != -1
        and iteration >= (up_to_including + 1)
    ):
        return id_hash_set, id_to_fsn_dict

    concept_children = concepts.get_concept_children(
        root_code, endpoint_builder=endpoint_builder
    )

    id_hash_set.add(root_code)
    if iteration == 0:
        if filter_list is not None:
            c = [f for f in filter_list if f.isdigit()]
            t = [f for f in filter_list if f not in c]
            filter_list = FilterLists(c, t)

    iteration += 1
    if dump_mode == dump_mode.SEMANTIC and filter_list is not None:
        for code in return_codes(
            filter_by_semantic_tag(
                concept_children,
                tags=filter_list.tags,
                positive=filter_mode == FilterMode.POSITIVE,
            )
        ):
            if code.conceptId in filter_list.codes:
                continue
            _id_hash_set, _id_to_fsn_dict = dump_concept_ids(
                code.conceptId,
                code.fsn.term,
                endpoint_builder,
                filter_list,
                filter_mode,
                dump_mode,
                is_not_recursive,
                up_to_including,
                iteration,
                id_hash_set,
                id_to_fsn_dict,
            )
            id_hash_set.update(_id_hash_set)
    else:
        for code in return_codes(concept_children):
            _id_hash_set, _id_to_fsn_dict = dump_concept_ids(
                code.conceptId,
                code.fsn.term,
                endpoint_builder,
                filter_list,
                filter_mode,
                dump_mode,
                is_not_recursive,
                up_to_including,
                iteration,
                id_hash_set,
                id_to_fsn_dict,
            )
            id_hash_set.update(_id_hash_set)

    return set(id_hash_set), id_to_fsn_dict
