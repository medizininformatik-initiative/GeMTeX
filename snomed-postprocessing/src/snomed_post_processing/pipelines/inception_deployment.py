"""Deploy sanitized INCEpTION shell projects and flattened CAS artifacts."""

from __future__ import annotations

import dataclasses
import datetime
import io
import json
import os
import pathlib
from typing import Any, Optional

import cassis


SUPPORTED_UPLOAD_FORMATS = {"jsoncas", "xmi"}
DEFAULT_ARTIFACT_REPORT_NAME = "inception-upload-artifacts-report.json"
DEFAULT_DEPLOYMENT_REPORT_NAME = "inception-sanitized-deployment-report.json"


@dataclasses.dataclass(frozen=True)
class InceptionDeploymentPlanItem:
    source_member: str
    source_document: str
    source_annotator: str
    remote_document_name: str
    artifact_path: pathlib.Path
    cas_format: str
    decision_count: int
    changed_annotation_count: int


@dataclasses.dataclass(frozen=True)
class InceptionDeploymentResult:
    dry_run: bool
    applied: bool
    shell_project: pathlib.Path
    upload_artifacts_dir: pathlib.Path
    artifact_report_path: pathlib.Path
    deployment_report_path: pathlib.Path
    planned_upload_count: int
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    imported_project_id: Optional[int] = None
    imported_project_name: Optional[str] = None


class InceptionDeploymentError(RuntimeError):
    """Raised when sanitized INCEpTION deployment cannot proceed."""


