import dataclasses
import logging
import pathlib
from collections import deque
from typing import cast, Union, Optional

import h5py
import numpy as np
import yaspin
from PyInquirer import prompt
from pycaprio import Pycaprio
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


@dataclasses.dataclass
class Information:
    log_dump_pretext_caption: str = "Vorbemerkung"
    log_dump_pretext: str = (
        f"### {log_dump_pretext_caption}\n"
        "Manche Codes, die als 'blacklisted' gekenzeichnet sind, mögen ersteinmal verwundern, da sie den Semantic Tag `(qualifier value)` haben,\n"
        "der nicht verboten ist. Diese fallen dann jedoch unter die Kategorien `Overlapping sites` oder `action`,\n"
        "welche wiederum als ganzes ausgeschlossen wurden.\n\n"
        "Es folgt:\n"
        "* eine Auflistung nach Annotator*in und dazugehörige Dokumente für: [Whitelist](#whitelist) und [Blacklist](#blacklist)\n"
        "* eine Tabelle, mit allen gefundenen [Whitelist Codes](#snomed-ct-codes) (mit Anzahl über das gesamte Projekt)\n"
        "* eine Tabelle, mit allen gefundenen [Semantic Tags](#semantic-tags) (mit Anzahl über das gesamte Projekt)\n\n"
    )


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


def get_project_zip(
    process_path: str,
    host: str,
    user_name: Optional[str] = None,
    password: Optional[str] = None,
    project_name: Optional[str] = None,
    verify_ssl: Union[bool, str] = True,
) -> Union[pathlib.Path, list[str]]:
    inception_client = None
    project_zip = None
    projects = None
    use_local_zip = False

    if user_name is not None and password is not None:
        logging.info(
            f"Trying to find project '{project_name}' in INCEpTION instance at '{host}'."
        )
        try:
            inception_client = Pycaprio(host, (user_name, password))
            if not verify_ssl:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                inception_client.api.client.session.verify = False
            elif isinstance(verify_ssl, str):
                inception_client.api.client.session.verify = verify_ssl

            projects = {
                p.project_name: p.project_id for p in inception_client.api.projects()
            }
        except Exception as e:
            logging.error(
                f"Something went wrong while trying to connect to INCEpTION instance: '{e}'."
            )
            raise RuntimeError(f"Could not connect to INCEpTION instance: {e}")
    else:
        logging.info(
            f"Inception client credentials were not complete/given and/or no project name. Assuming zipped project under '{process_path}'."
        )
        use_local_zip = True

    if not use_local_zip:
        if project_name is None:
            if projects is not None:
                return list(projects.keys())
            else:
                raise ValueError(
                    "No project name given and no API connection established."
                )
        else:
            logging.info(f"Project name given: '{project_name}'.")

    if inception_client is None:
        project_zip = pathlib.Path(process_path).resolve()
        if (
            not project_zip.exists()
            or not project_zip.is_file()
            or not project_zip.suffix == ".zip"
        ):
            logging.error(f"Could not find project zip file '{process_path}'.")
            raise FileNotFoundError(
                f"Could not find project zip file '{process_path}'."
            )
    else:
        project = [
            p
            for p in projects
            if p.lower() == project_name.lower()
            or str(projects.get(p)) == project_name.lower()
        ]
        if len(project) == 0:
            logging.error(
                f"Could not find project '{project_name}' in INCEpTION instance at '{host}'. Did you forgot to use the 'URL slug' for the project?"
            )
            logging.error(
                f"Available projects: {', '.join([p.project_name.lower() for p in projects])}"
            )
            raise ValueError(f"Project '{project_name}' not found.")
        else:
            logging.info(f"Found project '{project_name}' in INCEpTION instance.")
            with yaspin.yaspin(text="Exporting project..."):
                project = project[0]
                project_id = projects.get(project)
                project_export = inception_client.api.export_project(
                    project_id, "jsoncas"
                )
                folder = pathlib.Path(process_path).resolve()
                if folder.is_file():
                    folder = folder.parent
                if not folder.exists():
                    folder.mkdir(parents=True)
                file_path = folder / pathlib.Path(project).with_suffix(".zip")
                logging.info(f"Exporting project '{project}' to '{file_path}'")
                with open(file_path, "wb") as f:
                    f.write(project_export)
            project_zip = file_path
    return project_zip


def prompt_for_names(annotator_names: set[str]):
    if len(annotator_names) <= 1:
        return None

    return_all_name = "return_all"
    return_all = prompt(
        [
            {
                "type": "confirm",
                "name": return_all_name,
                "message": "There are multiple annotators in the project. Do you want to log all of them?",
                "default": False,
            }
        ]
    )
    if return_all.get(return_all_name):
        return None

    annotator_choice_name = "menu_entry"
    annotator_names_chosen = prompt(
        [
            {
                "type": "checkbox",
                "name": annotator_choice_name,
                "message": "Please choose the annotators you want to log:",
                "choices": [{"name": _name} for _name in sorted(annotator_names)],
            }
        ]
    )
    return annotator_names_chosen.get(annotator_choice_name)


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


