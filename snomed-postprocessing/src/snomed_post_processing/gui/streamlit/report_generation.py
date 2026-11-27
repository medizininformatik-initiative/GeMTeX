"""Policy-check report generation for the Streamlit GUI."""

from __future__ import annotations

import datetime
import json
import pathlib
import tempfile

from snomed_post_processing.annotation_source import is_annotation_store
from typing import Optional

from snomed_post_processing.findings_io import write_critical_findings_json
from snomed_post_processing.uima_processing import CriticalFinding, create_log_from_results, process_inception_zip
from snomed_post_processing.uima_processing.report_creation import create_log_from_annotation_store


def generate_report(
    project_zip: pathlib.Path,
    lists_path: pathlib.Path,
    anno_filter: Optional[list] = None,
    progress_obj: dict = None,
    annotation_types: Optional[list[str]] = None,
    ignore_overlap_types: Optional[list[str]] = None,
    ignore_overlap_mode: str = "overlap",
    id_prefix: str = "http://snomed.info/id/",
    id_feature: str = "id",
    store_scope: str | None = None,
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path, int, list[CriticalFinding]]:
    json_dump_dictionary = {}
    store_input = is_annotation_store(project_zip)
    output_dir = pathlib.Path(tempfile.mkdtemp(prefix="snomed-policy-report-")) if store_input else project_zip.parent
    output_md = output_dir / (
        f"critical_documents_{datetime.datetime.now().strftime('%d-%m-%Y_%H-%M')}.md"
    )
    output_md_masked = output_md.with_suffix(".masked.md")
    output_json = output_md.with_suffix(".json")
    output_findings_json = output_md.with_name(
        output_md.stem.replace("critical_documents", "critical_findings")
        + ".json"
    )

    critical_findings: list[CriticalFinding] = []
    source_options = dict(
        annotator_filter=anno_filter,
        annotation_types=annotation_types,
        ignore_overlap_types=ignore_overlap_types,
        ignore_overlap_mode=ignore_overlap_mode,
        **({"store_scope": store_scope} if store_scope is not None else {}),
    )
    result = None if store_input else process_inception_zip(
        project_zip, id_prefix=id_prefix, id_feature=id_feature, **source_options,
    )
    if not store_input and result is None:
        raise RuntimeError("Processing failed.")

    with (
        output_md.open("w", encoding="utf-8") as log_doc,
        output_md_masked.open("w", encoding="utf-8") as log_doc_masked,
    ):
        if store_input:
            err_doc_count = create_log_from_annotation_store(
                project_zip,
                log_doc,
                log_doc_masked,
                lists_path,
                progress_obj=progress_obj,
                dump_dict=json_dump_dictionary,
                critical_findings=critical_findings,
                **source_options,
            )
        else:
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
            "annotation_source_file": project_zip.name, "store_scope": store_scope,
            "annotators": sorted(anno_filter or []),
            "lists_path": str(lists_path),
            "annotation_types": annotation_types or [],
            "ignore_overlap_types": ignore_overlap_types or [],
            "ignore_overlap_mode": ignore_overlap_mode,
            "id_prefix": id_prefix,
            "id_feature": id_feature,
        },
    )

    return output_md, output_md_masked, output_json, output_findings_json, err_doc_count, critical_findings
