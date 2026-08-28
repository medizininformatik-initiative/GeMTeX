"""End-to-end sanitized INCEpTION corpus deployment pipeline."""

from __future__ import annotations

import dataclasses
import datetime
import json
import pathlib
from typing import Optional

from ..sanitization.decisions_json import read_sanitization_decisions_json
from .inception_deployment import InceptionDeploymentResult, deploy_inception_sanitized_project
from .inception_shell_project import InceptionShellProjectResult, build_inception_shell_project
from .inception_upload_artifacts import InceptionUploadArtifactsResult, build_inception_upload_artifacts


DEFAULT_MANUAL_REVIEW_LAYER = "webanno.custom.ManualReview"
DEFAULT_PIPELINE_REPORT_NAME = "inception-apply-decisions-upload-report.json"


@dataclasses.dataclass(frozen=True)
class InceptionApplyUploadResult:
    """Summary of the combined shell/artifacts/deployment workflow."""

    source_project: pathlib.Path
    decisions_path: pathlib.Path
    output_dir: pathlib.Path
    shell_project: pathlib.Path
    upload_artifacts_dir: pathlib.Path
    pipeline_report_path: pathlib.Path
    decision_count: int
    shell_result: InceptionShellProjectResult
    artifacts_result: InceptionUploadArtifactsResult
    deployment_result: InceptionDeploymentResult

    @property
    def applied(self) -> bool:
        return self.deployment_result.applied

    @property
    def dry_run(self) -> bool:
        return self.deployment_result.dry_run


class InceptionApplyUploadError(RuntimeError):
    """Raised when the combined INCEpTION apply/upload pipeline cannot run."""


def apply_decisions_and_upload_to_inception(
    *,
    source_project: pathlib.Path,
    decisions_path: pathlib.Path,
    output_dir: pathlib.Path,
    shell_project: Optional[pathlib.Path] = None,
    upload_artifacts_dir: Optional[pathlib.Path] = None,
    pipeline_report: Optional[pathlib.Path] = None,
    project_name: Optional[str] = None,
    project_slug: Optional[str] = None,
    project_description: Optional[str] = None,
    sanitized_project_suffix: str = "sanitized",
    manual_review_layer: str = DEFAULT_MANUAL_REVIEW_LAYER,
    id_prefix: str = "http://snomed.info/id/",
    repair_for_remote_upload: bool = True,
    inception_url: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    password_env: Optional[str] = None,
    annotation_user: Optional[str] = None,
    apply: bool = False,
    check_connection: bool = False,
    verify_tls: bool = True,
    force: bool = False,
) -> InceptionApplyUploadResult:
    """Apply reviewed decisions to a corpus and prepare/deploy it to INCEpTION.

    The original project ZIP is never modified. The pipeline performs the
    conservative deployment workflow in one call:

    ``original project ZIP + reviewed decisions JSON`` -> schema shell ZIP ->
    repaired flattened CAS upload artifacts -> INCEpTION dry-run or remote apply.

    Remote writes only happen when ``apply=True``. Otherwise the deployment step
    only validates inputs and writes a deployment report.
    """

    source_project = pathlib.Path(source_project)
    decisions_path = pathlib.Path(decisions_path)
    output_dir = pathlib.Path(output_dir)
    if not source_project.exists() or not source_project.is_file():
        raise FileNotFoundError(f"Source project does not exist: {source_project}")
    if not decisions_path.exists() or not decisions_path.is_file():
        raise FileNotFoundError(f"Decisions JSON does not exist: {decisions_path}")
    if output_dir.exists() and any(output_dir.iterdir()) and not force:
        raise FileExistsError(f"Output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    shell_project = pathlib.Path(shell_project or output_dir / _default_shell_name(source_project))
    upload_artifacts_dir = pathlib.Path(upload_artifacts_dir or output_dir / "inception-upload-artifacts")
    pipeline_report_path = pathlib.Path(pipeline_report or output_dir / DEFAULT_PIPELINE_REPORT_NAME)

    decisions, decisions_metadata = read_sanitization_decisions_json(decisions_path)

    shell_result = build_inception_shell_project(
        source_project=source_project,
        output_project=shell_project,
        project_name=project_name,
        project_slug=project_slug,
        project_description=project_description,
        sanitized_project_suffix=sanitized_project_suffix,
        manual_review_layer=manual_review_layer,
        clear_source_documents=True,
        clear_annotation_documents=True,
        include_source_files=False,
        force=force,
    )
    artifacts_result = build_inception_upload_artifacts(
        source_project=source_project,
        decisions=decisions,
        output_dir=upload_artifacts_dir,
        id_prefix=id_prefix,
        manual_review_layer=manual_review_layer,
        force=force,
        repair_for_remote_upload=repair_for_remote_upload,
    )
    deployment_result = deploy_inception_sanitized_project(
        shell_project=shell_result.output_project,
        upload_artifacts_dir=artifacts_result.output_dir,
        deployment_report=output_dir / "inception-sanitized-deployment-report.json",
        inception_url=inception_url,
        username=username,
        password=password,
        password_env=password_env,
        annotation_user=annotation_user,
        apply=apply,
        check_connection=check_connection,
        verify_tls=verify_tls,
    )

    result = InceptionApplyUploadResult(
        source_project=source_project,
        decisions_path=decisions_path,
        output_dir=output_dir,
        shell_project=shell_result.output_project,
        upload_artifacts_dir=artifacts_result.output_dir,
        pipeline_report_path=pipeline_report_path,
        decision_count=len(decisions),
        shell_result=shell_result,
        artifacts_result=artifacts_result,
        deployment_result=deployment_result,
    )
    _write_pipeline_report(result, decisions_metadata=decisions_metadata)
    return result


def _default_shell_name(source_project: pathlib.Path) -> str:
    stem = pathlib.Path(source_project).stem
    return f"{stem}-sanitized-shell.zip"


def _write_pipeline_report(
    result: InceptionApplyUploadResult,
    *,
    decisions_metadata: dict,
) -> None:
    payload = {
        "schema": "snomed-post-processing.inception-apply-decisions-upload",
        "schema_version": 1,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_project": str(result.source_project),
        "decisions_path": str(result.decisions_path),
        "output_dir": str(result.output_dir),
        "shell_project": str(result.shell_project),
        "upload_artifacts_dir": str(result.upload_artifacts_dir),
        "artifact_report": str(result.artifacts_result.report_path),
        "deployment_report": str(result.deployment_result.deployment_report_path),
        "decision_count": result.decision_count,
        "artifact_count": result.artifacts_result.artifact_count,
        "unmatched_decision_count": len(result.artifacts_result.unmatched_decisions),
        "skipped_decision_count": len(result.artifacts_result.skipped_decisions),
        "remote_upload_repaired_artifact_count": sum(
            1 for artifact in result.artifacts_result.artifacts if artifact.remote_upload_repaired
        ),
        "remote_upload_issue_count": sum(
            artifact.remote_upload_issue_count for artifact in result.artifacts_result.artifacts
        ),
        "dry_run": result.dry_run,
        "applied": result.applied,
        "planned_upload_count": result.deployment_result.planned_upload_count,
        "deployment_warning_count": len(result.deployment_result.warnings),
        "deployment_error_count": len(result.deployment_result.errors),
        "imported_project_id": result.deployment_result.imported_project_id,
        "imported_project_name": result.deployment_result.imported_project_name,
        "decisions_metadata": decisions_metadata,
    }
    result.pipeline_report_path.parent.mkdir(parents=True, exist_ok=True)
    result.pipeline_report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
