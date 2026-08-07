"""Document logging pipeline for INCEpTION/UIMA projects."""

from __future__ import annotations

import datetime
import json
import logging
import pathlib
import sys
from typing import Optional, Union

from ..cli import set_log_level
from ..findings_io import write_critical_findings_json
from ..uima_processing import (
    CriticalFinding,
    create_log_from_results,
    get_annotator_names,
    process_inception_zip,
)
from ..utils import get_project_zip, prompt_for_names


def run_log_documents(
    process_path: str,
    lists_path: Optional[str],
    ip: str,
    port: Union[int, str],
    use_secure_protocol: bool,
    inception_username: Optional[str],
    inception_password: Optional[str],
    inception_project: Optional[str],
    log_level: str,
    keep_export: bool,
    omit_dump: bool,
    forbid_prompt: bool,
    annotation_type: tuple[str, ...],
    ignore_overlap_type: tuple[str, ...],
    ignore_overlap_mode: str,
):
    """Run the critical-document logging pipeline."""
    set_log_level(log_level)

    host = f"http{'s' if use_secure_protocol else ''}://{ip}:{port}"
    use_api = (
        inception_username is not None
        and inception_password is not None
        and inception_project is not None
    )
    try:
        project_zip = get_project_zip(
            process_path,
            host,
            inception_username,
            inception_password,
            inception_project,
            False,
        )
    except Exception as e:
        logging.error(f"Error while getting project zip: '{e}'. Exiting.")
        sys.exit(-1)

    default_lists_path = (
        pathlib.Path(__file__).parents[3] / "data" / "gemtex_snomedct_codes_2024-04-01.hdf5"
    ).resolve()
    if lists_path is not None:
        lists_path_tmp = pathlib.Path(lists_path).resolve()
        if lists_path_tmp.exists() and lists_path_tmp.is_file():
            lists_path = lists_path_tmp
        else:
            logging.warning(
                f"The given list doesn't seem to exist or is not a file in hdf5 format: '{lists_path_tmp}'\nUsing default one."
            )
            lists_path = default_lists_path
    else:
        logging.info("No filter list given, using default one.")
        lists_path = default_lists_path

    if not lists_path.exists():
        logging.error(f"The given list doesn't exist: '{lists_path}'. Exiting.")
        sys.exit(-1)

    names_filter = None
    if not forbid_prompt:
        annotator_names, only_ser = get_annotator_names(project_zip)
        if only_ser:
            logging.error(
                "The project only contains UIMA Java Serialized CAS (.ser) files, which are not supported. Please export as JSON CAS or XMI instead."
            )
            sys.exit(-1)

        _res = prompt_for_names(annotator_names)
        if _res and len(_res) > 0:
            names_filter = [n.lower() for n in _res]
    else:
        # If forbid_prompt is set, we still check if the project is processable
        _, only_ser = get_annotator_names(project_zip)
        if only_ser:
            logging.error(
                "The project only contains UIMA Java Serialized CAS (.ser) files, which are not supported. Please export as JSON CAS or XMI instead."
            )
            sys.exit(-1)

    output_path = (
        project_zip.parent
        / f"critical_documents_{datetime.datetime.today().strftime('%d-%m-%Y_%H-%M')}.md"
    )
    output_path_masked = output_path.with_suffix(".masked.md")

    erroneous_doc_count = 0
    dump_dictionary = None if omit_dump else {}
    critical_findings: list[CriticalFinding] = []
    if result := process_inception_zip(
        project_zip,
        annotator_filter=names_filter,
        annotation_types=list(annotation_type),
        ignore_overlap_types=list(ignore_overlap_type),
        ignore_overlap_mode=ignore_overlap_mode,
    ):
        with (
            output_path.open("w", encoding="utf-8") as log_doc,
            output_path_masked.open("w", encoding="utf-8") as log_doc_masked,
        ):
            erroneous_doc_count = create_log_from_results(
                result,
                log_doc,
                log_doc_masked,
                lists_path,
                None,
                dump_dictionary,
                critical_findings=critical_findings,
            )
        with output_path.with_suffix(".json").open("w") as json_file:
            json.dump(dump_dictionary, json_file, ensure_ascii=False, indent=2)

        critical_findings_output_path = output_path.with_name(
            output_path.stem.replace("critical_documents", "critical_findings")
            + ".json"
        )
        write_critical_findings_json(
            critical_findings,
            critical_findings_output_path,
            metadata={
                "command": "log-critical-documents",
                "lists_path": str(lists_path),
                "annotation_types": list(annotation_type),
                "ignore_overlap_types": list(ignore_overlap_type),
                "ignore_overlap_mode": ignore_overlap_mode,
            },
        )
        logging.info(
            f"Critical findings JSON written to '{critical_findings_output_path.resolve()}'."
        )

    if not keep_export and use_api:
        logging.info(
            f"Removing temporary export of project '{project_zip.name}' from filesystem."
        )
        project_zip.unlink()

    print("-- Result --")
    if erroneous_doc_count > 0:
        logging.warning(
            f"{erroneous_doc_count:>4} critical document(s) found. See '{output_path.resolve()}' for details."
        )
    else:
        logging.info("No critical document(s) found.")
