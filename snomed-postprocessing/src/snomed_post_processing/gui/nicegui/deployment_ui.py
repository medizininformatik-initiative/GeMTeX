"""Explicit preparation and remote deployment of a saved NiceGUI review."""
from __future__ import annotations

import copy
import dataclasses
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

from snomed_post_processing.pipelines.inception_apply_upload import (
    InceptionApplyUploadResult,
    apply_decisions_and_upload_to_inception,
)
from snomed_post_processing.pipelines.inception_deployment import (
    InceptionDeploymentResult,
    deploy_inception_sanitized_project,
)
from snomed_post_processing.sanitization.decisions_json import read_sanitization_decisions_json

from .file_sources import FileSource
from .review import ReviewError, ReviewSession
from .shared_inputs import _api_error_message, _inception_projects
from .zip_writeback_ui import _actionable, _source_name


@dataclasses.dataclass(frozen=True)
class PreparedDeployment:
    result: InceptionApplyUploadResult
    artifacts_zip: Path
    sanitized_project_zip: Path | None


def prepare_review_deployment(
    source_project: Path,
    decisions_text: str,
    output_dir: Path,
    *,
    project_name: str | None,
    project_slug: str | None,
    manual_review_layer: str,
    store_scope: str | None,
    project_template: Path | None,
) -> PreparedDeployment:
    """Validate source binding and prepare a frozen, offline deployment package."""
    decisions, metadata = read_sanitization_decisions_json(io.StringIO(decisions_text))
    recorded_source = metadata.get("annotation_source_file")
    if not isinstance(recorded_source, str) or not recorded_source.strip():
        raise ReviewError("Loaded review does not record its annotation source. Regenerate suggestions from the selected source before deployment.")
    if _source_name(recorded_source) != source_project.name:
        raise ReviewError("The selected annotation source does not match the source recorded by this review.")
    if not any(_actionable(item) for item in decisions):
        raise ReviewError("Select and save at least one replacement, deletion, ID removal or manual-review action.")
    sanitized_project_zip = None
    if metadata.get("store_scope") is None:
        from .zip_writeback_ui import build_sanitized_zip
        sanitized_project_zip = output_dir / f"{source_project.stem}-sanitized.zip"
        build_sanitized_zip(
            source_project,
            decisions_text,
            sanitized_project_zip,
            manual_review_layer=manual_review_layer,
        )
    result = apply_decisions_and_upload_to_inception(
        source_project=source_project,
        decisions_path=_write_decisions(output_dir, decisions_text),
        output_dir=output_dir,
        project_name=project_name,
        project_slug=project_slug,
        manual_review_layer=manual_review_layer,
        apply=False,
        force=True,
        store_scope=store_scope,
        project_template=project_template,
    )
    artifacts_zip = output_dir / "inception-upload-artifacts.zip"
    with zipfile.ZipFile(artifacts_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(result.upload_artifacts_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(result.upload_artifacts_dir).as_posix())
    return PreparedDeployment(result, artifacts_zip, sanitized_project_zip)


def upload_prepared_deployment(
    prepared: PreparedDeployment,
    *,
    inception_url: str,
    username: str,
    password: str,
    annotation_user: str | None,
    verify_tls: bool,
) -> InceptionDeploymentResult:
    """Import the prepared shell as a new project and upload its repaired artifacts."""
    return deploy_inception_sanitized_project(
        shell_project=prepared.result.shell_project,
        upload_artifacts_dir=prepared.result.upload_artifacts_dir,
        deployment_report=prepared.result.deployment_result.deployment_report_path,
        inception_url=inception_url,
        username=username,
        password=password,
        annotation_user=annotation_user,
        apply=True,
        verify_tls=verify_tls,
    )


def _write_decisions(output_dir: Path, decisions_text: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "reviewed_sanitization_decisions.json"
    path.write_text(decisions_text, encoding="utf-8")
    return path


class InceptionDeploymentControls:
    def __init__(self, ui, inputs, review):
        self.ui, self.inputs, self.review = ui, inputs, review
        self.busy = self.closed = self.uploading = False
        self.owner: TemporaryDirectory | None = None
        self.prepared: PreparedDeployment | None = None
        self.prepared_token = None
        self.upload_attempted = False
        with ui.expansion("INCEpTION deployment", value=False).classes("w-full") as self.container:
            ui.label(
                "Prepare a schema shell and repaired CAS artifacts from saved choices, then upload them as a new INCEpTION project. The source project/store is never overwritten."
            ).classes("text-sm")
            with ui.row().classes("w-full gap-4 flex-wrap"):
                self.project_name = ui.input("Sanitized project name (optional)", on_change=self.preparation_changed).classes("grow")
                self.project_slug = ui.input("Sanitized project slug (optional)", on_change=self.preparation_changed).classes("grow")
            self.manual_layer = ui.input(
                "Manual-review marker layer", value="webanno.custom.ManualReview", on_change=self.preparation_changed,
            ).classes("w-full")
            self.template = FileSource(
                ui, "Optional project template ZIP", (".zip",), inputs.data_dir, self.preparation_changed,
            )
            self.progress = ui.linear_progress(value=0.0, show_value=False).classes("w-full")
            self.progress_label = ui.label("Save review choices, then prepare deployment artifacts.").classes("text-sm")
            self.prepare_button = ui.button("Prepare deployment artifacts", on_click=self.prepare)
            self.prepare_readiness = ui.label().classes("text-sm whitespace-pre-wrap")
            with ui.row().classes("w-full flex-wrap"):
                self.sanitized_download = ui.button("Download sanitized project ZIP", on_click=self.download_sanitized)
                self.shell_download = ui.button("Download shell project ZIP", on_click=self.download_shell)
                self.artifacts_download = ui.button("Download repaired artifacts ZIP", on_click=self.download_artifacts)
                self.pipeline_report_download = ui.button("Download preparation report JSON", on_click=self.download_pipeline_report)
                self.deployment_report_download = ui.button("Download deployment report JSON", on_click=self.download_deployment_report)
            self.status = ui.label().classes("text-sm whitespace-pre-wrap")
            with ui.expansion("Deployment connection", value=False).classes("w-full"):
                ui.label("This connection is independent of the project-download connection in Inputs.").classes("text-sm")
                self.url = ui.input("INCEpTION URL", value="http://localhost:8080", on_change=self.connection_changed).classes("w-full")
                with ui.row().classes("w-full gap-4 flex-wrap"):
                    self.username = ui.input("REMOTE Role Username", on_change=self.connection_changed).classes("grow")
                    self.password = ui.input(
                        "REMOTE Role Password", password=True, password_toggle_button=True, on_change=self.connection_changed,
                    ).classes("grow")
                self.annotation_user = ui.input(
                    "Annotation user (optional; defaults to username)", on_change=self.connection_changed,
                ).classes("w-full")
                self.disable_tls = ui.checkbox("Disable TLS verification", value=True, on_change=self.connection_changed)
                self.disable_tls.tooltip("Weakens connection security. Prefer a correctly trusted server certificate.")
                self.test_connection_button = ui.button("Test deployment connection", on_click=self.test_connection)
                self.confirm = ui.checkbox(
                    "I understand this imports a new project and uploads annotations", value=False, on_change=self.connection_changed,
                )
                self.upload_button = ui.button("Upload as new INCEpTION project", on_click=self.upload)
                with ui.row().classes("items-center gap-2"):
                    self.upload_spinner = ui.spinner("dots", size="lg")
                    self.upload_activity = ui.label("Importing project and uploading annotations…").classes("text-sm")
                self.connection_status = ui.label().classes("text-sm whitespace-pre-wrap")
        inputs.listeners.append(self.inputs_changed)
        review.deployment = self
        ui.context.client.on_disconnect(self.close)
        self.refresh()

    def _token(self):
        project = self.inputs.project.snapshot()
        template = self.template.snapshot()
        session = self.review.controls.session
        return (
            self.inputs.revision, project, project.stamp() if project is not None else None,
            self.inputs.scope.value if self.inputs.is_store else None,
            template, template.stamp() if template is not None else None,
            self.review.state, session, session.revision,
            (self.project_name.value or "").strip(), (self.project_slug.value or "").strip(),
            (self.manual_layer.value or "").strip(),
        )

    def _release(self):
        owner, self.owner = self.owner, None
        self.prepared = None
        self.prepared_token = None
        self.upload_attempted = False
        if owner is not None:
            owner.cleanup()

    def inputs_changed(self):
        if not self.closed:
            # Never remove frozen files while a connection check/upload worker may
            # still be reading them. Token validation blocks a later upload.
            if not (self.busy and self.prepared is not None):
                self._release()
            self.refresh()

    def review_changed(self):
        if self.closed or self.prepared is None or self.busy:
            return
        try:
            current = self._token()
        except OSError:
            current = None
        if current != self.prepared_token:
            self._release()
        self.refresh()

    def preparation_changed(self, _=None):
        if not (self.busy and self.prepared is not None):
            self._release()
        self.refresh()

    def connection_changed(self, _=None):
        self.connection_status.set_text("")
        self.refresh()

    def refresh(self):
        if self.closed:
            return
        project = self.inputs.project.snapshot()
        session = self.review.controls.session
        template = self.template.snapshot()
        preparation_blockers = []
        if project is None:
            preparation_blockers.append("select the matching annotation source")
        if self.review.state.source_name is None:
            preparation_blockers.append("load suggestions or a rule-only review")
        if session.dirty:
            preparation_blockers.append("save or discard pending review choices")
        if session.invalid_rules:
            preparation_blockers.append("reapply or clear stale concept rules")
        if self.template.uploading:
            preparation_blockers.append("wait for the project-template upload")
        if self.inputs.is_store and self.inputs.scope.value is None:
            preparation_blockers.append("select a SQLite export scope")
        can_prepare = not preparation_blockers and not self.busy
        prepared = self.prepared is not None
        connection_ready = bool((self.url.value or "").strip() and (self.username.value or "").strip() and self.password.value)
        self.template.container.set_visibility(self.inputs.is_store)
        self.prepare_button.set_enabled(can_prepare)
        self.prepare_readiness.set_text(
            "Preparation is currently running."
            if self.busy else "Ready to prepare offline; no INCEpTION connection or credentials are required."
            if not preparation_blockers else "Preparation unavailable: " + "; ".join(preparation_blockers) + "."
        )
        self.sanitized_download.set_visibility(bool(prepared and self.prepared.sanitized_project_zip is not None))
        self.sanitized_download.set_enabled(bool(prepared and self.prepared.sanitized_project_zip is not None and not self.busy))
        for button in (self.shell_download, self.artifacts_download, self.pipeline_report_download, self.deployment_report_download):
            button.set_visibility(prepared)
            button.set_enabled(prepared and not self.busy)
        self.test_connection_button.set_enabled(connection_ready and not self.busy)
        self.upload_button.set_enabled(
            prepared and connection_ready and bool(self.confirm.value) and not self.busy and not self.upload_attempted
        )
        self.upload_spinner.set_visibility(self.uploading)
        self.upload_activity.set_visibility(self.uploading)

    def close(self):
        self.closed = True
        self.template.close()
        self._release()

    async def prepare(self):
        if self.closed or self.busy:
            return
        from nicegui import run

        project = self.inputs.project.snapshot()
        state, session = self.review.state, self.review.controls.session
        input_revision, review_revision = self.inputs.revision, session.revision
        template = self.template.snapshot()
        owner = None
        self._release()
        self.busy = True
        self.progress.set_value(0.1)
        self.progress_label.set_text("Validating saved review and annotation source…")
        self.status.set_text("")
        self.refresh()
        try:
            if project is None:
                raise ReviewError("Select the annotation source used to generate this review.")
            if session.dirty:
                raise ReviewError("Save choices or discard pending changes before deployment preparation.")
            if self.review.controls.before_export is not None:
                await self.review.controls.before_export()
            source_stamp = project.stamp()
            template_stamp = template.stamp() if template is not None else None
            snapshot = ReviewSession(
                state, saved=copy.deepcopy(session.saved), rules=copy.deepcopy(session.rules),
                reviewed_documents=set(session.reviewed_documents),
                imported_metadata=copy.deepcopy(session.imported_metadata), rules_stale=session.rules_stale,
            )
            decisions_text = await run.io_bound(snapshot.export_text)

            def current():
                return (
                    not self.closed and not self.inputs.closed and self.inputs.revision == input_revision
                    and self.review.state is state and self.review.controls.session is session
                    and session.revision == review_revision and self.inputs.project.snapshot() == project
                    and project.stamp() == source_stamp and self.template.snapshot() == template
                    and (template is None or template.stamp() == template_stamp)
                )

            if not current():
                raise ReviewError("Inputs or review changed during validation. Save choices and try again.")
            owner = TemporaryDirectory(prefix="snomed-nicegui-inception-deployment-")
            output_dir = Path(owner.name) / "deployment"
            self.progress.set_value(0.35)
            self.progress_label.set_text("Building schema shell and repaired upload artifacts…")
            prepared = await run.cpu_bound(
                prepare_review_deployment,
                project.path,
                decisions_text,
                output_dir,
                project_name=(self.project_name.value or "").strip() or None,
                project_slug=(self.project_slug.value or "").strip() or None,
                manual_review_layer=(self.manual_layer.value or "").strip() or "webanno.custom.ManualReview",
                store_scope=self.inputs.scope.value if self.inputs.is_store else None,
                project_template=template.path if template is not None else None,
            )
            if not current():
                raise ReviewError("Inputs or review changed during preparation. The stale package was discarded.")
            self.owner, self.prepared = owner, prepared
            owner = None
            self.prepared_token = self._token()
            self.progress.set_value(1.0)
            self.progress_label.set_text("Deployment artifacts are prepared and frozen for upload.")
            result = prepared.result
            self.status.set_text(
                f"Prepared {result.deployment_result.planned_upload_count} upload artifact(s); "
                f"{len(result.artifacts_result.unmatched_decisions)} unmatched and "
                f"{len(result.artifacts_result.skipped_decisions)} skipped decision(s). No network upload occurred."
            )
        except (ReviewError, ValueError) as error:
            if not self.closed:
                self.status.set_text(str(error))
                self.progress.set_value(0.0)
                self.progress_label.set_text("Deployment preparation did not complete.")
        except Exception:
            if not self.closed:
                self.status.set_text("Could not prepare deployment artifacts. Check the selected source, saved review and optional project template.")
                self.progress.set_value(0.0)
                self.progress_label.set_text("Deployment preparation failed; no network upload occurred.")
        finally:
            if owner is not None:
                owner.cleanup()
            self.busy = False
            self.refresh()

    async def test_connection(self):
        if self.closed or self.busy:
            return
        from nicegui import run

        url, username, password = self._credentials()
        self.busy = True
        self.connection_status.set_text("Testing deployment connection…")
        self.refresh()
        try:
            projects = await run.io_bound(
                _inception_projects, url, username, password, not bool(self.disable_tls.value),
            )
            if not self.closed:
                self.connection_status.set_text(f"Connection succeeded; this account can access {len(projects)} project(s).")
        except Exception as error:
            if not self.closed:
                details = _api_error_message(error, username, password)
                self.connection_status.set_text(f"Could not connect with the deployment credentials. {details}")
        finally:
            self.busy = False
            self.refresh()

    async def upload(self):
        if self.closed or self.busy or self.prepared is None or not self.confirm.value:
            return
        from nicegui import run

        try:
            if self._token() != self.prepared_token:
                raise ReviewError("Prepared artifacts no longer match the current inputs or review. Prepare them again.")
            url, username, password = self._credentials()
        except (OSError, ReviewError) as error:
            self.connection_status.set_text(str(error))
            self.refresh()
            return
        prepared = self.prepared
        self.busy = True
        self.uploading = True
        self.upload_attempted = True
        self.progress.set_value(0.65)
        self.progress_label.set_text("Importing a new project and uploading prepared annotations…")
        self.connection_status.set_text("Remote upload started. Do not retry after a partial failure without checking INCEpTION.")
        self.refresh()
        try:
            result = await run.cpu_bound(
                upload_prepared_deployment,
                prepared,
                inception_url=url,
                username=username,
                password=password,
                annotation_user=(self.annotation_user.value or "").strip() or None,
                verify_tls=not bool(self.disable_tls.value),
            )
            if self.closed:
                return
            if result.applied and not result.errors:
                self.progress.set_value(1.0)
                name = result.imported_project_name or "sanitized project"
                identifier = f" (ID {result.imported_project_id})" if result.imported_project_id is not None else ""
                self.progress_label.set_text("Remote deployment completed.")
                self.connection_status.set_text(
                    f"Uploaded {result.planned_upload_count} artifact(s) into new INCEpTION project {name}{identifier}."
                )
            else:
                self.progress_label.set_text("Remote deployment did not complete successfully.")
                self.connection_status.set_text(
                    f"Deployment reported {len(result.errors)} error(s). Check INCEpTION before preparing or attempting another upload; download the deployment report for diagnostics."
                )
        except Exception:
            if not self.closed:
                self.progress_label.set_text("Remote deployment failed or its outcome is uncertain.")
                self.connection_status.set_text(
                    "The upload failed. Check INCEpTION for a partially imported project before preparing or attempting another upload."
                )
        finally:
            self.uploading = False
            self.busy = False
            self.refresh()

    def _credentials(self):
        url = (self.url.value or "").strip()
        username = (self.username.value or "").strip()
        password = self.password.value or ""
        if not url or not username or not password:
            raise ReviewError("Enter the deployment URL, username and password.")
        return url, username, password

    def download_sanitized(self):
        if self.prepared is not None and self.prepared.sanitized_project_zip is not None:
            path = self.prepared.sanitized_project_zip
            self.ui.download.file(path, filename=path.name)

    def download_shell(self):
        if self.prepared is not None:
            path = self.prepared.result.shell_project
            self.ui.download.file(path, filename=path.name)

    def download_artifacts(self):
        if self.prepared is not None:
            path = self.prepared.artifacts_zip
            self.ui.download.file(path, filename=path.name)

    def download_pipeline_report(self):
        if self.prepared is not None:
            path = self.prepared.result.pipeline_report_path
            self.ui.download.file(path, filename=path.name)

    def download_deployment_report(self):
        if self.prepared is not None:
            path = self.prepared.result.deployment_result.deployment_report_path
            self.ui.download.file(path, filename=path.name)
