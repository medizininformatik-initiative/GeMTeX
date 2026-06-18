import json
import logging
import pathlib
import dataclasses
import sys
import zipfile
import gc
from collections import Counter
from io import TextIOWrapper
from typing import Union, Optional

import cassis
import h5py
import numpy as np
import yaspin
import randomname


if __name__.find(".uima_processing") != -1:
    from ..utils import ListDumpType, Information
else:
    sys.path.append(".")
    from utils import ListDumpType, Information


@dataclasses.dataclass
class DocumentAnnotations:
    snomed_codes: np.ndarray
    offsets: np.ndarray
    text: np.ndarray
    length: int


@dataclasses.dataclass
class TemporaryContainer:
    max_length: int
    documents: dict[str, DocumentAnnotations]


@dataclasses.dataclass
class TemporaryCorpus:
    annotators: dict[str, TemporaryContainer]


def _load_document(path: Union[str, pathlib.Path]) -> cassis.Cas:
    if isinstance(path, str):
        path = pathlib.Path(path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File '{path}' does not exist.")

    return cassis.load_cas_from_json(path.open("r", encoding="utf-8"))


def _read_project(zip_file: zipfile.ZipFile, file_name: str) -> Optional[list[dict]]:
    try:
        project_meta = json.loads(zip_file.read("exportedproject.json").decode("utf-8"))
    except KeyError:
        logging.warning(f"No exportedproject.json found in {file_name}")
        return None

    project_documents = project_meta.get("source_documents", [])
    if not project_documents:
        logging.warning(f"No source documents found in project {file_name}")
        return None
    return project_documents


def _yield_matching_files(
    project_documents: list[dict], zip_file: zipfile.ZipFile, file_name: str = None
):
    for doc in project_documents:
        doc_name = doc["name"]
        state = doc.get("state", "")

        # Determine path (curation or annotation)
        folder_prefix = (
            f"curation/{doc_name}/"
            if state == "CURATION_FINISHED"
            else f"annotation/{doc_name}/"
        )
        folder_prefix_ser = (
            f"curation_ser/{doc_name}/"
            if state == "CURATION_FINISHED"
            else f"annotation_ser/{doc_name}/"
        )

        # Collect CAS JSON files
        matching_files = [
            info.filename
            for info in zip_file.infolist()
            if (
                info.filename.startswith(folder_prefix)
                or info.filename.startswith(folder_prefix_ser)
            )
            and (
                info.filename.endswith(".json")
                or info.filename.endswith(".xmi")
                or info.filename.endswith(".zip")
                or info.filename.endswith(".ser")
            )
            and not info.is_dir()
        ]

        # Use INITIAL_CAS files only if they are the *only* files
        if len(matching_files) > 1:
            matching_files = [
                p
                for p in matching_files
                if not any(
                    p.endswith(ext)
                    for ext in [
                        "INITIAL_CAS.json",
                        "INITIAL_CAS.xmi",
                        "INITIAL_CAS.zip",
                        "INITIAL_CAS.ser",
                    ]
                )
            ]

        if not matching_files:
            logging.warning(
                f"No CAS found for {doc_name} in {file_name} ({folder_prefix}, {folder_prefix_ser})"
            )
            continue
        yield doc_name, matching_files


def _populate_dump_dictionary(
    dictionary: dict, code: str, offset: tuple[int, int], fsn: Optional[str] = None
):
    if code not in dictionary:
        dictionary[code] = {
            "offset": [offset],
        }
        if fsn is not None:
            dictionary[code]["fsn"] = fsn
    else:
        dictionary[code]["offset"].append(offset)


def get_annotations_from_document(
    document: Union[cassis.Cas, str, pathlib.Path],
    annotation_types: list[str] = None,
    id_prefix: str = "http://snomed.info/id/",
) -> DocumentAnnotations:
    if not annotation_types:
        annotation_types = ["gemtex.Concept"]
    id_prefix = id_prefix + "/" if not id_prefix.endswith("/") else id_prefix

    if not isinstance(document, cassis.Cas):
        document = _load_document(document)
    codes, offsets, text = [], [], []
    for type_ in annotation_types:
        for annotation in document.select(type_):
            try:
                if annotation.get("id") is not None:
                    _id = annotation.get("id")
                    codes.append(_id.removeprefix(id_prefix))
                else:
                    codes.append(np.nan)

                offsets.append(
                    (
                        annotation.begin,
                        annotation.end,
                    )
                )
                text.append(annotation.get_covered_text())
            except Exception:
                pass
    return DocumentAnnotations(
        snomed_codes=np.asarray(codes, dtype="bytes"),
        offsets=np.asarray(offsets, dtype="i,i"),
        text=np.asarray(text, dtype=np.dtypes.StringDType),
        length=len(codes),
    )


def get_annotator_names(project_path: pathlib.Path) -> tuple[set[str], bool]:
    annotator_names = set()
    only_ser = True
    found_any = False
    with zipfile.ZipFile(project_path, "r") as zip_file:
        file_name = project_path.name
        project_documents = _read_project(zip_file, file_name)
        if project_documents is not None:
            for _, fi in _yield_matching_files(project_documents, zip_file):
                for cp in fi:
                    found_any = True
                    annotator_names.add(str(pathlib.Path(cp).stem))
                    if not cp.endswith(".ser"):
                        only_ser = False
    return annotator_names, (only_ser if found_any else False)


def process_inception_zip(
    file_path: Union[str, pathlib.Path],
    annotator_filter=None,
    annotation_types: list[str] = None,
    id_prefix: str = "http://snomed.info/id/",
) -> TemporaryCorpus:
    if not annotation_types:
        annotation_types = ["gemtex.Concept"]

    # ---- Prepare containers ----
    annotations = TemporaryCorpus(annotators={})
    if isinstance(file_path, pathlib.Path):
        file_name = file_path.name
    else:
        file_name = pathlib.Path(file_path).name
    
    try:
        with zipfile.ZipFile(file_path, "r") as zip_file:
            # ---- Read project metadata ----
            project_documents = _read_project(zip_file, file_name)

            # ---- Process each document ----
            logging.info(f" Started processing project {file_name}")
            if annotator_filter is not None:
                logging.info(
                    f" Processing only following annotators: {annotator_filter}"
                )
            for doc_name, matching_files in _yield_matching_files(
                project_documents, zip_file, file_name
            ):
                # ---- Load each CAS, compute stats, discard CAS ----
                for cas_path in matching_files:
                    annotator_name = str(pathlib.Path(cas_path).stem)
                    if (
                        annotator_filter is not None
                        and annotator_name.lower() not in annotator_filter
                    ):
                        continue
                    try:
                        if cas_path.endswith(".ser"):
                            logging.warning(
                                f"Skipping {cas_path} from {file_name}: UIMA Java Serialized CAS (.ser) is not supported by 'cassis'. Please export as JSON CAS or XMI instead."
                            )
                            continue

                        with zip_file.open(cas_path) as cas_file:
                            cas = cassis.load_cas_from_json(cas_file)
                        doc_anno = get_annotations_from_document(
                            cas, annotation_types, id_prefix
                        )
                        if annotator_name not in annotations.annotators:
                            annotations.annotators[annotator_name] = TemporaryContainer(
                                max_length=0, documents={}
                            )
                        annotations.annotators[annotator_name].documents[doc_name] = (
                            doc_anno
                        )
                        annotations.annotators[annotator_name].max_length = (
                            doc_anno.length
                            if doc_anno.length
                            > annotations.annotators[annotator_name].max_length
                            else annotations.annotators[annotator_name].max_length
                        )
                        # Drop CAS immediately
                        del cas

                    except Exception as e:
                        logging.warning(
                            f"Failed to load {cas_path} from {file_name}: {e}"
                        )

        # Encourage cleanup
        gc.collect()

    except Exception as e:
        logging.error(f"Error processing {file_name}: {e}")
        return None

    return annotations


def analyze_documents(
    project: TemporaryCorpus,
    filter_array: np.ndarray,
    mapping_array: np.ndarray,
    filter_type: ListDumpType,
    log_doc: TextIOWrapper,
    log_doc_masked: TextIOWrapper,
    new_section: bool,
    section_count: dict[str, int],
    blacklist_tag_counter: Counter,
    whitelist_code_counter: Counter,
    progress_obj: Optional[dict] = None,
    dump_dictionary: Optional[dict] = None,
    filter_nan_values: bool = True,
) -> Optional[int]:
    as_whitelist = filter_type == ListDumpType.WHITELIST
    erroneous_doc_count = 0
    annotator_names_masked = {
        n: f"annotator-{randomname.get_name(adj=('age', 'character', 'emotions', 'appearance'))}"
        for n in project.annotators.keys()
    }
    documents_masked = {}

    with yaspin.yaspin() as spinner:
        annotator_names = sorted(project.annotators.keys())
        if len(annotator_names) <= 0:
            spinner.write("No annotators found.")
            return erroneous_doc_count
        annotator_names_max = len(max(annotator_names, key=len))
        for annotator_name, documents in project.annotators.items():
            new_annotator = True
            doc_error_count = 0
            concept_error_count = 0
            for i, (doc_name, annotations) in enumerate(documents.documents.items()):
                _text = f"Processing ({annotator_name} [{i + 1:>3}/{len(documents.documents)}]: '{doc_name}') ..."
                if doc_name not in documents_masked:
                    document_name_masked = randomname.get_name(
                        adj=(
                            "linguistics",
                            "construction",
                            "materials",
                            "geometry",
                            "algorithms",
                            "size",
                            "complexity",
                            "colors",
                        )
                    )
                    document_name_masked = f"document-{document_name_masked}"
                    documents_masked[doc_name] = document_name_masked
                else:
                    document_name_masked = documents_masked[doc_name]

                if progress_obj is not None:
                    progress_obj["current_progress"] = (
                        progress_obj["current_progress"]
                        + progress_obj["progress_increment"]
                    )
                    progress_obj["obj"].progress(
                        progress_obj["current_progress"],
                        progress_obj["text_pre"] + _text,
                    )
                spinner.text = _text
                nan_filter = (annotations.snomed_codes != b"nan") if filter_nan_values else np.ones(annotations.length, dtype=bool)
                if as_whitelist:
                    erroneous_codes_array = ~np.isin(
                        annotations.snomed_codes[nan_filter], filter_array
                    )
                else:
                    erroneous_codes_array = np.isin(
                        annotations.snomed_codes[nan_filter], filter_array
                    )

                if not np.all(~erroneous_codes_array):
                    doc_error_count += 1
                    concept_error_count += np.count_nonzero(erroneous_codes_array)
                    _map_dict = None
                    if not as_whitelist:
                        _map_dict = {}
                        idx = np.searchsorted(
                            filter_array,
                            annotations.snomed_codes[erroneous_codes_array],
                        )
                        for _idx in idx:
                            key = filter_array[_idx]
                            _map_dict[bytes(key)] = mapping_array[_idx]
                    log_critical_docs(
                        annotator_name,
                        doc_name,
                        document_name_masked,
                        annotations,
                        erroneous_codes_array,
                        log_doc,
                        log_doc_masked,
                        new_annotator,
                        as_whitelist,
                        _map_dict,
                        filter_type,
                        new_section,
                        section_count,
                        blacklist_tag_counter,
                        whitelist_code_counter,
                        annotator_names,
                        annotator_names_masked,
                        dump_dictionary,
                    )
                    new_section = False
                    new_annotator = False
            concept_error_text = f"- with {concept_error_count:>3} concept(s) {'not ' if as_whitelist else ''}on '{filter_type.name.lower()}'."
            spinner.write(
                f"{annotator_name}:{' ' * (annotator_names_max - len(annotator_name) + 1)}Done. {doc_error_count:>3} critical document(s) found {concept_error_text if doc_error_count > 0 else ''}"
            )
            erroneous_doc_count += doc_error_count
    return erroneous_doc_count


def log_critical_docs(
    annotator_name: str,
    document_name: str,
    document_name_masked: str,
    document_dump: DocumentAnnotations,
    bool_index_array: np.ndarray,
    output_file: TextIOWrapper,
    output_file_masked: TextIOWrapper,
    is_new_annotator: bool,
    is_whitelist: bool,
    mapping_dict: dict,
    filter_type: ListDumpType,
    new_section: bool,
    section_count: dict[str, int],
    blacklist_tag_counter: Counter,
    whitelist_code_counter: Counter,
    annotator_names: list[str],
    annotator_names_masked: dict[str, str],
    dump_dictionary: Optional[dict],
):
    stacked = np.stack(
        [
            document_dump.snomed_codes[bool_index_array],
            document_dump.text[bool_index_array],
            document_dump.offsets[bool_index_array],
            np.asarray(
                [
                    mapping_dict.get(x)
                    for x in document_dump.snomed_codes
                    if x in mapping_dict
                ]
            )
            if not is_whitelist
            else np.zeros(sum(bool_index_array)),
        ],
        axis=-1,
        dtype=object,
    )
    lines = []
    lines_masked = []

    if annotator_name not in section_count:
        section_count[annotator_name] = 0
    else:
        section_count[annotator_name] += 1
    if new_section:
        lines = [
            f"# {filter_type.name.capitalize()}\n",
            f"[Zum Inhalt](#{Information.log_dump_pretext_caption.lower()})  \n",
            "Zu den Annotator*innen: ",
        ]
        lines_masked = lines.copy()
        for n in annotator_names:
            lines.append(
                f"[{n}](#{n.lower()}{('-' + str(section_count.get(annotator_name))) if section_count.get(annotator_name) > 0 else ''}), "
            )
            lines_masked.append(
                f"[{annotator_names_masked.get(n)}](#{annotator_names_masked.get(n).lower()}{('-' + str(section_count.get(annotator_name))) if section_count.get(annotator_name) > 0 else ''}), "
            )
        for _lines in [lines, lines_masked]:
            if len(_lines) > 0:
                ll = _lines.pop(-1)
                _lines.append(ll[:-2])
            _lines.append("\n")
    if is_new_annotator:
        lines.append(
            f"## {annotator_name}\n([Zum Sektionsanfang](#{filter_type.name.lower()}))\n"
        )
        lines_masked.append(
            f"## {annotator_names_masked.get(annotator_name)}\n([Zum Sektionsanfang](#{filter_type.name.lower()}))\n"
        )

    lines.append(f"#### {document_name}\n")
    lines_masked.append(f"#### {document_name_masked}\n")

    for lines_ in [lines, lines_masked]:
        if is_whitelist:
            lines_.append("| Snomed CT Code | Covered Text | Offset in Document |\n")
            lines_.append("| -------------: | -----------: | -----------------: |\n")
            for line in stacked:
                code_, offset_ = line[0].decode("utf-8"), line[2]
                lines_.append(f"| {code_} | {line[1]} | {offset_} |\n")
                whitelist_code_counter.update([code_])
                if dump_dictionary is not None:
                    _populate_dump_dictionary(dump_dictionary, code_, offset_)
        else:
            lines_.append(
                "| Snomed CT Code | Covered Text | Offset in Document | FSN |\n"
            )
            lines_.append(
                "| -------------: | -----------: | -----------------: | --: |\n"
            )
            for line in stacked:
                code_, offset_, tag_ = (
                    line[0].decode("utf-8"),
                    line[2],
                    line[3].decode("utf-8"),
                )
                lines_.append(f"| {code_} | {line[1]} | {line[2]} | {tag_} |\n")
                blacklist_tag_counter.update([tag_.split("(", 1)[1].split(")")[0]])
                if dump_dictionary is not None:
                    _populate_dump_dictionary(dump_dictionary, code_, offset_, tag_)

    for tuple_ in [(output_file, lines), (output_file_masked, lines_masked)]:
        tuple_[0].writelines(tuple_[1])
        tuple_[0].write("\n\n")


def log_final_tag_count(
    whitelist_tag_counter: Counter,
    blacklist_tag_counter: Counter,
    output_file: TextIOWrapper,
    output_file_masked: TextIOWrapper,
):
    def no_count(list_type: str, out_: TextIOWrapper):
        is_whitelist = list_type == "whitelist"
        type_ = "SNOMED CT codes" if is_whitelist else "semantic tags"
        out_.write(
            f"_No {type_} found that are {'not ' if is_whitelist else ''}on the {list_type}_.\n"
        )

    for fi in [output_file, output_file_masked]:
        fi.write("# Final Count\n")
        fi.write("## Snomed CT Codes\n")
        fi.write(f"[Zum Inhalt](#{Information.log_dump_pretext_caption.lower()})  \n\n")
        if sum(whitelist_tag_counter.values()) > 0:
            fi.write("| Snomed CT Code | Count |\n")
            fi.write("| -------------: | ----: |\n")
            for code, count in whitelist_tag_counter.most_common():
                fi.write(f"| {code} | {count} |\n")
        else:
            no_count("whitelist", fi)
        fi.write("## Semantic Tags\n")
        fi.write(f"[Zum Inhalt](#{Information.log_dump_pretext_caption.lower()})  \n\n")
        if sum(blacklist_tag_counter.values()) > 0:
            fi.write("| Semantic Tag | Count |\n")
            fi.write("| -----------: | ----: |\n")
            for tag, count in blacklist_tag_counter.most_common():
                fi.write(f"| {tag} | {count} |\n")
        else:
            no_count("blacklist", fi)


def create_log_from_results(
    result: TemporaryCorpus,
    log_doc: TextIOWrapper,
    log_doc_masked: TextIOWrapper,
    lists: pathlib.Path,
    progress_obj: Optional[dict] = None,
    dump_dict: Optional[dict] = None,
) -> int:
    err_docs = 0
    log_doc.write(Information.log_dump_pretext)
    log_doc_masked.write(Information.log_dump_pretext)

    with h5py.File(lists.open("rb"), "r") as h5_file:
        blacklist_tag_counter = Counter()
        whitelist_code_counter = Counter()
        section_count = {}

        if progress_obj is not None:
            progress_increment = 1 / max(
                sum([len(x.documents) for x in result.annotators.values()]) * 2, 1
            )

        ft_iter = [ListDumpType.WHITELIST, ListDumpType.BLACKLIST]
        for i, ft in enumerate(ft_iter):
            print(f"-- {ft.name.capitalize()} --")
            group_name = ft.name.lower()
            if group_name in h5_file.keys():
                filter_list = h5_file.get(group_name).get("0").get("codes")
                fsn_list = h5_file.get(group_name).get("0").get("fsn")
                err_docs += analyze_documents(
                    project=result,
                    filter_array=filter_list[:],
                    mapping_array=fsn_list[:],
                    filter_type=ft,
                    log_doc=log_doc,
                    log_doc_masked=log_doc_masked,
                    new_section=True,
                    section_count=section_count,
                    blacklist_tag_counter=blacklist_tag_counter,
                    whitelist_code_counter=whitelist_code_counter,
                    progress_obj=(
                        None
                        if progress_obj is None
                        else {
                            "obj": progress_obj["obj"],
                            "text_pre": f"__{group_name.capitalize()}__: ",
                            "progress_increment": progress_increment,
                            "current_progress": 1.0 * (i / len(ft_iter)),
                        }
                    ),
                    dump_dictionary=dump_dict,
                )
        log_final_tag_count(
            whitelist_code_counter, blacklist_tag_counter, log_doc, log_doc_masked
        )
    return err_docs
