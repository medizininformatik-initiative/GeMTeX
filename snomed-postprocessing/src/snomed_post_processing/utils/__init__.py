import dataclasses
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


@dataclasses.dataclass
class FilterLists:
    codes: list[str]
    tags: list[str]


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


def return_codes(data: Union[dict, SnowstormResponse]) -> list[SnomedConcept]:
    return_list = []
    for concept in (
        snowstorm_response_to_pydantic(data) if isinstance(data, dict) else data
    ).content:
        return_list.append(concept)
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
        return SnowstormResponse(success=False, content=[])
    snowstorm_response = snowstorm_response_to_pydantic(json_data)
    if tags is None:
        return snowstorm_response

    re_tags = re.compile(
        rf"\({'|'.join([_flexible_whitespace_pattern(t) for t in tags])}\)",
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


def dump_codes_to_hdf5(
    fi_path: pathlib.Path,
    codes: set,
    id_to_fsn_dict: dict[str, str],
    list_type: ListDumpType,
    revision: bool = True,
    force_overwrite: bool = False,
):
    def _create_dataset(
        fi: h5py.File, name: str, content: Union[set, list, np.ndarray], mappings: dict
    ):
        if name in fi:
            group = fi[f"/{name}"]
        else:
            group = fi.create_group(name)

        _last = (
            sorted(int(k) for k in group.keys())[-1] if len(group.keys()) > 0 else -1
        )
        last_group = group.create_group(str(_last + 1))

        code_data = (
            np.array(sorted(content))
            if not isinstance(content, np.ndarray)
            else content
        )
        fsn_data = np.array(
            [
                mappings.get(code)
                for code in (
                    sorted(content) if not isinstance(content, np.ndarray) else content
                )
            ]
        )

        ds_codes = last_group.create_dataset(
            "codes", shape=(code_data.shape[0],), dtype="T"
        )
        ds_codes[:] = code_data
        fs_codes = last_group.create_dataset(
            "fsn", shape=(fsn_data.shape[0],), dtype="T"
        )
        fs_codes[:] = fsn_data

    dataset_name = list_type.name.lower()
    file_exists = False
    if fi_path.exists():
        file_exists = True

    with h5py.File(str(fi_path.resolve()), "r+" if file_exists else "a") as f:
        dataset_exists = dataset_name in f.keys()

        if file_exists and dataset_exists and not (force_overwrite or revision):
            logging.error(f"Dataset '{dataset_name}' already exists.")
            return

        if not file_exists:
            _create_dataset(f, dataset_name, codes, id_to_fsn_dict)
        else:
            if dataset_exists:
                if force_overwrite:
                    del f[dataset_name]
                    _create_dataset(f, dataset_name, codes, id_to_fsn_dict)
                elif revision:
                    pass
                    # df: np.ndarray = f[dataset_name]
                    # df.resize(df.shape[0] + len(codes))
                    # df[-len(codes):] = np.array(list(codes))
                    # comment
            else:
                _create_dataset(f, dataset_name, codes, id_to_fsn_dict)
