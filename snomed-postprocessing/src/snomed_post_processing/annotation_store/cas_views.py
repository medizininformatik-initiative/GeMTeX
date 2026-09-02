"""Iterate CAS views in INCEpTION export ZIPs with provenance."""

from __future__ import annotations

import gc
import logging
import pathlib
import zipfile
from collections.abc import Callable, Iterator
from typing import Optional

from ..uima_processing.io import (
    _annotator_name_from_cas_path,
    _load_cas_from_zip_member,
    _load_typesystem_from_zip,
    _prefer_non_ser_files,
    _read_project,
    _yield_flat_archive_files,
    _yield_matching_files,
)
from .filename import normalize_document_name, parse_export_filename, view_kind_from_cas_path
from .models import CasView

FailureCallback = Callable[[dict], None]


def iter_cas_views(
    export_path: pathlib.Path,
    *,
    site_override: Optional[str] = None,
    allowed_extensions: Optional[list[str]] = None,
    fail_fast: bool = False,
    on_failure: Optional[FailureCallback] = None,
) -> Iterator[CasView]:
    """Yield loadable non-`.ser` CAS views from an INCEpTION export ZIP."""
    export_path = pathlib.Path(export_path)
    export_meta = parse_export_filename(export_path, site_override=site_override)
    file_name = export_path.name

    try:
        with zipfile.ZipFile(export_path, "r") as zip_file:
            project_documents = _read_project(zip_file, file_name)
            typesystem = _load_typesystem_from_zip(zip_file)
            typesystem_by_parent = {}

            matching_document_files = list(
                _yield_matching_files(
                    project_documents,
                    zip_file,
                    file_name,
                    allowed_extensions=allowed_extensions,
                )
            )
            fallback_flat_layout = project_documents is None
            if project_documents is None:
                matching_document_files = _prefer_non_ser_files(
                    list(
                        _yield_flat_archive_files(
                            zip_file,
                            allowed_extensions=allowed_extensions,
                        )
                    )
                )

            for raw_doc_name, matching_files in matching_document_files:
                seen_doc_paths = set()
                matching_files = [
                    cas_path
                    for cas_path in matching_files
                    if not (cas_path in seen_doc_paths or seen_doc_paths.add(cas_path))
                ]
                non_ser_files = [
                    cas_path for cas_path in matching_files if not cas_path.lower().endswith(".ser")
                ]
                if non_ser_files:
                    matching_files = non_ser_files

                document_name = normalize_document_name(raw_doc_name)
                for cas_path in matching_files:
                    if cas_path.lower().endswith(".ser"):
                        _record_failure(
                            on_failure,
                            export_path,
                            cas_path,
                            ValueError("Unsupported .ser CAS member"),
                        )
                        logging.warning(
                            "Skipping %s from %s: UIMA Java Serialized CAS (.ser) is not supported.",
                            cas_path,
                            file_name,
                        )
                        continue

                    try:
                        parent = str(pathlib.PurePosixPath(cas_path).parent)
                        cas_typesystem = typesystem_by_parent.get(parent)
                        if cas_typesystem is None:
                            cas_typesystem = _load_typesystem_from_zip(zip_file, cas_path) or typesystem
                            typesystem_by_parent[parent] = cas_typesystem
                        cas = _load_cas_from_zip_member(zip_file, cas_path, typesystem=cas_typesystem)
                        annotator = _annotator_name_from_cas_path(
                            cas_path,
                            fallback_flat_layout=fallback_flat_layout,
                        )
                        yield CasView(
                            site=export_meta.site,
                            export_path=export_path,
                            export_filename=file_name,
                            batch_index=export_meta.batch_index,
                            batch_total=export_meta.batch_total,
                            batch_label=export_meta.batch_label,
                            document_name=document_name,
                            view_kind=view_kind_from_cas_path(
                                cas_path,
                                fallback_flat_layout=fallback_flat_layout,
                            ),
                            annotator=annotator,
                            cas_path=cas_path,
                            cas=cas,
                        )
                        del cas
                    except Exception as exc:
                        _record_failure(on_failure, export_path, cas_path, exc)
                        logging.warning("Failed to load %s from %s: %s", cas_path, file_name, exc)
                        if fail_fast:
                            raise
            gc.collect()
    except Exception as exc:
        if fail_fast:
            raise
        _record_failure(on_failure, export_path, None, exc)
        logging.error("Error processing %s: %s", file_name, exc)


def _record_failure(
    on_failure: Optional[FailureCallback],
    export_path: pathlib.Path,
    cas_path: Optional[str],
    error,
) -> None:
    if on_failure is None:
        return
    on_failure(
        {
            "export": str(export_path),
            "cas_path": cas_path,
            "error": str(error),
            "error_type": type(error).__name__,
        }
    )
