import pathlib
from io import TextIOWrapper
from typing import Optional

import h5py


from ..snomed import Information, ListDumpType
from ..hdf5_handling.policy import read_policy_data
from .models import (
    CriticalFinding,
    DocumentAnnotations,
    IgnoreOverlap,
    TemporaryContainer,
    TemporaryCorpus,
)
from .extraction import get_annotations_from_document, spans_match
from .analysis import analyze_documents, collect_critical_findings, log_skipped_document
from .markdown_report import finding_counters, log_final_tag_count, render_finding_sections
from .project import get_annotator_names, process_inception_zip



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
        render_finding_sections(collected_findings, log_doc, log_doc_masked, dump_dict)
        whitelist_code_counter, blacklist_tag_counter = finding_counters(collected_findings)
        log_final_tag_count(
            whitelist_code_counter, blacklist_tag_counter, log_doc, log_doc_masked
        )
    return err_docs
