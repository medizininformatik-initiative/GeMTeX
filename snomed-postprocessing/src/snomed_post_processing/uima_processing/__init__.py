import logging
import pathlib
import zipfile
import gc
import re
from collections import Counter
from io import TextIOWrapper
from typing import Union, Optional

import cassis
import h5py
import numpy as np
import yaspin
import randomname


from ..utils import ListDumpType, Information, is_numeric
from ..hdf5_policy import read_policy_data
from .models import (
    CriticalFinding,
    DocumentAnnotations,
    IgnoreOverlap,
    TemporaryContainer,
    TemporaryCorpus,
)
from .io import (
    _annotator_name_from_cas_path,
    _load_cas_from_zip_member,
    _load_document,
    _load_typesystem_from_zip,
    _prefer_non_ser_files,
    _read_project,
    _yield_flat_archive_files,
    _yield_matching_files,
)


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
        matched_files = list(
            _yield_matching_files(
                project_documents,
                zip_file,
                file_name,
                allowed_extensions=allowed_extensions,
            )
        )
        flat_files = list(
            _yield_flat_archive_files(
                zip_file,
                allowed_extensions=allowed_extensions,
            )
        )
        fallback_flat_layout = project_documents is None
        if matched_files and all(
            cp.lower().endswith(".ser")
            for _, files in matched_files
            for cp in files
        ):
            # Some archives contain INCEpTION metadata/serialized CAS plus an
            # additional flat XMI/JSON export. Do not report "only .ser" until
            # the fallback scan has also been considered.
            flat_non_ser_files = _prefer_non_ser_files(flat_files)
            if flat_non_ser_files:
                matched_files = flat_non_ser_files
                fallback_flat_layout = True
        elif not matched_files:
            matched_files = _prefer_non_ser_files(flat_files)
            fallback_flat_layout = True

        seen_paths = set()
        for _, fi in matched_files:
            for cp in fi:
                if cp in seen_paths:
                    continue
                seen_paths.add(cp)
                found_any = True
                annotator_names.add(_annotator_name_from_cas_path(cp, fallback_flat_layout=fallback_flat_layout))
                if not cp.lower().endswith(".ser"):
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
            typesystem = _load_typesystem_from_zip(zip_file)
            typesystem_by_parent = {}

            # ---- Process each document ----
            logging.info(f" Started processing project {file_name}")
            if annotator_filter is not None:
                logging.info(
                    f" Processing only following annotators: {annotator_filter}"
                )
            matching_document_files = list(
                _yield_matching_files(
                    project_documents,
                    zip_file,
                    file_name,
                    allowed_extensions=allowed_extensions,
                )
            )
            fallback_flat_layout = project_documents is None
            if matching_document_files and all(
                cas_path.lower().endswith(".ser")
                for _, matching_files in matching_document_files
                for cas_path in matching_files
            ):
                flat_document_files = list(
                    _yield_flat_archive_files(
                        zip_file,
                        allowed_extensions=allowed_extensions,
                    )
                )
                flat_document_files = _prefer_non_ser_files(flat_document_files)
                if flat_document_files:
                    matching_document_files = flat_document_files
                    fallback_flat_layout = True
            elif not matching_document_files:
                matching_document_files = _prefer_non_ser_files(
                    list(
                        _yield_flat_archive_files(
                            zip_file,
                            allowed_extensions=allowed_extensions,
                        )
                    )
                )
                fallback_flat_layout = True

            for doc_name, matching_files in matching_document_files:
                seen_doc_paths = set()
                matching_files = [
                    cas_path
                    for cas_path in matching_files
                    if not (cas_path in seen_doc_paths or seen_doc_paths.add(cas_path))
                ]
                non_ser_files = [cas_path for cas_path in matching_files if not cas_path.lower().endswith(".ser")]
                if non_ser_files:
                    matching_files = non_ser_files
                # ---- Load each CAS, compute stats, discard CAS ----
                for cas_path in matching_files:
                    annotator_name = _annotator_name_from_cas_path(cas_path, fallback_flat_layout=fallback_flat_layout)
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

                        parent = str(pathlib.PurePosixPath(cas_path).parent)
                        cas_typesystem = typesystem_by_parent.get(parent)
                        if cas_typesystem is None:
                            cas_typesystem = _load_typesystem_from_zip(zip_file, cas_path) or typesystem
                            typesystem_by_parent[parent] = cas_typesystem
                        cas = _load_cas_from_zip_member(zip_file, cas_path, typesystem=cas_typesystem)
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
    progress_obj: Optional[dict] = None,
    filter_nan_values: bool = True,
    critical_findings: Optional[list[CriticalFinding]] = None,
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
            doc_error_count = 0
            concept_error_count = 0
            skipped_doc_count = 0
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
                            if critical_findings is not None:
                                critical_findings.extend(
                                    collect_critical_findings(
                                        annotator_name,
                                        doc_name,
                                        annotations,
                                        actionable_codes_array,
                                        filter_type,
                                        _map_dict,
                                        ignored=False,
                                    )
                                )

                        if np.any(ignored_codes_array):
                            if critical_findings is not None:
                                critical_findings.extend(
                                    collect_critical_findings(
                                        annotator_name,
                                        doc_name,
                                        annotations,
                                        ignored_codes_array,
                                        filter_type,
                                        _map_dict,
                                        ignored=True,
                                    )
                                )
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


