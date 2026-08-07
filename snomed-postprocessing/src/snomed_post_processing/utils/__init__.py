import logging
from typing import cast, Union

from ..snomed_models import (
    DumpMode,
    FilterLists,
    FilterMode,
    Information,
    ListDumpType,
    SnomedConcept,
    SnomedLanguage,
    SnomedTerm,
    SnowstormResponse,
)
from ..hdf5_handling.dump import (
    _compute_compact_ancestor_arrays,
    dump_codes_to_hdf5,
    hdf5_has_concepts_extension,
)
from ..inception_io import get_project_zip, prompt_for_names
import json
import re


def _flexible_whitespace_pattern(s: str) -> str:
    """
    Build a regex pattern from `s` where any whitespace sequence matches \\s+.
    Non-whitespace characters are escaped for regex.
    """
    escaped_parts = []
    i = 0
    while i < len(s):
        if s[i].isspace():
            while i < len(s) and s[i].isspace():
                i += 1
            escaped_parts.append(r"\s+")
        else:
            char = s[i]
            if char in r".^$*+?{}[]\|()":
                escaped_parts.append(re.escape(char))
            else:
                escaped_parts.append(char)
            i += 1
    return "".join(escaped_parts)



def pprint_json(json_data):
    print(json.dumps(json_data, indent=2))


def is_numeric(text: str) -> bool:
    """Check if the provided text is numeric (integer or decimal)."""
    import re

    return bool(re.fullmatch(r"(\d+([.,]\d+)?)", text.strip()))


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
    """
    Filters the results of e.g. "scttsrapy"´s `get_concept_children` by the respective "semantic tag".

    :param data: the result dict, containing at least a "content" field that features a list of concepts.
    :param tags: a list of the semantic tags to filter by (e.g. "disorder", "finding", etc.).
    :param positive: whether to include concepts with said semantic tags (`True`) or to exclude them (`False`).
    """
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
        rf"{'|'.join([rf'{_backslash_car}(' + _flexible_whitespace_pattern(t) + rf'{_backslash_car})' for t in tags])}\)",
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

