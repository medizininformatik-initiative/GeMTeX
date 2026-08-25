"""INCEpTION project ZIP processing."""

from __future__ import annotations

import gc
import logging
import pathlib
import zipfile
from typing import Optional, Union

from .extraction import get_annotations_from_document
from .io import (
    _annotator_name_from_cas_path,
    _load_cas_from_zip_member,
    _load_typesystem_from_zip,
    _prefer_non_ser_files,
    _read_project,
    _yield_flat_archive_files,
    _yield_matching_files,
)
from .models import TemporaryContainer, TemporaryCorpus


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

    annotations = TemporaryCorpus(annotators={})
    if isinstance(file_path, pathlib.Path):
        file_name = file_path.name
    else:
        file_name = pathlib.Path(file_path).name

    try:
        with zipfile.ZipFile(file_path, "r") as zip_file:
            project_documents = _read_project(zip_file, file_name)
            typesystem = _load_typesystem_from_zip(zip_file)
            typesystem_by_parent = {}

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
                        del cas

                    except Exception as e:
                        logging.warning(
                            f"Failed to load {cas_path} from {file_name}: {e}"
                        )

        gc.collect()

    except Exception as e:
        logging.error(f"Error processing {file_name}: {e}")
        return None

    return annotations
