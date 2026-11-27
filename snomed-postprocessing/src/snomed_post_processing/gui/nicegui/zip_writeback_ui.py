"""Explicit local ZIP write-back for a saved NiceGUI review."""
from __future__ import annotations

import copy
import io
from pathlib import Path
from tempfile import TemporaryDirectory

from snomed_post_processing.pipelines.sanitization_run import SanitizationRunResult, run_sanitization
from snomed_post_processing.sanitization.decisions_json import read_sanitization_decisions_json
from snomed_post_processing.uima_processing.scope import normalize_annotators

from .file_sources import SourceFile
from .review import ReviewError, ReviewSession


def _source_name(value) -> str:
    return str(value or "").replace("\\", "/").rsplit("/", 1)[-1]


def _actionable(decision: dict) -> bool:
    action = decision.get("action")
    if bool(decision.get("manual_edit")) or action == "manual_edit":
        return True
    if bool(decision.get("delete_annotation")) or action == "delete":
        return True
    if action == "clear_id":
        return bool(decision.get("apply")) and bool(decision.get("valid_choice")) and not decision.get("replacement_code")
    return bool(decision.get("apply")) and bool(decision.get("valid_choice")) and bool(decision.get("replacement_code"))


def build_sanitized_zip(
    source_project: Path,
    decisions_text: str,
    output_project: Path,
    *,
    manual_review_layer: str,
) -> SanitizationRunResult:
    """Validate a review/source binding and apply its actions to a copied ZIP."""
    decisions, metadata = read_sanitization_decisions_json(io.StringIO(decisions_text))
    recorded_source = metadata.get("annotation_source_file")
    if not isinstance(recorded_source, str) or not recorded_source.strip():
        raise ReviewError("Loaded review does not record its annotation source. Regenerate suggestions from the selected project before write-back.")
    if _source_name(recorded_source) != source_project.name:
        raise ReviewError("The selected project ZIP does not match the project recorded by this review.")
    if metadata.get("store_scope") is not None:
        raise ReviewError("This is a SQLite-backed review. Use the preserved-CAS offline package below.")
    if not any(_actionable(item) for item in decisions):
        raise ReviewError("Select and save at least one replacement, deletion, ID removal or manual-review action.")
    annotators = normalize_annotators(metadata.get("annotators", ()))
    return run_sanitization(
        source_project,
        decisions,
        output_project,
        annotator_filter=set(annotators) or None,
        id_prefix=str(metadata.get("id_prefix", "http://snomed.info/id/")),
        id_feature=str(metadata.get("id_feature", "id")),
        manual_review_layer=manual_review_layer,
    )


