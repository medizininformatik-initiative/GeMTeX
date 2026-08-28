"""Build local sanitized CAS upload artifacts for INCEpTION deployment."""

from __future__ import annotations

import dataclasses
import json
import pathlib
import re
import zipfile
from typing import Any, Optional

from ..uima_processing.io import (
    _annotator_name_from_cas_path,
    _load_typesystem_from_zip,
    _read_project,
    _yield_flat_archive_files,
    _yield_matching_files,
)
from .sanitization_run import sanitize_cas_bytes


CURATION_USER = "CURATION_USER"


@dataclasses.dataclass(frozen=True)
class InceptionUploadArtifact:
    source_member: str
    source_document: str
    source_annotator: str
    remote_document_name: str
    output_path: pathlib.Path
    cas_format: str
    decision_count: int
    applied_decision_count: int
    changed_annotation_count: int
    unmatched_decisions: tuple[dict[str, Any], ...]
    skipped_decisions: tuple[dict[str, Any], ...]


@dataclasses.dataclass(frozen=True)
class InceptionUploadArtifactsResult:
    output_dir: pathlib.Path
    report_path: pathlib.Path
    artifact_count: int
    artifacts: tuple[InceptionUploadArtifact, ...]
    unmatched_decisions: tuple[dict[str, Any], ...]
    skipped_decisions: tuple[dict[str, Any], ...]


class InceptionUploadArtifactsError(RuntimeError):
    """Raised when upload artifacts cannot be generated."""


