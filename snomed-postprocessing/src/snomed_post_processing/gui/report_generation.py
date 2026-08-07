"""Policy-check report generation for the Streamlit GUI."""

from __future__ import annotations

import datetime
import json
import pathlib
from typing import Optional

from snomed_post_processing.findings_io import write_critical_findings_json
from snomed_post_processing.uima_processing import (
    CriticalFinding,
    create_log_from_results,
    process_inception_zip,
)


def generate_report(
    project_zip: pathlib.Path,
    lists_path: pathlib.Path,
    anno_filter: Optional[list] = None,
    progress_obj: dict = None,
    annotation_types: Optional[list[str]] = None,
    ignore_overlap_types: Optional[list[str]] = None,
    ignore_overlap_mode: str = "overlap",
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path, int, list[CriticalFinding]]:
    json_dump_dictionary = {}
    output_md = project_zip.parent / (
        f"critical_documents_{datetime.datetime.now().strftime('%d-%m-%Y_%H-%M')}.md"
    )
    output_md_masked = output_md.with_suffix(".masked.md")
    output_json = output_md.with_suffix(".json")
    output_findings_json = output_md.with_name(
        output_md.stem.replace("critical_documents", "critical_findings")
        + ".json"
    )

    critical_findings: list[CriticalFinding] = []
    result = process_inception_zip(
        project_zip,
        annotator_filter=anno_filter,
        annotation_types=annotation_types,
        ignore_overlap_types=ignore_overlap_types,
        ignore_overlap_mode=ignore_overlap_mode,
    )
    if result is None:
        raise RuntimeError("Processing failed.")

    with (
        output_md.open("w", encoding="utf-8") as log_doc,
        output_md_masked.open("w", encoding="utf-8") as log_doc_masked,
    ):
        err_doc_count = create_log_from_results(
            result,
            log_doc,
            log_doc_masked,
            lists_path,
            progress_obj,
            json_dump_dictionary,
            critical_findings=critical_findings,
        )
    if progress_obj is not None and progress_obj.get("obj") is not None:
        progress_obj["obj"].empty()

    with output_json.open("w", encoding="utf-8") as json_fi:
        json.dump(json_dump_dictionary, json_fi, indent=2, ensure_ascii=False)

    write_critical_findings_json(
        critical_findings,
        output_findings_json,
        metadata={
            "source": "streamlit-policy-check",
            "lists_path": str(lists_path),
            "annotation_types": annotation_types or [],
            "ignore_overlap_types": ignore_overlap_types or [],
            "ignore_overlap_mode": ignore_overlap_mode,
        },
    )

    return output_md, output_md_masked, output_json, output_findings_json, err_doc_count, critical_findings
