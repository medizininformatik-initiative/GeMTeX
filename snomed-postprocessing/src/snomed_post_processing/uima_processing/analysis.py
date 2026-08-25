"""Policy analysis over extracted document annotations."""

from __future__ import annotations

import logging
from io import TextIOWrapper
from typing import Optional

import numpy as np
import randomname
import yaspin

from ..snomed import Information, ListDumpType
from ..utils.text import is_numeric
from .models import CriticalFinding, DocumentAnnotations, TemporaryCorpus


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
                                continue

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
    """Materialize structured critical findings for a document/mask."""
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