class ZipWritebackControls:
    def __init__(self, ui, inputs, review):
        self.ui, self.inputs, self.review = ui, inputs, review
        self.busy = self.closed = False
        self.output: SourceFile | None = None
        self.output_token = None
        with ui.expansion("Local ZIP write-back", value=False).classes("w-full") as self.container:
            ui.label(
                "Applies saved review actions to a new project ZIP. The selected source ZIP is read-only; no INCEpTION connection is made."
            ).classes("text-sm")
            self.manual_layer = ui.input(
                "Manual-review marker layer", value="webanno.custom.ManualReview", on_change=self.changed,
            ).classes("w-full")
            self.progress = ui.linear_progress(value=0.0, show_value=False).classes("w-full")
            self.progress_label = ui.label("Save review choices and select their matching project ZIP.").classes("text-sm")
            self.run = ui.button("Run sanitization", on_click=self.prepare)
            self.download = ui.button("Download sanitized project ZIP", on_click=self.download_output)
            self.status = ui.label().classes("text-sm whitespace-pre-wrap")
        inputs.listeners.append(self.inputs_changed)
        review.writeback = self
        ui.context.client.on_disconnect(self.close)
        self.refresh()

    def _token(self):
        project = self.inputs.project.snapshot()
        stamp = project.stamp() if project is not None else None
        session = self.review.controls.session
        return (self.inputs.revision, project, stamp, self.review.state, session, session.revision,
                (self.manual_layer.value or "").strip())

    def _release_output(self):
        output, self.output = self.output, None
        self.output_token = None
        if output is not None and output.owner is not None:
            output.owner.cleanup()

    def inputs_changed(self):
        if not self.closed:
            self._release_output()
            self.refresh()

    def review_changed(self):
        if self.closed:
            return
        if self.output is not None:
            try:
                current = self._token()
            except OSError:
                current = None
            if current != self.output_token:
                self._release_output()
        self.refresh()

    def changed(self, _=None):
        self._release_output()
        self.refresh()

    def refresh(self):
        if self.closed:
            return
        session = self.review.controls.session
        project = self.inputs.project.snapshot()
        eligible = (not self.inputs.is_store and project is not None and self.review.state.source_name is not None
                    and not session.dirty and not session.invalid_rules and not self.busy)
        self.container.set_visibility(not self.inputs.is_store)
        self.run.set_enabled(eligible)
        self.download.set_visibility(self.output is not None)
        self.download.set_enabled(self.output is not None and not self.busy)

    def close(self):
        self.closed = True
        self._release_output()

    async def prepare(self):
        if self.closed or self.busy or self.inputs.is_store:
            return
        from nicegui import run

        project = self.inputs.project.snapshot()
        state, session = self.review.state, self.review.controls.session
        input_revision, review_revision = self.inputs.revision, session.revision
        owner = None
        self._release_output()
        self.busy = True
        self.progress.set_value(0.1)
        self.progress_label.set_text("Validating saved review and source project…")
        self.status.set_text("")
        self.refresh()
        try:
            if project is None:
                raise ReviewError("Select the project ZIP used to generate this review.")
            if session.dirty:
                raise ReviewError("Save choices or discard pending changes before write-back.")
            if self.review.controls.before_export is not None:
                await self.review.controls.before_export()
            source_stamp = project.stamp()
            snapshot = ReviewSession(
                state,
                saved=copy.deepcopy(session.saved),
                rules=copy.deepcopy(session.rules),
                reviewed_documents=set(session.reviewed_documents),
                imported_metadata=copy.deepcopy(session.imported_metadata),
                rules_stale=session.rules_stale,
            )
            decisions_text = await run.io_bound(snapshot.export_text)

            def current():
                return (not self.closed and not self.inputs.closed and self.inputs.revision == input_revision
                        and self.review.state is state and self.review.controls.session is session
                        and session.revision == review_revision and self.inputs.project.snapshot() == project
                        and project.stamp() == source_stamp)

            if not current():
                raise ReviewError("Project inputs or review changed during preparation. Save choices and try again.")
            owner = TemporaryDirectory(prefix="snomed-nicegui-sanitized-")
            output_path = Path(owner.name) / f"{project.path.stem}-sanitized.zip"
            self.progress.set_value(0.35)
            self.progress_label.set_text("Applying reviewed actions to copied JSONCAS/XMI files…")
            result = await run.cpu_bound(
                build_sanitized_zip,
                project.path,
                decisions_text,
                output_path,
                manual_review_layer=(self.manual_layer.value or "").strip() or "webanno.custom.ManualReview",
            )
            if not current():
                raise ReviewError("Project inputs or review changed during write-back. The stale result was discarded.")
            output_token = self._token()
            self.output = SourceFile(result.output_project, owner)
            self.output_token = output_token
            owner = None
            self.progress.set_value(1.0)
            self.progress_label.set_text("Sanitized project ZIP is ready for download.")
            message = (f"Changed {result.changed_annotation_count} annotation(s) in "
                       f"{result.changed_member_count} CAS file(s).")
            if result.unmatched_decisions:
                message += f" {len(result.unmatched_decisions)} applied decision(s) could not be matched."
            self.status.set_text(message)
        except ReviewError as error:
            if not self.closed:
                self.status.set_text(str(error))
                self.progress.set_value(0.0)
                self.progress_label.set_text("Write-back did not run; the source project remains unchanged.")
        except Exception:
            if not self.closed:
                self.status.set_text("Sanitization failed. Check that the selected ZIP matches the saved review and contains readable JSONCAS/XMI files.")
                self.progress.set_value(0.0)
                self.progress_label.set_text("Write-back failed; the source project remains unchanged.")
        finally:
            if owner is not None:
                owner.cleanup()
            self.busy = False
            self.refresh()

    def download_output(self):
        if self.output is None or self.closed:
            return
        try:
            if self._token() != self.output_token or self.output.stamp() is None:
                raise OSError()
            self.ui.download.file(self.output.path, filename=self.output.path.name)
        except OSError:
            self._release_output()
            self.status.set_text("The sanitized ZIP is no longer current or available. Run sanitization again.")
            self.refresh()
