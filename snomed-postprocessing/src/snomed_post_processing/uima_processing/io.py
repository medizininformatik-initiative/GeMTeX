"""ZIP/CAS IO helpers for UIMA/INCEpTION processing."""

from __future__ import annotations

import io
import json
import logging
import pathlib
import zipfile
from typing import Optional, Union

import cassis


FLAT_ARCHIVE_ANNOTATOR = "flat-archive"


def _load_document(path: Union[str, pathlib.Path]) -> cassis.Cas:
    if isinstance(path, str):
        path = pathlib.Path(path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File '{path}' does not exist.")

    return cassis.load_cas_from_json(path.open("r", encoding="utf-8"))


def _is_ignored_zip_member(info: zipfile.ZipInfo) -> bool:
    path = pathlib.PurePosixPath(info.filename)
    return (
        info.is_dir()
        or info.filename.startswith("__MACOSX/")
        or any(part.startswith("._") for part in path.parts)
        or path.name in {".DS_Store", "TypeSystem.xml", "exportedproject.json"}
    )


def _is_supported_cas_path(path: str, allowed_extensions: Optional[list[str]] = None) -> bool:
    lower_path = path.lower()
    extensions = allowed_extensions or [".json", ".xmi", ".zip", ".ser"]
    return any(lower_path.endswith(ext.lower()) for ext in extensions)


def _load_typesystem_from_zip(zip_file: zipfile.ZipFile, cas_path: Optional[str] = None):
    candidates = []
    if cas_path is not None:
        parent = pathlib.PurePosixPath(cas_path).parent
        candidates.append(str(parent / "TypeSystem.xml"))
    candidates.extend(
        info.filename
        for info in zip_file.infolist()
        if not info.is_dir()
        and not info.filename.startswith("__MACOSX/")
        and pathlib.PurePosixPath(info.filename).name == "TypeSystem.xml"
    )
    for candidate in dict.fromkeys(candidates):
        try:
            with zip_file.open(candidate) as typesystem_file:
                return cassis.load_typesystem(typesystem_file)
        except KeyError:
            continue
    return None


def _load_cas_from_nested_zip(cas_zip_file, outer_path: str, typesystem=None):
    data = cas_zip_file.read()
    with zipfile.ZipFile(io.BytesIO(data)) as nested_zip:
        nested_typesystem = typesystem
        for info in nested_zip.infolist():
            if info.is_dir():
                continue
            if pathlib.PurePosixPath(info.filename).name == "TypeSystem.xml":
                with nested_zip.open(info.filename) as typesystem_file:
                    nested_typesystem = cassis.load_typesystem(typesystem_file)
                break
        cas_members = [
            info.filename
            for info in nested_zip.infolist()
            if not _is_ignored_zip_member(info)
            and _is_supported_cas_path(info.filename, allowed_extensions=[".json", ".xmi"])
        ]
        if not cas_members:
            raise ValueError(f"No JSON CAS or XMI found inside nested CAS ZIP '{outer_path}'.")
        if len(cas_members) > 1:
            non_initial = [
                member
                for member in cas_members
                if not pathlib.PurePosixPath(member).name.startswith("INITIAL_CAS")
            ]
            if non_initial:
                cas_members = non_initial
        cas_member = sorted(cas_members)[0]
        with nested_zip.open(cas_member) as nested_cas_file:
            if cas_member.lower().endswith(".json"):
                return cassis.load_cas_from_json(nested_cas_file, typesystem=nested_typesystem)
            return cassis.load_cas_from_xmi(nested_cas_file, typesystem=nested_typesystem, lenient=True)


def _load_cas_from_zip_member(zip_file: zipfile.ZipFile, cas_path: str, typesystem=None):
    lower_path = cas_path.lower()
    with zip_file.open(cas_path) as cas_file:
        if lower_path.endswith(".json"):
            return cassis.load_cas_from_json(cas_file, typesystem=typesystem)
        if lower_path.endswith(".xmi"):
            return cassis.load_cas_from_xmi(cas_file, typesystem=typesystem, lenient=True)
        if lower_path.endswith(".zip"):
            return _load_cas_from_nested_zip(cas_file, cas_path, typesystem=typesystem)
        raise ValueError(f"Unsupported CAS format for '{cas_path}'.")


def _read_project(zip_file: zipfile.ZipFile, file_name: str) -> Optional[list[dict]]:
    try:
        project_meta = json.loads(zip_file.read("exportedproject.json").decode("utf-8"))
    except KeyError:
        logging.info(f"No exportedproject.json found in {file_name}; trying flat CAS archive layout.")
        return None

    project_documents = project_meta.get("source_documents", [])
    if not project_documents:
        logging.warning(f"No source documents found in project {file_name}")
        return None
    return project_documents


def _strip_cas_suffix(name: str) -> str:
    for suffix in (".xmi", ".json", ".zip", ".ser"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return name


def _doc_name_from_flat_cas_path(cas_path: str) -> str:
    path = pathlib.PurePosixPath(cas_path)
    if path.parent.name.lower().endswith((".xmi", ".json", ".zip", ".ser")):
        return _strip_cas_suffix(path.parent.name)
    return _strip_cas_suffix(path.name)


def _annotator_name_from_cas_path(cas_path: str, fallback_flat_layout: bool = False) -> str:
    path = pathlib.PurePosixPath(cas_path)
    if fallback_flat_layout and not path.parent.name.lower().endswith((".xmi", ".json", ".zip", ".ser")):
        return FLAT_ARCHIVE_ANNOTATOR
    return path.stem


def _yield_flat_archive_files(
    zip_file: zipfile.ZipFile,
    allowed_extensions: Optional[list[str]] = None,
):
    document_files: dict[str, list[str]] = {}
    for info in zip_file.infolist():
        if _is_ignored_zip_member(info):
            continue
        if not _is_supported_cas_path(info.filename, allowed_extensions):
            continue
        doc_name = _doc_name_from_flat_cas_path(info.filename)
        document_files.setdefault(doc_name, []).append(info.filename)

    for doc_name in sorted(document_files):
        yield doc_name, sorted(document_files[doc_name])


def _prefer_non_ser_files(
    document_files: list[tuple[str, list[str]]]
) -> list[tuple[str, list[str]]]:
    has_non_ser = any(
        not cas_path.lower().endswith(".ser")
        for _, files in document_files
        for cas_path in files
    )
    if not has_non_ser:
        return document_files
    return [
        (doc_name, [cas_path for cas_path in files if not cas_path.lower().endswith(".ser")])
        for doc_name, files in document_files
        if any(not cas_path.lower().endswith(".ser") for cas_path in files)
    ]


def _yield_matching_files(
    project_documents: Optional[list[dict]],
    zip_file: zipfile.ZipFile,
    file_name: str = None,
    allowed_extensions: Optional[list[str]] = None,
):
    if project_documents is None:
        yield from _yield_flat_archive_files(zip_file, allowed_extensions=allowed_extensions)
        return

    for doc in project_documents:
        doc_name = doc["name"]

        prefixes = [
            f"curation/{doc_name}/",
            f"annotation/{doc_name}/",
            f"curation_ser/{doc_name}/",
            f"annotation_ser/{doc_name}/",
        ]

        matching_files = [
            info.filename
            for info in zip_file.infolist()
            if not _is_ignored_zip_member(info)
            and any(info.filename.startswith(p) for p in prefixes)
            and _is_supported_cas_path(info.filename, allowed_extensions)
        ]

        if len(matching_files) > 1:
            matching_files = [
                p
                for p in matching_files
                if not any(
                    p.endswith(ext)
                    for ext in (
                        [f"INITIAL_CAS{ext}" for ext in allowed_extensions]
                        if allowed_extensions is not None
                        else [
                            "INITIAL_CAS.json",
                            "INITIAL_CAS.xmi",
                            "INITIAL_CAS.zip",
                            "INITIAL_CAS.ser",
                        ]
                    )
                )
            ]

        if not matching_files:
            logging.debug(
                f"No CAS found for {doc_name} in {file_name} searched in {prefixes}"
            )
            continue
        yield doc_name, matching_files
