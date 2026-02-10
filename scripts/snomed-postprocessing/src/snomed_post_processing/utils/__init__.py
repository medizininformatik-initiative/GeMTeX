import logging
import pathlib
from typing import cast, Union

import h5py
import numpy as np
from pydantic import BaseModel
import enum
import json
import re


class SnomedLanguage(enum.Enum):
    DE = "de"
    EN = "en"
    NONE = None

    @classmethod
    def _missing_(cls, value):
        return cls.NONE


class SnomedTerm(BaseModel):
    term: str
    lang: SnomedLanguage


class SnomedConcept(BaseModel):
    conceptId: str
    fsn: SnomedTerm
    pt: SnomedTerm


class SnowstormResponse(BaseModel):
    success: bool
    content: list[SnomedConcept]


class DumpMode(enum.Enum):
    SEMANTIC = enum.auto()
    VERSION = enum.auto()


class FilterMode(enum.Enum):
    POSITIVE = enum.auto()
    NEGATIVE = enum.auto()


class ListDumpType(enum.Enum):
    BLACKLIST = enum.auto()
    WHITELIST = enum.auto()


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


def return_codes(
    data: Union[dict, SnowstormResponse]
):
    return_list = []
    for concept in (snowstorm_response_to_pydantic(data) if isinstance(data, dict) else data).content:
        return_list.append(concept.conceptId)
    return return_list


def filter_by_semantic_tag(
    json_data: dict, tags: list[str] = None, positive: bool = True
) -> SnowstormResponse:
    """
    Filters the results of e.g. "scttsrapy"´s `get_concept_children` by the respective "semantic tag".

    :param json_data: the result dict, containing at least a "content" field that features a list of concepts.
    :param tags: a list of the semantic tags to filter by (e.g. "disorder", "finding", etc.).
    :param positive: whether to include concepts with said semantic tags (`True`) or to exclude them (`False`).
    """
    if not json_data.get("success", False):
        return SnowstormResponse(
            success=False,
            content=[]
        )
    snowstorm_response = snowstorm_response_to_pydantic(json_data)
    if tags is None:
        return snowstorm_response

    re_tags = re.compile(fr"\({"|".join([_flexible_whitespace_pattern(t) for t in tags])}\)", re.IGNORECASE)

    if positive:
        bool_check = lambda d: (
                len(re_tags.findall(cast(SnomedConcept, d).fsn.term.lower())) > 0
        )
    else:
        bool_check = lambda d: (
                len(re_tags.findall(cast(SnomedConcept, d).fsn.term.lower())) == 0
        )
    return SnowstormResponse(
        success=True,
        content=[d for d in snowstorm_response.content if bool_check(d)]
    )


def snowstorm_response_to_pydantic(
    json_data: dict
):
    return SnowstormResponse.model_validate_json(json.dumps(json_data, ensure_ascii=False))


def dump_codes_to_hdf5(fi_path: pathlib.Path, codes: set, list_type: ListDumpType, append: bool = True, force_overwrite: bool = False):
    def _create_dataset(fi, name, content):
        return fi.create_dataset(name, np.array(list(content)), maxshape=(None,))

    dataset_name = str(list_type)
    file_exists = False
    if fi_path.exists():
        file_exists = True

    with h5py.File(str(fi_path.resolve()), "r+" if file_exists else "a") as f:
        dataset_exists = dataset_name in f.keys()

        if file_exists and dataset_exists and not (force_overwrite or append):
            logging.error(f"Dataset '{dataset_name}' already exists.")
            return

        if not file_exists:
            _create_dataset(f, dataset_name, np.array(list(codes)))
        else:
            if dataset_exists:
                if force_overwrite:
                    del f[dataset_name]
                    _create_dataset(f, dataset_name, np.array(list(codes)))
                elif append:
                    df: np.ndarray = f[dataset_name]
                    df.resize(df.shape[0] + len(codes))
                    df[-len(codes):] = np.array(list(codes))
            else:
                _create_dataset(f, dataset_name, np.array(list(codes)))