def _decode_optional_code(value) -> Optional[str]:
    if isinstance(value, (bytes, bytearray)):
        decoded = value.decode("utf-8")
    else:
        decoded = str(value)
    return None if decoded.lower() in {"", "nan", "none", "null"} else decoded


def _offset_tuple(value) -> tuple[int, int]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return (int(value[0]), int(value[1]))


def collect_critical_findings(
    annotator_name: str,
    document_name: str,
    document_dump: DocumentAnnotations,
    bool_index_array: np.ndarray,
    filter_type: ListDumpType,
    mapping_dict: Optional[dict] = None,
    ignored: bool = False,
) -> list[CriticalFinding]:
    """Materialize structured critical findings for a document/mask.

    This is intentionally side-effect free. The current Markdown/JSON writers
    still render from ``DocumentAnnotations`` directly, but this model is the
    bridge for the upcoming sanitization resolver.
    """
    mapping_dict = mapping_dict or {}
    findings: list[CriticalFinding] = []
    reason = "not_in_whitelist" if filter_type == ListDumpType.WHITELIST else "blacklisted"
    for idx in np.where(bool_index_array)[0]:
        raw_code = document_dump.snomed_codes[idx]
        code = _decode_optional_code(raw_code)
        fsn_value = None
        if filter_type == ListDumpType.BLACKLIST:
            raw_fsn = mapping_dict.get(bytes(raw_code), b"")
            fsn_value = raw_fsn.decode("utf-8") if isinstance(raw_fsn, (bytes, bytearray)) else str(raw_fsn)
            fsn_value = fsn_value or None
        layer = document_dump.layers[idx]
        text = document_dump.text[idx]
        findings.append(
            CriticalFinding(
                annotator=annotator_name,
                document=document_name,
                code=code,
                covered_text=text.decode("utf-8") if isinstance(text, (bytes, bytearray)) else str(text),
                offset=_offset_tuple(document_dump.offsets[idx]),
                list_type=filter_type.name.lower(),
                reason=reason,
                layer=layer.decode("utf-8") if isinstance(layer, (bytes, bytearray)) else str(layer),
                fsn=fsn_value,
                ignored=ignored,
                ignore_overlaps=tuple(document_dump.ignore_overlaps[idx]) if idx < len(document_dump.ignore_overlaps) else (),
            )
        )
    return findings


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


def _format_overlap_layers(overlaps: list[IgnoreOverlap]) -> str:
    if not overlaps:
        return ""
    return ", ".join(sorted({overlap.layer for overlap in overlaps}))