def build_inception_upload_artifacts(
    source_project: pathlib.Path,
    decisions: list[dict[str, Any]],
    output_dir: pathlib.Path,
    *,
    id_prefix: str = "http://snomed.info/id/",
    manual_review_layer: str = "webanno.custom.ManualReview",
    force: bool = False,
) -> InceptionUploadArtifactsResult:
    """Create flattened sanitized JSONCAS/XMI files and a deployment report.

    This is an offline preparation step for INCEpTION deployment. It extracts
    real annotator/curation CAS files from an INCEpTION project ZIP, skips
    ``INITIAL_CAS`` and ``.ser`` contents, applies reviewed decisions in memory,
    and writes one uploadable file per original document/annotator CAS.
    """

    source_project = pathlib.Path(source_project)
    output_dir = pathlib.Path(output_dir)
    if not source_project.exists() or not source_project.is_file():
        raise FileNotFoundError(f"Source project does not exist: {source_project}")
    if output_dir.exists() and any(output_dir.iterdir()) and not force:
        raise FileExistsError(f"Output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    artifacts: list[InceptionUploadArtifact] = []
    decisions_with_existing_cas_ids: set[int] = set()
    all_skipped_decisions: list[dict[str, Any]] = []
    used_remote_names: set[str] = set()

    with zipfile.ZipFile(source_project, "r") as zip_file:
        project_documents = _read_project(zip_file, source_project.name)
        fallback_flat_layout = project_documents is None
        matching_document_files = list(
            _yield_matching_files(
                project_documents,
                zip_file,
                source_project.name,
                allowed_extensions=[".json", ".xmi"],
            )
        )
        if not matching_document_files:
            matching_document_files = list(
                _yield_flat_archive_files(zip_file, allowed_extensions=[".json", ".xmi"])
            )
            fallback_flat_layout = True

        typesystem = _load_typesystem_from_zip(zip_file)
        typesystem_by_parent = {}
        for source_document, member_names in matching_document_files:
            for member_name in sorted(dict.fromkeys(member_names)):
                annotator = _annotator_name_from_cas_path(
                    member_name, fallback_flat_layout=fallback_flat_layout
                )
                cas_format = _cas_format_from_member(member_name)
                parent = str(pathlib.PurePosixPath(member_name).parent)
                cas_typesystem = typesystem_by_parent.get(parent)
                if cas_typesystem is None:
                    cas_typesystem = _load_typesystem_from_zip(zip_file, member_name) or typesystem
                    typesystem_by_parent[parent] = cas_typesystem
                member_decisions = [
                    decision
                    for decision in decisions
                    if str(decision.get("document", "")) == str(source_document)
                    and str(decision.get("annotator", "")) == str(annotator)
                ]
                decisions_with_existing_cas_ids.update(id(decision) for decision in member_decisions)
                sanitized = sanitize_cas_bytes(
                    zip_file.read(member_name),
                    member_decisions,
                    cas_format=cas_format,
                    typesystem=cas_typesystem,
                    document=source_document,
                    annotator=annotator,
                    id_prefix=id_prefix,
                    manual_review_layer=manual_review_layer,
                )
                all_skipped_decisions.extend(sanitized.skipped_decisions)

                remote_name = _unique_remote_document_name(
                    source_document,
                    annotator,
                    pathlib.PurePosixPath(member_name).suffix.lower(),
                    used_remote_names,
                )
                output_path = output_dir / remote_name
                output_path.write_bytes(sanitized.cas_bytes)
                artifacts.append(
                    InceptionUploadArtifact(
                        source_member=member_name,
                        source_document=source_document,
                        source_annotator=annotator,
                        remote_document_name=remote_name,
                        output_path=output_path,
                        cas_format=cas_format,
                        decision_count=sanitized.decision_count,
                        applied_decision_count=sanitized.applied_decision_count,
                        changed_annotation_count=sanitized.changed_annotation_count,
                        unmatched_decisions=sanitized.unmatched_decisions,
                        skipped_decisions=sanitized.skipped_decisions,
                    )
                )

    artifact_unmatched = [
        decision
        for artifact in artifacts
        for decision in artifact.unmatched_decisions
    ]
    decisions_targeting_missing_cas = [
        decision for decision in decisions if id(decision) not in decisions_with_existing_cas_ids
    ]
    unmatched_decisions = tuple(_deduplicate_decisions([*artifact_unmatched, *decisions_targeting_missing_cas]))
    skipped_decisions = tuple(_deduplicate_decisions(all_skipped_decisions))
    report_path = output_dir / "inception-upload-artifacts-report.json"
    report = _artifacts_report(
        source_project=source_project,
        output_dir=output_dir,
        artifacts=artifacts,
        unmatched_decisions=unmatched_decisions,
        skipped_decisions=skipped_decisions,
    )
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return InceptionUploadArtifactsResult(
        output_dir=output_dir,
        report_path=report_path,
        artifact_count=len(artifacts),
        artifacts=tuple(artifacts),
        unmatched_decisions=unmatched_decisions,
        skipped_decisions=skipped_decisions,
    )


def _cas_format_from_member(member_name: str) -> str:
    lower = member_name.lower()
    if lower.endswith(".json"):
        return "jsoncas"
    if lower.endswith(".xmi"):
        return "xmi"
    raise InceptionUploadArtifactsError(f"Unsupported CAS member format: {member_name}")


def _unique_remote_document_name(
    source_document: str,
    annotator: str,
    extension: str,
    used_names: set[str],
) -> str:
    base = _remote_document_base(source_document, annotator)
    candidate = f"{base}{extension}"
    counter = 2
    while candidate in used_names:
        candidate = f"{base}-{counter}{extension}"
        counter += 1
    used_names.add(candidate)
    return candidate


def _remote_document_base(source_document: str, annotator: str) -> str:
    doc_base = _safe_name(_document_stem(source_document)) or "document"
    if annotator == CURATION_USER:
        return f"{doc_base}__curation"
    return f"{doc_base}__ann-{_safe_name(annotator) or 'annotator'}"


def _document_stem(source_document: str) -> str:
    name = pathlib.PurePosixPath(str(source_document)).name
    for suffix in (".xmi", ".json", ".zip", ".txt"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
    return name


def _safe_name(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip(".-_")
    return text[:120].strip(".-_")


def _deduplicate_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[int] = set()
    unique: list[dict[str, Any]] = []
    for decision in decisions:
        marker = id(decision)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(decision)
    return unique


def _artifacts_report(
    *,
    source_project: pathlib.Path,
    output_dir: pathlib.Path,
    artifacts: list[InceptionUploadArtifact],
    unmatched_decisions: tuple[dict[str, Any], ...],
    skipped_decisions: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    return {
        "mode": "flattened-documents",
        "source_project": str(source_project),
        "output_dir": str(output_dir),
        "artifact_count": len(artifacts),
        "uploads": [
            {
                "source_member": artifact.source_member,
                "source_document": artifact.source_document,
                "source_annotator": artifact.source_annotator,
                "remote_document_name": artifact.remote_document_name,
                "output_path": str(artifact.output_path),
                "format": artifact.cas_format,
                "decision_count": artifact.decision_count,
                "applied_decision_count": artifact.applied_decision_count,
                "changed_annotation_count": artifact.changed_annotation_count,
                "unmatched_decision_count": len(artifact.unmatched_decisions),
                "skipped_decision_count": len(artifact.skipped_decisions),
            }
            for artifact in artifacts
        ],
        "unmatched_decisions": list(unmatched_decisions),
        "skipped_decisions": list(skipped_decisions),
    }
