"""Build bare-bones INCEpTION project ZIPs for sanitized deployments."""

from __future__ import annotations

import dataclasses
import json
import pathlib
import zipfile
from typing import Any

from .sanitization_run import (
    _append_sanitized_description,
    _append_sanitized_name,
    _append_sanitized_slug,
    _ensure_manual_review_layer_in_project,
)


DEFAULT_MANUAL_REVIEW_LAYER = "webanno.custom.ManualReview"
MIN_PROJECT_SLUG_LENGTH = 3
MAX_PROJECT_SLUG_LENGTH = 40


@dataclasses.dataclass(frozen=True)
class InceptionShellProjectResult:
    """Summary of a generated INCEpTION shell project ZIP."""

    output_project: pathlib.Path
    project_name: str
    project_slug: str
    layer_count: int
    source_document_count: int
    annotation_document_count: int
    omitted_member_count: int


class InceptionShellProjectError(RuntimeError):
    """Raised when a project shell ZIP cannot be generated."""


def build_inception_shell_project(
    source_project: pathlib.Path,
    output_project: pathlib.Path,
    *,
    project_name: str | None = None,
    project_slug: str | None = None,
    project_description: str | None = None,
    sanitized_project_suffix: str = "sanitized",
    manual_review_layer: str = DEFAULT_MANUAL_REVIEW_LAYER,
    clear_source_documents: bool = True,
    clear_annotation_documents: bool = True,
    include_source_files: bool = False,
    force: bool = False,
) -> InceptionShellProjectResult:
    """Create a bare-bones INCEpTION project ZIP carrying schema/layers.

    The shell ZIP is intended to initialize a new sanitized project. It preserves
    project schema from ``exportedproject.json`` and ensures the manual-review
    layer exists, while dropping annotation/curation CAS contents. Sanitized CAS
    contents should be uploaded later through INCEpTION's remote API.
    """

    source_project = pathlib.Path(source_project)
    output_project = pathlib.Path(output_project)
    if not source_project.exists() or not source_project.is_file():
        raise FileNotFoundError(f"Source project does not exist: {source_project}")
    if source_project.resolve() == output_project.resolve():
        raise InceptionShellProjectError("Output project must be different from source project.")
    if output_project.exists() and not force:
        raise FileExistsError(f"Output project already exists: {output_project}")

    manual_review_layer = str(manual_review_layer or "").strip() or DEFAULT_MANUAL_REVIEW_LAYER
    sanitized_project_suffix = str(sanitized_project_suffix or "").strip() or "sanitized"

    output_project.parent.mkdir(parents=True, exist_ok=True)
    omitted_member_count = 0
    with zipfile.ZipFile(source_project, "r") as in_zip:
        try:
            project = json.loads(in_zip.read("exportedproject.json").decode("utf-8"))
        except KeyError as exc:
            raise InceptionShellProjectError("Source ZIP does not contain exportedproject.json") from exc
        except Exception as exc:
            raise InceptionShellProjectError("Could not parse exportedproject.json") from exc

        _prepare_shell_project_json(
            project,
            project_name=project_name,
            project_slug=project_slug,
            project_description=project_description,
            sanitized_project_suffix=sanitized_project_suffix,
            manual_review_layer=manual_review_layer,
            clear_source_documents=clear_source_documents,
            clear_annotation_documents=clear_annotation_documents,
        )

        with zipfile.ZipFile(output_project, "w", compression=zipfile.ZIP_DEFLATED) as out_zip:
            out_zip.writestr(
                "exportedproject.json",
                json.dumps(project, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            for info in in_zip.infolist():
                name = _normalize_zip_member_name(info.filename)
                if name == "exportedproject.json" or info.is_dir():
                    continue
                if _is_annotation_or_curation_content(name):
                    omitted_member_count += 1
                    continue
                if _is_source_content(name):
                    if include_source_files:
                        out_zip.writestr(_copy_zip_info(info), in_zip.read(info.filename))
                    else:
                        omitted_member_count += 1
                    continue
                if _should_copy_support_member(name):
                    out_zip.writestr(_copy_zip_info(info), in_zip.read(info.filename))
                else:
                    omitted_member_count += 1

    return InceptionShellProjectResult(
        output_project=output_project,
        project_name=str(project.get("name", "")),
        project_slug=str(project.get("slug", "")),
        layer_count=len(project.get("layers") or []),
        source_document_count=len(project.get("source_documents") or []),
        annotation_document_count=len(project.get("annotation_documents") or []),
        omitted_member_count=omitted_member_count,
    )


def _prepare_shell_project_json(
    project: dict[str, Any],
    *,
    project_name: str | None,
    project_slug: str | None,
    project_description: str | None,
    sanitized_project_suffix: str,
    manual_review_layer: str,
    clear_source_documents: bool,
    clear_annotation_documents: bool,
) -> None:
    if project_name:
        project["name"] = project_name
    else:
        project["name"] = _append_sanitized_name(project.get("name"), sanitized_project_suffix)

    if project_slug:
        _validate_project_slug(project_slug)
        project["slug"] = project_slug
    else:
        project["slug"] = _coerce_project_slug(
            _append_sanitized_slug(project.get("slug"), sanitized_project_suffix)
        )

    if project_description is not None:
        project["description"] = project_description
    else:
        project["description"] = _append_sanitized_description(
            project.get("description"), sanitized_project_suffix
        )

    project.setdefault("layers", [])
    _ensure_manual_review_layer_in_project(project, manual_review_layer)

    if clear_source_documents:
        project["source_documents"] = []
    else:
        project.setdefault("source_documents", [])

    if clear_annotation_documents:
        project["annotation_documents"] = []
    else:
        project.setdefault("annotation_documents", [])

    # Avoid importing stale curation metadata without matching sanitized CAS content.
    for key in ("curated_documents", "curation_documents"):
        if key in project:
            project[key] = []


def _validate_project_slug(slug: str) -> None:
    if not _is_valid_project_slug(slug):
        raise InceptionShellProjectError(
            "Invalid INCEpTION project slug. Slugs must be 3-40 characters, start "
            "with a lowercase letter [a-z], and contain only lowercase letters, "
            "numbers, '-' or '_'."
        )


def _is_valid_project_slug(slug: str) -> bool:
    if not MIN_PROJECT_SLUG_LENGTH <= len(slug) <= MAX_PROJECT_SLUG_LENGTH:
        return False
    if not "a" <= slug[0] <= "z":
        return False
    return all(char.isdigit() or "a" <= char <= "z" or char in "-_" for char in slug)


def _coerce_project_slug(slug: str) -> str:
    text = "".join(
        char if char.isdigit() or "a" <= char <= "z" or char in "-_" else "-"
        for char in str(slug or "").lower()
    ).strip("-_")
    if not text or not ("a" <= text[0] <= "z"):
        text = f"project-{text}".strip("-_")
    text = text[:MAX_PROJECT_SLUG_LENGTH].rstrip("-_")
    if len(text) < MIN_PROJECT_SLUG_LENGTH:
        text = (text + "-project")[:MIN_PROJECT_SLUG_LENGTH]
    if not _is_valid_project_slug(text):
        raise InceptionShellProjectError(f"Could not derive a valid INCEpTION project slug from: {slug!r}")
    return text


def _is_annotation_or_curation_content(name: str) -> bool:
    return any(
        name == prefix or name.startswith(prefix + "/")
        for prefix in ("annotation", "annotation_ser", "curation", "curation_ser")
    )


def _is_source_content(name: str) -> bool:
    return name == "source" or name.startswith("source/")


def _should_copy_support_member(name: str) -> bool:
    """Return whether a non-content ZIP member should be preserved in the shell.

    Keep auxiliary schema/project files such as TypeSystem.xml while dropping
    runtime/export convenience content. The authoritative schema for full project
    import is still exportedproject.json, but retaining TypeSystem.xml is useful
    as a debugging/manual-import artifact.
    """

    lower = name.lower()
    if lower.endswith(".ser"):
        return False
    if lower in {"typesystem.xml", "project.properties"}:
        return True
    if "/typesystem.xml" in lower:
        return True
    return False


def _normalize_zip_member_name(name: str) -> str:
    return name.lstrip("/")


def _copy_zip_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    copied = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    copied.comment = info.comment
    copied.extra = info.extra
    copied.internal_attr = info.internal_attr
    copied.external_attr = info.external_attr
    copied.create_system = info.create_system
    return copied
