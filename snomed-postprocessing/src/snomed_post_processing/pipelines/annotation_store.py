"""Build a SQLite annotation store from INCEpTION export ZIPs."""

from __future__ import annotations

import datetime as _dt
import json
import logging
import pathlib
from collections import defaultdict
from typing import Iterable, Optional, Union, Any

from ..annotation_store import (
    AnnotationStoreSummary,
    SnomedLookup,
    cas_document_text,
    document_text_hash,
    iter_annotation_occurrences,
    iter_cas_views,
    parse_export_filename,
)
from ..annotation_store.sqlite import AnnotationStoreWriter
from ..cli import set_log_level


def run_build_annotation_store(
    input_paths: Iterable[Union[str, pathlib.Path]],
    snomed_hdf5: Union[str, pathlib.Path],
    output: Union[str, pathlib.Path],
    annotation_type: tuple[str, ...],
    id_prefix: str,
    replace: bool,
    append: bool,
    store_document_text: bool,
    site: Optional[str],
    fail_fast: bool,
    report: Optional[Union[str, pathlib.Path]],
    log_level: str,
) -> AnnotationStoreSummary:
    """Run the annotation-store import pipeline."""
    set_log_level(log_level)

    output = pathlib.Path(output)
    snomed_hdf5 = pathlib.Path(snomed_hdf5)
    if replace and append:
        raise ValueError("--replace and --append are mutually exclusive.")
    if output.exists() and not (replace or append):
        raise FileExistsError(f"Output DB already exists: {output}. Use --replace or --append.")
    if replace and output.exists():
        output.unlink()
    output.parent.mkdir(parents=True, exist_ok=True)

    zip_paths = _resolve_zip_inputs(input_paths)
    if not zip_paths:
        raise ValueError("No ZIP files found in input path(s).")
    if site is not None and len(zip_paths) > 1:
        logging.warning("--site applies to all input ZIPs; inferred filename sites are overridden.")

    annotation_types = list(annotation_type) if annotation_type else ["gemtex.Concept"]
    logging.info("Loading SNOMED metadata from %s", snomed_hdf5)
    snomed_lookup = SnomedLookup.from_hdf5(snomed_hdf5)

    summary = AnnotationStoreSummary()
    imported_at = _dt.datetime.now(tz=_dt.timezone.utc).isoformat()
    writer = AnnotationStoreWriter(output)
    try:
        writer.initialize()
        for export_path in zip_paths:
            export_meta = parse_export_filename(export_path, site_override=site)
            logging.info("Processing export %s", export_path)
            export_id = writer.insert_export(export_meta, export_path, imported_at)
            summary.exports_processed += 1

            failures_before = len(summary.failed_cas_members)
            for view in iter_cas_views(
                export_path,
                site_override=site,
                fail_fast=fail_fast,
                on_failure=summary.failed_cas_members.append,
            ):
                document_id = writer.insert_document(view.document_name)
                document_hash_id = None
                document_text_id = None
                text = cas_document_text(view.cas)
                if text is not None:
                    text_hash = document_text_hash(text)
                    document_hash_id = writer.insert_document_hash(
                        document_id,
                        export_id,
                        text_hash,
                        view.cas_path,
                    )
                    if store_document_text:
                        document_text_id = writer.insert_document_text(
                            document_id,
                            export_id,
                            text,
                            text_hash,
                            view.cas_path,
                        )

                view_id = writer.insert_annotation_view(
                    export_id,
                    document_id,
                    document_hash_id,
                    document_text_id,
                    view.view_kind,
                    view.annotator,
                    view.cas_path,
                )
                for occurrence in iter_annotation_occurrences(
                    view,
                    snomed_lookup,
                    annotation_types=annotation_types,
                    id_prefix=id_prefix,
                ):
                    concept = snomed_lookup.get(occurrence.sctid)
                    writer.insert_concept(occurrence.sctid, concept)
                    if occurrence.sctid:
                        if concept:
                            summary.known_sctids += 1
                        else:
                            summary.unknown_sctids.add(occurrence.sctid)
                    if writer.insert_annotation(view_id, occurrence):
                        summary.annotations += 1

            if len(summary.failed_cas_members) > failures_before and fail_fast:
                break
            writer.commit()

        summary.documents = writer.count("documents")
        summary.annotation_views = writer.count("annotation_views")
        summary.annotations = writer.count("annotations")
        summary.known_sctids = int(
            writer.connection.execute(
                "select count(*) as n from annotations where sctid is not null and fsn is not null"
            ).fetchone()["n"]
        )
        summary.unknown_sctids = {
            row["sctid"]
            for row in writer.connection.execute(
                "select distinct sctid from annotations where sctid is not null and fsn is null order by sctid"
            )
        }
        summary.missing_batches = _missing_batches_from_db(writer)
        writer.commit()
    finally:
        writer.close()

    if report is not None:
        _write_report(pathlib.Path(report), summary)

    _log_summary(summary, output)
    return summary