def _markdown_cell(value) -> str:
    return (
        str(value)
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("|", "\\|")
    )


def _finding_tag(finding: CriticalFinding) -> str:
    if not finding.fsn:
        return ""
    match = re.search(r"\(([^()]*)\)\s*$", finding.fsn)
    return match.group(1) if match else ""


def _format_finding_offset(finding: CriticalFinding) -> str:
    return f"({finding.offset[0]}, {finding.offset[1]})"


def _render_finding_sections(
    findings: list[CriticalFinding],
    output_file: TextIOWrapper,
    output_file_masked: TextIOWrapper,
    dump_dictionary: Optional[dict] = None,
):
    annotators = sorted({finding.annotator for finding in findings})
    annotator_names_masked = {
        name: f"annotator-{randomname.get_name(adj=('age', 'character', 'emotions', 'appearance'))}"
        for name in annotators
    }
    documents_masked: dict[str, str] = {}

    def masked_doc(name: str) -> str:
        if name not in documents_masked:
            documents_masked[name] = f"document-{randomname.get_name(adj=('linguistics', 'construction', 'materials', 'geometry', 'algorithms', 'size', 'complexity', 'colors'))}"
        return documents_masked[name]

    def write_policy_section(section_findings: list[CriticalFinding], list_type: str):
        if not section_findings:
            return
        for fi, masked in ((output_file, False), (output_file_masked, True)):
            fi.write(f"# {list_type.capitalize()}\n")
            fi.write(f"[Zum Inhalt](#{Information.log_dump_pretext_caption.lower()})  \n")
            fi.write("Zu den Annotator*innen: ")
            links = []
            for annotator in annotators:
                display = annotator_names_masked[annotator] if masked else annotator
                links.append(f"[{display}](#{display.lower()})")
            fi.write(", ".join(links) + "\n")

            current_annotator = None
            current_document = None
            for finding in section_findings:
                annotator = annotator_names_masked[finding.annotator] if masked else finding.annotator
                document = masked_doc(finding.document) if masked else finding.document
                if annotator != current_annotator:
                    fi.write(f"## {annotator}\n([Zum Sektionsanfang](#{list_type}))\n")
                    current_annotator = annotator
                    current_document = None
                if document != current_document:
                    fi.write(f"#### {document}\n")
                    if list_type == "whitelist":
                        fi.write("| Snomed CT Code | Covered Text | Offset in Document |\n")
                        fi.write("| -------------: | -----------: | -----------------: |\n")
                    else:
                        fi.write("| Snomed CT Code | Covered Text | Offset in Document | FSN |\n")
                        fi.write("| -------------: | -----------: | -----------------: | --: |\n")
                    current_document = document
                code = finding.code or "nan"
                if list_type == "whitelist":
                    fi.write(f"| {_markdown_cell(code)} | {_markdown_cell(finding.covered_text)} | {_format_finding_offset(finding)} |\n")
                else:
                    fi.write(f"| {_markdown_cell(code)} | {_markdown_cell(finding.covered_text)} | {_format_finding_offset(finding)} | {_markdown_cell(finding.fsn or '')} |\n")
            fi.write("\n\n")

    def write_ignored_section(ignored_findings: list[CriticalFinding]):
        if not ignored_findings:
            return
        for fi, masked in ((output_file, False), (output_file_masked, True)):
            fi.write("# Ignored faulty concepts\n")
            fi.write(f"[Zum Inhalt](#{Information.log_dump_pretext_caption.lower()})  \n\n")
            fi.write(
                "These concepts would have been reported as faulty, but were ignored because they overlap with configured ignore layer(s).\n\n"
            )
            for list_type in ("whitelist", "blacklist"):
                section_findings = [f for f in ignored_findings if f.list_type == list_type]
                if not section_findings:
                    continue
                fi.write(f"## {list_type.capitalize()}\n")
                current_annotator = None
                current_document = None
                for finding in section_findings:
                    annotator = annotator_names_masked[finding.annotator] if masked else finding.annotator
                    document = masked_doc(finding.document) if masked else finding.document
                    if annotator != current_annotator:
                        fi.write(f"### {annotator}\n")
                        current_annotator = annotator
                        current_document = None
                    if document != current_document:
                        fi.write(f"#### {document}\n")
                        columns = [
                            "Target Layer",
                            "Snomed CT Code",
                            "Covered Text",
                            "Offset in Document",
                            "Reason",
                            "Overlapping Ignore Layer(s)",
                        ]
                        if list_type == "blacklist":
                            columns.append("FSN")
                        fi.write("| " + " | ".join(columns) + " |\n")
                        fi.write("| " + " | ".join(["--:"] * len(columns)) + " |\n")
                        current_document = document
                    overlap_layers = _format_overlap_layers(list(finding.ignore_overlaps))
                    row = f"| {_markdown_cell(finding.layer or '')} | {_markdown_cell(finding.code or 'nan')} | {_markdown_cell(finding.covered_text)} | {_format_finding_offset(finding)} | {_markdown_cell(finding.reason)} | {_markdown_cell(overlap_layers)}"
                    if list_type == "blacklist":
                        row += f" | {_markdown_cell(finding.fsn or '')}"
                    fi.write(row + " |\n")
            fi.write("\n\n")

    actionable = [finding for finding in findings if not finding.ignored]
    ignored = [finding for finding in findings if finding.ignored]
    write_policy_section([f for f in actionable if f.list_type == "whitelist"], "whitelist")
    write_policy_section([f for f in actionable if f.list_type == "blacklist"], "blacklist")
    write_ignored_section(ignored)

    if dump_dictionary is not None:
        for finding in actionable:
            if finding.code is None:
                continue
            if finding.list_type == "blacklist":
                _populate_dump_dictionary(dump_dictionary, finding.code, finding.offset, finding.fsn or "")
            else:
                _populate_dump_dictionary(dump_dictionary, finding.code, finding.offset)


