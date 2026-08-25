"""Snowstorm concept lookup and subtree traversal."""

from __future__ import annotations

from typing import Iterable, Optional, Tuple, Union

import scttsrapy.concepts as concepts
from scttsrapy.api import EndpointBuilder

from ..snomed import DumpMode, FilterLists, FilterMode, SnomedConcept
from .mapping import filter_by_semantic_tag, return_codes


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
    parent_map: dict[str, set[str]] = None,
    collect_parent_map: bool = True,
) -> Tuple[set[str], dict[str, str], dict[str, set[str]]]:
    """Dump concept IDs/FSNs below ``root_concept`` with optional filtering."""
    if visited_nodes is None:
        visited_nodes = set()
    if id_hash_set is None:
        id_hash_set = set()
    if id_to_fsn_dict is None:
        id_to_fsn_dict = {}
    if parent_map is None:
        parent_map = {}
    if root_concept is None or root_concept.conceptId is None:
        return id_hash_set, id_to_fsn_dict, parent_map
    if root_concept.conceptId not in id_to_fsn_dict:
        id_to_fsn_dict[root_concept.conceptId] = root_concept.fsn.term
    if root_concept.conceptId in visited_nodes:
        return id_hash_set, id_to_fsn_dict, parent_map
    if (is_not_recursive and iteration >= 2) or (
        not is_not_recursive
        and up_to_including != -1
        and iteration >= (up_to_including + 1)
    ):
        return id_hash_set, id_to_fsn_dict, parent_map
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
    if dump_mode == DumpMode.SEMANTIC and filter_list is not None:
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
        if collect_parent_map:
            parent_map.setdefault(code.conceptId, set()).add(root_concept.conceptId)
        if code.conceptId not in id_to_fsn_dict:
            id_to_fsn_dict[code.conceptId] = code.fsn.term
        _id_hash_set, _id_to_fsn_dict, _parent_map = dump_concept_ids(
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
            parent_map,
            collect_parent_map,
        )
        id_hash_set.update(_id_hash_set)
        parent_map.update(_parent_map)

    return set(id_hash_set), id_to_fsn_dict, parent_map
