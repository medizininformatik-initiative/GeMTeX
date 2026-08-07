"""Mapping/filtering helpers for Snowstorm API responses."""

from __future__ import annotations

import json
import logging
import re
from typing import Union, cast

from ..snomed import SnomedConcept, SnowstormResponse
from ..utils.text import flexible_whitespace_pattern


def return_codes(data: Union[dict, SnowstormResponse]) -> list[SnomedConcept]:
    return_list = []
    for concept in (
        snowstorm_response_to_pydantic(data) if isinstance(data, dict) else data
    ).content:
        return_list.append(concept)
    return return_list


def filter_by_semantic_tag(
    data: Union[dict, SnowstormResponse, SnomedConcept],
    tags: list[str] = None,
    positive: bool = True,
) -> SnowstormResponse:
    """Filter Snowstorm concepts by semantic tag in their FSN."""
    if isinstance(data, SnomedConcept):
        snowstorm_response = SnowstormResponse(success=True, content=[data])
    elif isinstance(data, SnowstormResponse):
        snowstorm_response = data
    else:
        if not data.get("success", False):
            return SnowstormResponse(success=False, content=[])
        snowstorm_response = snowstorm_response_to_pydantic(data)

    if tags is None:
        return snowstorm_response

    _backslash_car = "\\"
    re_tags = re.compile(
        rf"{'|'.join([rf'{_backslash_car}(' + flexible_whitespace_pattern(t) + rf'{_backslash_car})' for t in tags])}\)",
        re.IGNORECASE,
    )

    if positive:
        bool_check = lambda d: (
            len(re_tags.findall(cast(SnomedConcept, d).fsn.term.lower())) > 0
        )
    else:
        bool_check = lambda d: (
            len(re_tags.findall(cast(SnomedConcept, d).fsn.term.lower())) == 0
        )
    return SnowstormResponse(
        success=True, content=[d for d in snowstorm_response.content if bool_check(d)]
    )


def snowstorm_response_to_pydantic(json_data: dict):
    try:
        if not isinstance(json_data.get("content", []), list):
            json_data["content"] = [json_data.get("content", {})]
        json_dump = json.dumps(json_data, ensure_ascii=False)
    except Exception as e:
        logging.error(f"{e}")
        return SnowstormResponse(success=False, content=[])
    return SnowstormResponse.model_validate_json(json_dump)
