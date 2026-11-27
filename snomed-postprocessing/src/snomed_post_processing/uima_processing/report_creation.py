"""Markdown/JSON report creation from processed UIMA corpus results."""

from __future__ import annotations

import pathlib
from io import TextIOWrapper
from typing import Optional

import h5py

from ..hdf5_handling.policy import read_policy_data
from ..snomed import Information, ListDumpType
from ..terminology import policy_label
from .analysis import analyze_documents
from .markdown_report import finding_counters, log_final_tag_count, render_finding_sections
from .models import CriticalFinding, TemporaryCorpus


def create_log_from_results(
    result: TemporaryCorpus,
    log_doc: TextIOWrapper,
    log_doc_masked: TextIOWrapper,
    lists: pathlib.Path,
    progress_obj: Optional[dict] = None,
    dump_dict: Optional[dict] = None,
    critical_findings: Optional[list[CriticalFinding]] = None,
) -> int:
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
            print(f"-- {policy_label(ft.name.lower()).capitalize()} --")
            group_name = ft.name.lower()
            policy_data = read_policy_data(h5_file, group_name)
            if policy_data is None:
                continue
            filter_list = policy_data.codes
            fsn_list = policy_data.fsn
            analyze_documents(
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
                        "text_pre": f"__{policy_label(group_name).capitalize()}__: ",
                        "progress_increment": progress_increment,
                        "current_progress": 1.0 * (i / len(ft_iter)),
                    }
                ),
                critical_findings=collected_findings,
            )
        _finish_reports(collected_findings, log_doc, log_doc_masked, dump_dict)
    return _unique_actionable_document_count(collected_findings)


def create_log_from_annotation_store(
    store: pathlib.Path,
    log_doc: TextIOWrapper,
    log_doc_masked: TextIOWrapper,
    lists: pathlib.Path,
    *,
    annotator_filter=None,
    annotation_types=None,
    ignore_overlap_types=None,
    ignore_overlap_mode="overlap",
    store_scope=None,
    progress_obj: Optional[dict] = None,
    dump_dict: Optional[dict] = None,
    critical_findings: Optional[list[CriticalFinding]] = None,
    batch_size: int = 16,
) -> int:
    """Analyze bounded SQLite batches without materializing the complete corpus."""
    from ..annotation_source import annotation_store_document_count, iter_annotation_store_batches

    log_doc.write(Information.log_dump_pretext)
    log_doc_masked.write(Information.log_dump_pretext)
    collected_findings = critical_findings if critical_findings is not None else []
    document_count = annotation_store_document_count(
        store, store_scope=store_scope, annotator_filter=annotator_filter
    )
    progress_increment = 1 / max(document_count * 2, 1)

    with h5py.File(lists, "r") as h5_file:
        for pass_index, filter_type in enumerate((ListDumpType.WHITELIST, ListDumpType.BLACKLIST)):
            print(f"-- {policy_label(filter_type.name.lower()).capitalize()} --")
            group_name = filter_type.name.lower()
            policy_data = read_policy_data(h5_file, group_name)
            if policy_data is None:
                continue
            processed = 0
            for batch in iter_annotation_store_batches(
                store,
                store_scope=store_scope,
                annotator_filter=annotator_filter,
                annotation_types=annotation_types,
                ignore_overlap_types=ignore_overlap_types,
                ignore_overlap_mode=ignore_overlap_mode,
                batch_size=batch_size,
            ):
                analyze_documents(
                    project=batch,
                    filter_array=policy_data.codes,
                    mapping_array=policy_data.fsn,
                    filter_type=filter_type,
                    log_doc=log_doc,
                    log_doc_masked=log_doc_masked,
                    progress_obj=(
                        None
                        if progress_obj is None
                        else {
                            "obj": progress_obj["obj"],
                            "text_pre": f"__{policy_label(group_name).capitalize()}__: ",
                            "progress_increment": progress_increment,
                            "current_progress": pass_index / 2 + processed * progress_increment,
                        }
                    ),
                    critical_findings=collected_findings,
                )
                processed += sum(len(container.documents) for container in batch.annotators.values())
        _finish_reports(collected_findings, log_doc, log_doc_masked, dump_dict)
    return _unique_actionable_document_count(collected_findings)


def _finish_reports(findings, log_doc, log_doc_masked, dump_dict):
    render_finding_sections(findings, log_doc, log_doc_masked, dump_dict)
    whitelist_code_counter, blacklist_tag_counter = finding_counters(findings)
    log_final_tag_count(whitelist_code_counter, blacklist_tag_counter, log_doc, log_doc_masked)


def _unique_actionable_document_count(findings: list[CriticalFinding]) -> int:
    return len(
        {
            (finding.annotator, finding.document)
            for finding in findings
            if not finding.ignored
        }
    )