def _resolve_zip_inputs(input_paths: Iterable[Union[str, pathlib.Path]]) -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    for input_path in input_paths:
        path = pathlib.Path(input_path)
        if path.is_dir():
            paths.extend(sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() == ".zip"))
        elif path.is_file() and path.suffix.lower() == ".zip":
            paths.append(path)
        elif path.exists():
            logging.warning("Skipping non-ZIP input: %s", path)
        else:
            raise FileNotFoundError(f"Input path does not exist: {path}")
    return sorted(dict.fromkeys(paths))


def _missing_batches_from_db(writer: AnnotationStoreWriter) -> list[dict]:
    batches_by_site: dict[str, dict[str, Any]] = defaultdict(lambda: {"found": set(), "total": 0})
    for row in writer.connection.execute(
        """
        select site, batch_index, batch_total from exports
        where batch_index is not null and batch_total is not null
        """
    ):
        batches_by_site[row["site"]]["found"].add(int(row["batch_index"]))
        batches_by_site[row["site"]]["total"] = max(
            int(batches_by_site[row["site"]]["total"]),
            int(row["batch_total"]),
        )

    missing = []
    for site, batch_info in sorted(batches_by_site.items()):
        found = set(batch_info["found"])
        total = int(batch_info["total"])
        if total <= 0:
            continue
        missing_indices = [idx for idx in range(1, total + 1) if idx not in found]
        if missing_indices:
            missing.append(
                {
                    "site": site,
                    "found": sorted(found),
                    "total": total,
                    "missing": missing_indices,
                }
            )
    return missing


def _summary_as_dict(summary: AnnotationStoreSummary) -> dict:
    return {
        "exports_processed": summary.exports_processed,
        "documents": summary.documents,
        "annotation_views": summary.annotation_views,
        "annotations": summary.annotations,
        "known_sctids": summary.known_sctids,
        "unknown_sctids": sorted(summary.unknown_sctids),
        "failed_cas_members": summary.failed_cas_members,
        "missing_batches": summary.missing_batches,
    }


def _write_report(path: pathlib.Path, summary: AnnotationStoreSummary) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_summary_as_dict(summary), ensure_ascii=False, indent=2), encoding="utf-8")


def _log_summary(summary: AnnotationStoreSummary, output: pathlib.Path) -> None:
    logging.info("Annotation store written to %s", output.resolve())
    logging.info("Exports processed: %s", summary.exports_processed)
    logging.info("Documents: %s", summary.documents)
    logging.info("Annotation views: %s", summary.annotation_views)
    logging.info("Annotations: %s", summary.annotations)
    logging.info("Known SCTID occurrences: %s", summary.known_sctids)
    logging.info("Unknown SCTIDs: %s", len(summary.unknown_sctids))
    logging.info("Failed CAS members: %s", len(summary.failed_cas_members))
    for item in summary.missing_batches:
        logging.warning(
            "Site %s: found batches %s of expected %s; missing %s.",
            item["site"],
            ",".join(str(v) for v in item["found"]),
            item["total"],
            ",".join(str(v) for v in item["missing"]),
        )
