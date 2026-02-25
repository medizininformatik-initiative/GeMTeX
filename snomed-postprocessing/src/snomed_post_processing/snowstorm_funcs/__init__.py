import logging
import sys
from typing import Union, Optional, Iterable, Tuple

import requests.exceptions
from scttsrapy.api import EndpointBuilder
import scttsrapy.concepts as concepts
import scttsrapy.branching as branching

if __name__.find(".snowstorm_funcs") != -1:
    from ..utils import (
        filter_by_semantic_tag,
        DumpMode,
        return_codes,
        FilterMode,
        FilterLists,
        SnomedConcept,
    )
else:
    from utils import (
        filter_by_semantic_tag,
        DumpMode,
        return_codes,
        FilterMode,
        FilterLists,
        SnomedConcept,
    )


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
    root_concept: Optional[SnomedConcept],
    endpoint_builder: EndpointBuilder,
    filter_list: Optional[Union[Iterable, FilterLists]] = None,
    filter_mode: FilterMode = FilterMode.POSITIVE,
    dump_mode: DumpMode = DumpMode.VERSION,
    is_not_recursive: bool = False,
    up_to_including: int = -1,
    iteration: int = 0,
    id_hash_set: set = None,
    id_to_fsn_dict: dict = None,
    dump_whole_subtree: bool = False,
    visited_nodes: set = None,
) -> Tuple[set[str], dict[str, str]]:
    """
    Dumps concept IDs and their fully specified names (FSNs) with configurable filtering and recursion.

    The function retrieves a set of concept IDs and a dictionary mapping concept IDs to their
    fully specified names (FSNs). It utilizes hierarchical relationships of concepts and applies
    filters based on semantic tags or inclusion/exclusion lists. Recursive exploration of child
    concepts is optionally limited by specified parameters.

    Parameters:
        root_concept (str): The concept identifier to start dumping IDs from.
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
        dump_whole_subtree (bool): ...
        visited_nodes (set): ...

    Returns:
        Tuple[set[str], dict[str, str]]: A tuple containing:
            - A set of unique concept IDs encountered during traversal.
            - A dictionary mapping concept IDs to their corresponding FSNs.

    Raises:
        NotImplementedError: If filtering by concept codes (as opposed to semantic tags)
            is requested but not implemented.
    """
    if visited_nodes is None:
        visited_nodes = set()
    if id_hash_set is None:
        id_hash_set = set()
    if id_to_fsn_dict is None:
        id_to_fsn_dict = {}
    if (
        root_concept is None
        or root_concept.conceptId is None
        or root_concept.conceptId in id_hash_set
        or root_concept.conceptId in visited_nodes
    ):
        return id_hash_set, id_to_fsn_dict
    if root_concept.conceptId not in id_to_fsn_dict:
        id_to_fsn_dict[root_concept.conceptId] = root_concept.fsn.term
    if (is_not_recursive and iteration >= 2) or (
        not is_not_recursive
        and up_to_including != -1
        and iteration >= (up_to_including + 1)
    ):
        return id_hash_set, id_to_fsn_dict
    if iteration == 0:
        if filter_list is not None:
            c = [f.strip() for f in filter_list if f.isdigit()]
            t = [f.strip() for f in filter_list if f not in c]
            filter_list = FilterLists(c, t)

    visited_nodes.add(root_concept.conceptId)
    concept_children = concepts.get_concept_children(
        root_concept.conceptId, endpoint_builder=endpoint_builder
    )

    # If dump_mode is "semantic", only add concept to list when on the filter list
    if dump_mode == dump_mode.SEMANTIC and filter_list is not None:
        if (root_concept.conceptId in filter_list.codes) or dump_whole_subtree:
            # When a code and not a tag is on the filter list, the whole subtree should be regarded
            id_hash_set.add(root_concept.conceptId)
            dump_whole_subtree = True
        else:
            id_hash_set.update(
                c.conceptId
                for c in return_codes(
                    filter_by_semantic_tag(
                        root_concept,
                        tags=filter_list.tags,
                        positive=filter_mode == FilterMode.POSITIVE,
                    )
                )
            )
    else:
        id_hash_set.add(root_concept.conceptId)

    iteration += 1
    for code in return_codes(concept_children):
        _id_hash_set, _id_to_fsn_dict = dump_concept_ids(
            code,
            endpoint_builder,
            filter_list,
            filter_mode,
            dump_mode,
            is_not_recursive,
            up_to_including,
            iteration,
            id_hash_set,
            id_to_fsn_dict,
            dump_whole_subtree,
            visited_nodes,
        )
        id_hash_set.update(_id_hash_set)

    return set(id_hash_set), id_to_fsn_dict