def hdf5_has_concepts_extension(fi_path: pathlib.Path) -> bool:
    if not fi_path.exists() or not fi_path.is_file():
        return False
    with h5py.File(str(fi_path.resolve()), "r") as h5_file:
        return "concepts" in h5_file


def _compute_ancestors_bfs(
    code: str, parent_map: dict[str, set[str]]
) -> dict[str, int]:
    distances = {}
    queue = deque((parent, 1) for parent in sorted(parent_map.get(code, set())))
    while queue:
        ancestor, distance = queue.popleft()
        if ancestor in distances and distances[ancestor] <= distance:
            continue
        distances[ancestor] = distance
        queue.extend(
            (parent, distance + 1)
            for parent in sorted(parent_map.get(ancestor, set()))
        )
    return distances


def _compute_ancestors_memoized(
    code: str,
    parent_map: dict[str, set[str]],
    memo: dict[str, dict[str, int]],
    visiting: Optional[set[str]] = None,
) -> dict[str, int]:
    if code in memo:
        return memo[code]
    if visiting is None:
        visiting = set()
    if code in visiting:
        return {}

    visiting.add(code)
    distances = {}
    for parent in sorted(parent_map.get(code, set())):
        if parent not in distances or distances[parent] > 1:
            distances[parent] = 1
        for ancestor, distance in _compute_ancestors_memoized(
            parent, parent_map, memo, visiting
        ).items():
            candidate_distance = distance + 1
            if (
                ancestor not in distances
                or distances[ancestor] > candidate_distance
            ):
                distances[ancestor] = candidate_distance
    visiting.remove(code)
    memo[code] = distances
    return distances


def _compute_compact_ancestor_arrays(
    id_to_fsn_dict: dict[str, str],
    parent_map: dict[str, set[str]],
    use_memoization: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    all_codes = sorted(
        set(id_to_fsn_dict.keys())
        | set(parent_map.keys())
        | {parent for parents in parent_map.values() for parent in parents}
    )
    ancestor_codes_flat = []
    ancestor_distances_flat = []
    ancestor_index = []

    memo = {} if use_memoization else None
    for code in all_codes:
        start = len(ancestor_codes_flat)
        distances = (
            _compute_ancestors_memoized(code, parent_map, memo)
            if use_memoization
            else _compute_ancestors_bfs(code, parent_map)
        )

        for ancestor, distance in sorted(distances.items(), key=lambda x: (x[1], x[0])):
            ancestor_codes_flat.append(ancestor)
            ancestor_distances_flat.append(distance)
        ancestor_index.append((start, len(ancestor_codes_flat) - start))

    return (
        np.asarray(all_codes, dtype=np.dtypes.StringDType),
        np.asarray(ancestor_index, dtype=np.int64),
        np.asarray(ancestor_codes_flat, dtype=np.dtypes.StringDType),
        np.asarray(ancestor_distances_flat, dtype=np.int32),
    )


def _write_concepts_extension(
    fi: h5py.File,
    id_to_fsn_dict: dict[str, str],
    parent_map: dict[str, set[str]],
    force_overwrite: bool = False,
    use_memoization: bool = False,
):
    if "concepts" in fi:
        if force_overwrite:
            del fi["concepts"]
        else:
            logging.warning(
                "HDF5 concepts extension already exists and 'force_overwrite' is FALSE. Skipping."
            )
            return

    codes, ancestor_index, ancestor_codes, ancestor_distances = (
        _compute_compact_ancestor_arrays(
            id_to_fsn_dict, parent_map, use_memoization=use_memoization
        )
    )
    concept_group = fi.create_group("concepts")
    fsn = np.asarray(
        [id_to_fsn_dict.get(code, "") for code in codes],
        dtype=np.dtypes.StringDType,
    )

    ds_codes = concept_group.create_dataset("codes", shape=(codes.shape[0],), dtype="T")
    ds_codes[:] = codes
    ds_fsn = concept_group.create_dataset("fsn", shape=(fsn.shape[0],), dtype="T")
    ds_fsn[:] = fsn
    concept_group.create_dataset("ancestors_index", data=ancestor_index)
    ds_ancestor_codes = concept_group.create_dataset(
        "ancestors_codes", shape=(ancestor_codes.shape[0],), dtype="T"
    )
    ds_ancestor_codes[:] = ancestor_codes
    concept_group.create_dataset("ancestors_distance", data=ancestor_distances)


def dump_codes_to_hdf5(
    fi_path: pathlib.Path,
    codes: set,
    id_to_fsn_dict: dict[str, str],
    list_type: ListDumpType,
    revision: bool = True,
    force_overwrite: bool = False,
    parent_map: Optional[dict[str, set[str]]] = None,
    use_memoization: bool = False,
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
                    # ToDo: Implement revision
                    logging.warning(
                        f"Dataset '{dataset_name}' already exists and 'force_overwrite' is FALSE. Revision is not yet implemented. Skipping."
                    )
            else:
                _create_dataset(f, dataset_name, codes, id_to_fsn_dict)

        if parent_map is not None:
            _write_concepts_extension(
                f,
                id_to_fsn_dict,
                parent_map,
                force_overwrite=force_overwrite,
                use_memoization=use_memoization,
            )
