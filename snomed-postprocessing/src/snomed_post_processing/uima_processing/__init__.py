import json
import logging
import pathlib
import dataclasses
import sys
import zipfile
import gc
import re
from collections import Counter
from io import StringIO, TextIOWrapper
from typing import Union, Optional

import cassis
import h5py
import numpy as np
import yaspin
import randomname


from ..utils import ListDumpType, Information, is_numeric


@dataclasses.dataclass
class IgnoreOverlap:
    layer: str
    offset: tuple[int, int]
    text: str


@dataclasses.dataclass
class DocumentAnnotations:
    snomed_codes: np.ndarray
    offsets: np.ndarray
    text: np.ndarray
    layers: np.ndarray
    length: int
    ignore_mask: np.ndarray = dataclasses.field(default_factory=lambda: np.asarray([], dtype=bool))
    ignore_overlaps: list[list[IgnoreOverlap]] = dataclasses.field(default_factory=list)


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
    project_documents: list[dict],
    zip_file: zipfile.ZipFile,
    file_name: str = None,
    allowed_extensions: Optional[list[str]] = None,
):
    for doc in project_documents:
        doc_name = doc["name"]
        state = doc.get("state", "")

        # Determine paths (curation and annotation)
        prefixes = [
            f"curation/{doc_name}/",
            f"annotation/{doc_name}/",
            f"curation_ser/{doc_name}/",
            f"annotation_ser/{doc_name}/",
        ]

        # Collect CAS files
        matching_files = [
            info.filename
            for info in zip_file.infolist()
            if any(info.filename.startswith(p) for p in prefixes)
            and (
                allowed_extensions is None
                or any(info.filename.endswith(ext) for ext in allowed_extensions)
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
                    for ext in (
                        [f"INITIAL_CAS{ext}" for ext in allowed_extensions]
                        if allowed_extensions is not None
                        else [
                            "INITIAL_CAS.json",
                            "INITIAL_CAS.xmi",
                            "INITIAL_CAS.zip",
                            "INITIAL_CAS.ser",
                        ]
                    )
                )
            ]

        if not matching_files:
            logging.warning(
                f"No CAS found for {doc_name} in {file_name} searched in {prefixes}"
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


def spans_match(
    target: tuple[int, int], ignore: tuple[int, int], mode: str = "overlap"
) -> bool:
    target_begin, target_end = target
    ignore_begin, ignore_end = ignore
    if mode == "exact":
        return target_begin == ignore_begin and target_end == ignore_end
    if mode == "covered-by":
        return target_begin >= ignore_begin and target_end <= ignore_end
    if mode == "contains":
        return target_begin <= ignore_begin and target_end >= ignore_end
    if mode == "overlap":
        return target_begin < ignore_end and ignore_begin < target_end
    raise ValueError(f"Unknown overlap mode: '{mode}'.")


def _safe_select(document: cassis.Cas, type_: str):
    try:
        yield from document.select(type_)
    except Exception as e:
        logging.debug(f"Could not select annotations of type '{type_}': {e}")


def get_annotations_from_document(
    document: Union[cassis.Cas, str, pathlib.Path],
    annotation_types: list[str] = None,
    id_prefix: str = "http://snomed.info/id/",
    ignore_overlap_types: Optional[list[str]] = None,
    ignore_overlap_mode: str = "overlap",
) -> DocumentAnnotations:
    if not annotation_types:
        annotation_types = ["gemtex.Concept"]
    if ignore_overlap_types is None:
        ignore_overlap_types = []
    id_prefix = id_prefix + "/" if not id_prefix.endswith("/") else id_prefix
    id_prefix = id_prefix.lower()

    if not isinstance(document, cassis.Cas):
        document = _load_document(document)

    ignore_spans: list[IgnoreOverlap] = []
    for type_ in ignore_overlap_types:
        for annotation in _safe_select(document, type_):
            try:
                ignore_spans.append(
                    IgnoreOverlap(
                        layer=type_,
                        offset=(annotation.begin, annotation.end),
                        text=annotation.get_covered_text(),
                    )
                )
            except Exception:
                pass

    codes, offsets, text, layers, ignore_mask, ignore_overlaps = [], [], [], [], [], []
    for type_ in annotation_types:
        for annotation in _safe_select(document, type_):
            try:
                _id = annotation.get("id")
                if _id is None:
                    codes.append(np.nan)
                else:
                    _id = str(_id).strip().lower().removeprefix(id_prefix).strip()
                    if _id in {"", "null", "none", "nan"}:
                        codes.append(np.nan)
                    else:
                        codes.append(_id)

                offset = (annotation.begin, annotation.end)
                overlaps = [
                    ignore
                    for ignore in ignore_spans
                    if spans_match(offset, ignore.offset, ignore_overlap_mode)
                ]
                offsets.append(offset)
                text.append(annotation.get_covered_text())
                layers.append(type_)
                ignore_mask.append(len(overlaps) > 0)
                ignore_overlaps.append(overlaps)
            except Exception:
                pass
    return DocumentAnnotations(
        snomed_codes=np.asarray(codes, dtype="bytes"),
        offsets=np.asarray(offsets, dtype="i,i"),
        text=np.asarray(text, dtype=np.dtypes.StringDType),
        layers=np.asarray(layers, dtype=np.dtypes.StringDType),
        length=len(codes),
        ignore_mask=np.asarray(ignore_mask, dtype=bool),
        ignore_overlaps=ignore_overlaps,
    )


def get_annotator_names(
    project_path: pathlib.Path, allowed_extensions: Optional[list[str]] = None
) -> tuple[set[str], bool]:
    annotator_names = set()
    only_ser = True
    found_any = False
    with zipfile.ZipFile(project_path, "r") as zip_file:
        file_name = project_path.name
        project_documents = _read_project(zip_file, file_name)
        if project_documents is not None:
            for _, fi in _yield_matching_files(
                project_documents,
                zip_file,
                allowed_extensions=allowed_extensions,
            ):
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
    allowed_extensions: Optional[list[str]] = None,
    ignore_overlap_types: Optional[list[str]] = None,
    ignore_overlap_mode: str = "overlap",
) -> TemporaryCorpus:
    if not annotation_types:
        annotation_types = ["gemtex.Concept"]
    if ignore_overlap_types is None:
        ignore_overlap_types = []

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
                project_documents,
                zip_file,
                file_name,
                allowed_extensions=allowed_extensions,
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
                            cas,
                            annotation_types,
                            id_prefix,
                            ignore_overlap_types=ignore_overlap_types,
                            ignore_overlap_mode=ignore_overlap_mode,
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
    ignored_log_doc: Optional[TextIOWrapper] = None,
    ignored_log_doc_masked: Optional[TextIOWrapper] = None,
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
            skipped_doc_count = 0
            ignored_new_annotator = True
            ignored_new_section = True
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
                try:
                    nan_filter = (annotations.snomed_codes != b"nan") if filter_nan_values else np.ones(annotations.length, dtype=bool)
                    erroneous_codes_array = np.zeros(annotations.length, dtype=bool)
                    if as_whitelist:
                        erroneous_codes_array[nan_filter] = ~np.isin(
                            annotations.snomed_codes[nan_filter], filter_array
                        )
                    else:
                        erroneous_codes_array[nan_filter] = np.isin(
                            annotations.snomed_codes[nan_filter], filter_array
                        )
    
                    if not np.all(~erroneous_codes_array):
                        # Filter out numerical spans without a code in whitelist mode
                        if as_whitelist:
                            actual_indices = np.where(erroneous_codes_array)[0]
                            final_erroneous_indices_mask = np.ones(
                                len(actual_indices), dtype=bool
                            )
                            for idx_in_err, idx_in_doc in enumerate(actual_indices):
                                code = annotations.snomed_codes[idx_in_doc]
                                text = str(annotations.text[idx_in_doc])
                                if code == b"nan" and is_numeric(text):
                                    final_erroneous_indices_mask[idx_in_err] = False
    
                            if not np.any(final_erroneous_indices_mask):
                                # All erroneous codes were numerical spans without a code
                                continue
    
                            # Update erroneous_codes_array to exclude numerical spans
                            erroneous_codes_array[
                                actual_indices[~final_erroneous_indices_mask]
                            ] = False
    
                        ignored_codes_array = erroneous_codes_array & annotations.ignore_mask
                        actionable_codes_array = erroneous_codes_array & ~annotations.ignore_mask
    
                        _map_dict = None
                        if not as_whitelist:
                            _map_dict = {}
                            erroneous_codes = annotations.snomed_codes[erroneous_codes_array]
                            idx = np.searchsorted(filter_array, erroneous_codes)
                            for code, _idx in zip(erroneous_codes, idx):
                                if _idx < len(filter_array) and filter_array[_idx] == code:
                                    _map_dict[bytes(code)] = mapping_array[_idx]
    
                        if np.any(actionable_codes_array):
                            doc_error_count += 1
                            concept_error_count += np.count_nonzero(actionable_codes_array)
                            log_critical_docs(
                                annotator_name,
                                doc_name,
                                document_name_masked,
                                annotations,
                                actionable_codes_array,
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
    
                        if np.any(ignored_codes_array):
                            log_ignored_faulty_docs(
                                annotator_name,
                                doc_name,
                                document_name_masked,
                                annotations,
                                ignored_codes_array,
                                ignored_log_doc or log_doc,
                                ignored_log_doc_masked or log_doc_masked,
                                ignored_new_annotator,
                                as_whitelist,
                                _map_dict,
                                filter_type,
                                ignored_new_section,
                                annotator_names_masked,
                            )
                            ignored_new_section = False
                            ignored_new_annotator = False
                except Exception as e:
                    skipped_doc_count += 1
                    logging.exception(
                        f"Skipping document due to an analysis/logging error ({filter_type.name.lower()}): annotator={annotator_name!r}, document={doc_name!r}: {e}"
                    )
                    log_skipped_document(
                        annotator_name=annotator_name,
                        document_name=doc_name,
                        document_name_masked=document_name_masked,
                        output_file=log_doc,
                        output_file_masked=log_doc_masked,
                        filter_type=filter_type,
                        annotator_names_masked=annotator_names_masked,
                        error=e,
                    )
                    continue
            concept_error_text = f"- with {concept_error_count:>3} concept(s) {'not ' if as_whitelist else ''}on '{filter_type.name.lower()}'."
            skipped_text = (
                f" {skipped_doc_count:>3} document(s) skipped due to errors."
                if skipped_doc_count > 0
                else ""
            )
            spinner.write(
                f"{annotator_name}:{' ' * (annotator_names_max - len(annotator_name) + 1)}Done. {doc_error_count:>3} critical document(s) found {concept_error_text if doc_error_count > 0 else ''}{skipped_text}"
            )
            erroneous_doc_count += doc_error_count
    return erroneous_doc_count


def log_skipped_document(
    annotator_name: str,
    document_name: str,
    document_name_masked: str,
    output_file: TextIOWrapper,
    output_file_masked: TextIOWrapper,
    filter_type: ListDumpType,
    annotator_names_masked: dict[str, str],
    error: Exception,
):
    section = f"Skipped documents ({filter_type.name.lower()})"
    lines = [
        f"# {section}\n",
        f"[Zum Inhalt](#{Information.log_dump_pretext_caption.lower()})  \n\n",
        "These documents were skipped because an error occurred while analyzing or writing their findings. The rest of the run continued.\n\n",
        "| Annotator | Document | Check | Error |\n",
        "| --: | --: | --: | --: |\n",
        f"| {annotator_name} | {document_name} | {filter_type.name.lower()} | {type(error).__name__}: {error} |\n",
    ]
    lines_masked = [
        f"# {section}\n",
        f"[Zum Inhalt](#{Information.log_dump_pretext_caption.lower()})  \n\n",
        "These documents were skipped because an error occurred while analyzing or writing their findings. The rest of the run continued.\n\n",
        "| Annotator | Document | Check | Error |\n",
        "| --: | --: | --: | --: |\n",
        f"| {annotator_names_masked.get(annotator_name)} | {document_name_masked} | {filter_type.name.lower()} | {type(error).__name__}: {error} |\n",
    ]
    for tuple_ in [(output_file, lines), (output_file_masked, lines_masked)]:
        tuple_[0].writelines(tuple_[1])
        tuple_[0].write("\n\n")


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
    selected_codes = document_dump.snomed_codes[bool_index_array]
    stacked = np.stack(
        [
            selected_codes,
            document_dump.text[bool_index_array],
            document_dump.offsets[bool_index_array],
            np.asarray([mapping_dict.get(bytes(x), b"") for x in selected_codes])
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

    if is_whitelist:
        for lines_ in [lines, lines_masked]:
            lines_.append("| Snomed CT Code | Covered Text | Offset in Document |\n")
            lines_.append("| -------------: | -----------: | -----------------: |\n")
            for line in stacked:
                code_, offset_ = line[0].decode("utf-8"), line[2]
                lines_.append(f"| {code_} | {line[1]} | {offset_} |\n")
        for line in stacked:
            code_, offset_ = line[0].decode("utf-8"), line[2]
            whitelist_code_counter.update([code_])
            if dump_dictionary is not None:
                _populate_dump_dictionary(dump_dictionary, code_, offset_)
    else:
        for lines_ in [lines, lines_masked]:
            lines_.append(
                "| Snomed CT Code | Covered Text | Offset in Document | FSN |\n"
            )
            lines_.append(
                "| -------------: | -----------: | -----------------: | --: |\n"
            )
            for line in stacked:
                code_, tag_ = line[0].decode("utf-8"), line[3].decode("utf-8")
                lines_.append(f"| {code_} | {line[1]} | {line[2]} | {tag_} |\n")
        for line in stacked:
            code_, offset_, tag_ = (
                line[0].decode("utf-8"),
                line[2],
                line[3].decode("utf-8"),
            )
            match = re.search(r"\(([^()]*)\)\s*$", tag_)
            blacklist_tag_counter.update([match.group(1) if match else ""])
            if dump_dictionary is not None:
                _populate_dump_dictionary(dump_dictionary, code_, offset_, tag_)

    for tuple_ in [(output_file, lines), (output_file_masked, lines_masked)]:
        tuple_[0].writelines(tuple_[1])
        tuple_[0].write("\n\n")


def _format_overlap_layers(overlaps: list[IgnoreOverlap]) -> str:
    if not overlaps:
        return ""
    return ", ".join(sorted({overlap.layer for overlap in overlaps}))


def log_ignored_faulty_docs(
    annotator_name: str,
    document_name: str,
    document_name_masked: str,
    document_dump: DocumentAnnotations,
    bool_index_array: np.ndarray,
    output_file: TextIOWrapper,
    output_file_masked: TextIOWrapper,
    is_new_annotator: bool,
    is_whitelist: bool,
    mapping_dict: Optional[dict],
    filter_type: ListDumpType,
    new_section: bool,
    annotator_names_masked: dict[str, str],
):
    reason = "not_in_whitelist" if is_whitelist else "blacklisted"
    lines = []
    lines_masked = []
    if new_section:
        lines.extend(
            [
                f"## {filter_type.name.capitalize()}\n",
                f"[Zum Inhalt](#{Information.log_dump_pretext_caption.lower()})  \n\n",
            ]
        )
        lines_masked.extend(lines)
    if is_new_annotator:
        lines.append(f"### {annotator_name}\n")
        lines_masked.append(f"### {annotator_names_masked.get(annotator_name)}\n")
    lines.append(f"#### {document_name}\n")
    lines_masked.append(f"#### {document_name_masked}\n")

    columns = [
        "Target Layer",
        "Snomed CT Code",
        "Covered Text",
        "Offset in Document",
        "Reason",
        "Overlapping Ignore Layer(s)",
    ]
    if not is_whitelist:
        columns.append("FSN")
    header = "| " + " | ".join(columns) + " |\n"
    separator = "| " + " | ".join(["--:"] * len(columns)) + " |\n"

    for lines_ in (lines, lines_masked):
        lines_.append(header)
        lines_.append(separator)

    for idx in np.where(bool_index_array)[0]:
        code = document_dump.snomed_codes[idx].decode("utf-8")
        target_layer = str(document_dump.layers[idx])
        text = str(document_dump.text[idx])
        offset = document_dump.offsets[idx]
        overlaps = document_dump.ignore_overlaps[idx]
        overlap_layers = _format_overlap_layers(overlaps)
        fsn = ""
        if not is_whitelist and mapping_dict is not None:
            fsn_value = mapping_dict.get(bytes(document_dump.snomed_codes[idx]))
            if fsn_value is not None:
                fsn = fsn_value.decode("utf-8")

        row = f"| {target_layer} | {code} | {text} | {offset} | {reason} | {overlap_layers}"
        if not is_whitelist:
            row += f" | {fsn}"
        row += " |\n"
        lines.append(row)
        lines_masked.append(row)

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

    with h5py.File(lists, "r") as h5_file:
        blacklist_tag_counter = Counter()
        whitelist_code_counter = Counter()
        section_count = {}

        if progress_obj is not None:
            progress_increment = 1 / max(
                sum([len(x.documents) for x in result.annotators.values()]) * 2, 1
            )

        ignored_sections: list[tuple[str, str]] = []
        ft_iter = [ListDumpType.WHITELIST, ListDumpType.BLACKLIST]
        for i, ft in enumerate(ft_iter):
            print(f"-- {ft.name.capitalize()} --")
            group_name = ft.name.lower()
            if group_name in h5_file.keys():
                filter_list = h5_file.get(group_name).get("0").get("codes")[:]
                fsn_list = h5_file.get(group_name).get("0").get("fsn")[:]
            elif (
                "policy_views" in h5_file
                and group_name in h5_file["policy_views"]
                and "concepts" in h5_file
            ):
                concept_indices = h5_file["policy_views"][group_name]["0"]["concept_index"][:]
                filter_list = h5_file["concepts"]["codes"][:][concept_indices]
                fsn_list = h5_file["concepts"]["fsn"][:][concept_indices]
            else:
                continue
            ignored_log_doc = StringIO()
            ignored_log_doc_masked = StringIO()
            err_docs += analyze_documents(
                project=result,
                filter_array=filter_list,
                mapping_array=fsn_list,
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
                ignored_log_doc=ignored_log_doc,
                ignored_log_doc_masked=ignored_log_doc_masked,
            )
            if ignored_log_doc.getvalue():
                ignored_sections.append(
                    (ignored_log_doc.getvalue(), ignored_log_doc_masked.getvalue())
                )
        if ignored_sections:
            for fi in (log_doc, log_doc_masked):
                fi.write("# Ignored faulty concepts\n")
                fi.write(f"[Zum Inhalt](#{Information.log_dump_pretext_caption.lower()})  \n\n")
                fi.write(
                    "These concepts would have been reported as faulty, but were ignored because they overlap with configured ignore layer(s).\n\n"
                )
            for ignored_text, ignored_text_masked in ignored_sections:
                log_doc.write(ignored_text)
                log_doc_masked.write(ignored_text_masked)
        log_final_tag_count(
            whitelist_code_counter, blacklist_tag_counter, log_doc, log_doc_masked
        )
    return err_docs