def _finding_counters(findings: list[CriticalFinding]) -> tuple[Counter, Counter]:
    whitelist_code_counter = Counter(
        finding.code for finding in findings if not finding.ignored and finding.list_type == "whitelist" and finding.code
    )
    blacklist_tag_counter = Counter(
        _finding_tag(finding) for finding in findings if not finding.ignored and finding.list_type == "blacklist"
    )
    return whitelist_code_counter, blacklist_tag_counter


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
    critical_findings: Optional[list[CriticalFinding]] = None,
) -> int:
    err_docs = 0
    log_doc.write(Information.log_dump_pretext)
    log_doc_masked.write(Information.log_dump_pretext)

    collected_findings = critical_findings if critical_findings is not None else []

    with h5py.File(lists, "r") as h5_file:
        if progress_obj is not None:
            progress_increment = 1 / max(
                sum([len(x.documents) for x in result.annotators.values()]) * 2, 1
            )

        ft_iter = [ListDumpType.WHITELIST, ListDumpType.BLACKLIST]
        for i, ft in enumerate(ft_iter):
            print(f"-- {ft.name.capitalize()} --")
            group_name = ft.name.lower()
            policy_data = read_policy_data(h5_file, group_name)
            if policy_data is None:
                continue
            filter_list = policy_data.codes
            fsn_list = policy_data.fsn
            err_docs += analyze_documents(
                project=result,
                filter_array=filter_list,
                mapping_array=fsn_list,
                filter_type=ft,
                log_doc=log_doc,
                log_doc_masked=log_doc_masked,
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
                critical_findings=collected_findings,
            )
        _render_finding_sections(collected_findings, log_doc, log_doc_masked, dump_dict)
        whitelist_code_counter, blacklist_tag_counter = _finding_counters(collected_findings)
        log_final_tag_count(
            whitelist_code_counter, blacklist_tag_counter, log_doc, log_doc_masked
        )
    return err_docs