def deploy_inception_sanitized_project(
    *,
    shell_project: pathlib.Path,
    upload_artifacts_dir: pathlib.Path,
    deployment_report: Optional[pathlib.Path] = None,
    inception_url: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    password_env: Optional[str] = None,
    annotation_user: Optional[str] = None,
    apply: bool = False,
    check_connection: bool = False,
    verify_tls: bool = True,
) -> InceptionDeploymentResult:
    """Validate or apply sanitized deployment into INCEpTION.

    By default this is a dry-run: it validates the shell ZIP and flattened
    artifact report/files, writes a deployment plan report, and performs no
    network writes. With ``apply=True`` it imports the shell project and uploads
    each flattened artifact as an annotation on a newly created plain-text source
    document.
    """

    shell_project = pathlib.Path(shell_project)
    upload_artifacts_dir = pathlib.Path(upload_artifacts_dir)
    artifact_report_path = upload_artifacts_dir / DEFAULT_ARTIFACT_REPORT_NAME
    deployment_report_path = pathlib.Path(
        deployment_report or upload_artifacts_dir / DEFAULT_DEPLOYMENT_REPORT_NAME
    )
    warnings: list[str] = []
    errors: list[str] = []

    plan = _validate_deployment_inputs(
        shell_project=shell_project,
        upload_artifacts_dir=upload_artifacts_dir,
        artifact_report_path=artifact_report_path,
        warnings=warnings,
        errors=errors,
    )

    imported_project_id: Optional[int] = None
    imported_project_name: Optional[str] = None
    upload_results: list[dict[str, Any]] = []
    applied = False

    if errors:
        report = _deployment_report_payload(
            dry_run=not apply,
            applied=False,
            shell_project=shell_project,
            upload_artifacts_dir=upload_artifacts_dir,
            artifact_report_path=artifact_report_path,
            plan=plan,
            warnings=warnings,
            errors=errors,
            imported_project_id=None,
            imported_project_name=None,
            upload_results=upload_results,
        )
        _write_report(deployment_report_path, report)
        return InceptionDeploymentResult(
            dry_run=not apply,
            applied=False,
            shell_project=shell_project,
            upload_artifacts_dir=upload_artifacts_dir,
            artifact_report_path=artifact_report_path,
            deployment_report_path=deployment_report_path,
            planned_upload_count=len(plan),
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    if check_connection or apply:
        if not inception_url:
            errors.append("INCEpTION URL is required for --check-connection or --apply.")
        password = _resolve_password(password=password, password_env=password_env)
        if not username:
            errors.append("INCEpTION username is required for --check-connection or --apply.")
        if not password:
            errors.append("INCEpTION password is required for --check-connection or --apply.")
        if not annotation_user:
            annotation_user = username

    if errors:
        report = _deployment_report_payload(
            dry_run=not apply,
            applied=False,
            shell_project=shell_project,
            upload_artifacts_dir=upload_artifacts_dir,
            artifact_report_path=artifact_report_path,
            plan=plan,
            warnings=warnings,
            errors=errors,
            imported_project_id=None,
            imported_project_name=None,
            upload_results=upload_results,
        )
        _write_report(deployment_report_path, report)
        return InceptionDeploymentResult(
            dry_run=not apply,
            applied=False,
            shell_project=shell_project,
            upload_artifacts_dir=upload_artifacts_dir,
            artifact_report_path=artifact_report_path,
            deployment_report_path=deployment_report_path,
            planned_upload_count=len(plan),
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    if check_connection and not apply:
        try:
            client = _pycaprio_client(inception_url, username, password, verify_tls=verify_tls)
            projects = client.api.projects()
            warnings.append(f"Connection check succeeded; accessible projects: {len(projects)}.")
        except Exception as exc:  # pragma: no cover - depends on remote INCEpTION
            errors.append(f"Connection check failed: {exc}")

    if apply and not errors:
        try:
            client = _pycaprio_client(inception_url, username, password, verify_tls=verify_tls)
            with shell_project.open("rb") as shell_file:
                project = client.api.import_project(shell_file)
            imported_project_id = getattr(project, "project_id", None)
            imported_project_name = getattr(project, "project_name", None)
            for item in plan:
                document_text = _extract_sofa_text(item.artifact_path, item.cas_format)
                document_name = _document_name_without_cas_suffix(item.remote_document_name)
                with io.BytesIO(document_text.encode("utf-8")) as source_content:
                    source_content.name = f"{document_name}.txt"
                    document = client.api.create_document(
                        project,
                        document_name,
                        source_content,
                        document_format="text",
                        filename=f"{document_name}.txt",
                    )
                with item.artifact_path.open("rb") as annotation_content:
                    annotation = client.api.create_annotation(
                        project,
                        document,
                        annotation_user,
                        annotation_content,
                        annotation_format=item.cas_format,
                    )
                upload_results.append(
                    {
                        "remote_document_name": item.remote_document_name,
                        "document_name": document_name,
                        "document_id": getattr(document, "document_id", None),
                        "annotation_user": annotation_user,
                        "annotation_state": getattr(annotation, "annotation_state", None),
                        "status": "uploaded",
                    }
                )
            applied = True
        except Exception as exc:  # pragma: no cover - depends on remote INCEpTION
            errors.append(f"Apply failed: {exc}")

    report = _deployment_report_payload(
        dry_run=not apply,
        applied=applied,
        shell_project=shell_project,
        upload_artifacts_dir=upload_artifacts_dir,
        artifact_report_path=artifact_report_path,
        plan=plan,
        warnings=warnings,
        errors=errors,
        imported_project_id=imported_project_id,
        imported_project_name=imported_project_name,
        upload_results=upload_results,
    )
    _write_report(deployment_report_path, report)
    return InceptionDeploymentResult(
        dry_run=not apply,
        applied=applied,
        shell_project=shell_project,
        upload_artifacts_dir=upload_artifacts_dir,
        artifact_report_path=artifact_report_path,
        deployment_report_path=deployment_report_path,
        planned_upload_count=len(plan),
        warnings=tuple(warnings),
        errors=tuple(errors),
        imported_project_id=imported_project_id,
        imported_project_name=imported_project_name,
    )


def _validate_deployment_inputs(
    *,
    shell_project: pathlib.Path,
    upload_artifacts_dir: pathlib.Path,
    artifact_report_path: pathlib.Path,
    warnings: list[str],
    errors: list[str],
) -> list[InceptionDeploymentPlanItem]:
    plan: list[InceptionDeploymentPlanItem] = []
    if not shell_project.exists() or not shell_project.is_file():
        errors.append(f"Shell project ZIP does not exist: {shell_project}")
    elif shell_project.suffix.lower() != ".zip":
        warnings.append(f"Shell project does not have .zip suffix: {shell_project}")
    if not upload_artifacts_dir.exists() or not upload_artifacts_dir.is_dir():
        errors.append(f"Upload artifacts directory does not exist: {upload_artifacts_dir}")
        return plan
    if not artifact_report_path.exists() or not artifact_report_path.is_file():
        errors.append(f"Artifact report does not exist: {artifact_report_path}")
        return plan

    try:
        artifact_report = json.loads(artifact_report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Could not read artifact report: {exc}")
        return plan

    if artifact_report.get("mode") != "flattened-documents":
        errors.append(f"Unsupported artifact report mode: {artifact_report.get('mode')!r}")
    uploads = artifact_report.get("uploads")
    if not isinstance(uploads, list):
        errors.append("Artifact report must contain an uploads list.")
        return plan
    if not uploads:
        warnings.append("Artifact report contains no uploads.")

    seen_remote_names: set[str] = set()
    for idx, upload in enumerate(uploads):
        if not isinstance(upload, dict):
            errors.append(f"Upload #{idx + 1} is not an object.")
            continue
        remote_name = str(upload.get("remote_document_name", "")).strip()
        if not remote_name:
            errors.append(f"Upload #{idx + 1} has no remote_document_name.")
            continue
        if remote_name in seen_remote_names:
            errors.append(f"Duplicate remote document name: {remote_name}")
        seen_remote_names.add(remote_name)
        if "INITIAL_CAS" in remote_name:
            errors.append(f"INITIAL_CAS must not be uploaded: {remote_name}")
        cas_format = str(upload.get("format", "")).strip().lower()
        if cas_format not in SUPPORTED_UPLOAD_FORMATS:
            errors.append(f"Unsupported format for {remote_name}: {cas_format!r}")
        artifact_path = _resolve_artifact_path(upload, upload_artifacts_dir)
        if not artifact_path.exists() or not artifact_path.is_file():
            errors.append(f"Artifact file for {remote_name} does not exist: {artifact_path}")
        plan.append(
            InceptionDeploymentPlanItem(
                source_member=str(upload.get("source_member", "")),
                source_document=str(upload.get("source_document", "")),
                source_annotator=str(upload.get("source_annotator", "")),
                remote_document_name=remote_name,
                artifact_path=artifact_path,
                cas_format=cas_format,
                decision_count=int(upload.get("decision_count", 0) or 0),
                changed_annotation_count=int(upload.get("changed_annotation_count", 0) or 0),
            )
        )
    return plan


def _resolve_artifact_path(upload: dict[str, Any], upload_artifacts_dir: pathlib.Path) -> pathlib.Path:
    output_path = upload.get("output_path")
    if output_path:
        candidate = pathlib.Path(str(output_path))
        if candidate.is_absolute() or candidate.exists():
            return candidate
        nested_candidate = upload_artifacts_dir / candidate
        if nested_candidate.exists():
            return nested_candidate
    return upload_artifacts_dir / str(upload.get("remote_document_name", ""))


def _deployment_report_payload(
    *,
    dry_run: bool,
    applied: bool,
    shell_project: pathlib.Path,
    upload_artifacts_dir: pathlib.Path,
    artifact_report_path: pathlib.Path,
    plan: list[InceptionDeploymentPlanItem],
    warnings: list[str],
    errors: list[str],
    imported_project_id: Optional[int],
    imported_project_name: Optional[str],
    upload_results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": "snomed-post-processing.inception-sanitized-deployment",
        "schema_version": 1,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mode": "flattened-documents",
        "dry_run": dry_run,
        "applied": applied,
        "shell_project": str(shell_project),
        "upload_artifacts_dir": str(upload_artifacts_dir),
        "artifact_report": str(artifact_report_path),
        "imported_project_id": imported_project_id,
        "imported_project_name": imported_project_name,
        "planned_upload_count": len(plan),
        "would_import_shell_project": str(shell_project),
        "would_create_documents": [item.remote_document_name for item in plan],
        "would_upload_annotations": len(plan),
        "uploads": [dataclasses.asdict(item) | {"artifact_path": str(item.artifact_path)} for item in plan],
        "upload_results": upload_results,
        "warnings": list(warnings),
        "errors": list(errors),
    }


def _write_report(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_password(*, password: Optional[str], password_env: Optional[str]) -> Optional[str]:
    if password:
        return password
    if password_env:
        return os.getenv(password_env)
    return None


def _pycaprio_client(inception_url: str, username: str, password: str, *, verify_tls: bool):
    from pycaprio import Pycaprio

    return Pycaprio(inception_host=inception_url, authentication=(username, password), verify=verify_tls)


def _extract_sofa_text(artifact_path: pathlib.Path, cas_format: str) -> str:
    with artifact_path.open("rb") as fi:
        if cas_format == "jsoncas":
            cas = cassis.load_cas_from_json(fi)
        elif cas_format == "xmi":
            cas = cassis.load_cas_from_xmi(fi, lenient=True)
        else:
            raise InceptionDeploymentError(f"Unsupported CAS format: {cas_format}")
    return cas.sofa_string or ""


def _document_name_without_cas_suffix(remote_document_name: str) -> str:
    name = pathlib.PurePosixPath(remote_document_name).name
    for suffix in (".json", ".xmi"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return name
