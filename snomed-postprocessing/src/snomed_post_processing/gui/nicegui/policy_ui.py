"""Explicit, page-local policy checks; does not change suggestions or review state."""
import asyncio
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from snomed_post_processing.findings_io import read_critical_findings_json_with_metadata
from snomed_post_processing.annotation_source import AnnotationStoreError
from snomed_post_processing.pipelines.policy_check import PolicyResult, PolicySettings, check_policy
from snomed_post_processing.terminology import policy_label
from snomed_post_processing.uima_processing.scope import annotator_in_scope, normalize_annotators
from .tables import resizable_table
from .file_sources import FileSource


MAX_FINDINGS_BYTES = 50 * 1024 * 1024


def _stamps(*sources):
    return tuple(source.stamp() for source in sources)


def _saved_findings(source):
    before = source.stamp()
    if before[2] > MAX_FINDINGS_BYTES:
        raise ValueError("CriticalFindings JSON exceeds 50 MiB.")
    content = source.path.read_bytes()
    if len(content) > MAX_FINDINGS_BYTES:
        raise ValueError("CriticalFindings JSON exceeds 50 MiB.")
    text = content.decode("utf-8-sig")
    findings, metadata = read_critical_findings_json_with_metadata(StringIO(text))
    scope = metadata.get("annotators", [])
    if not isinstance(scope, list) or any(not isinstance(name, str) for name in scope):
        raise ValueError("Invalid saved annotator scope.")
    for name in ("id_feature", "id_prefix"):
        if name in metadata and not isinstance(metadata[name], str):
            raise ValueError("Invalid saved ID settings.")
    settings = PolicySettings(annotators=normalize_annotators(scope),
                              id_feature=metadata.get("id_feature", "id"),
                              id_prefix=metadata.get("id_prefix", "http://snomed.info/id/"))
    findings = tuple(f for f in findings if annotator_in_scope(f.annotator, settings.annotators))
    count = len({(f.document, f.annotator) for f in findings if not f.ignored})
    if source.stamp() != before:
        raise ValueError("Findings changed while loading.")
    return PolicyResult(settings, findings, count, {"critical-findings.json": text}), before


class _PolicyProgress:
    def __init__(self, path):
        self.path = Path(path)

    def update(self, value, label):
        self.path.write_text(json.dumps({"value": max(0.0, min(1.0, value)), "label": label}), encoding="utf-8")

    def progress(self, value, text):
        check = "inclusion-list" if "Inclusion" in text else "exclusion-list"
        self.update(0.15 + 0.75 * value, f"Checking {check} policy across documents… {value:.0%}")


def _checked_policy(project, lists, settings, progress_path=None):
    before = _stamps(project, lists)
    progress = _PolicyProgress(progress_path) if progress_path is not None else None
    if progress is not None:
        progress.update(0.05, "Preparing annotation source and policy inputs…")
    result = check_policy(project.path, lists.path, settings,
                          progress_obj={"obj": progress} if progress is not None else None)
    if progress is not None:
        progress.update(0.95, "Building policy reports…")
    if before != _stamps(project, lists):
        raise ValueError("Inputs changed during checking.")
    return result, before


def finding_rows(findings):
    return [dict(row_id=index, document=f.document, annotator=f.annotator, sctid=f.code or "",
                 fsn=f.fsn or "", covered_text=f.covered_text, begin=f.offset[0], end=f.offset[1],
                 check=policy_label(f.list_type), layer=f.layer or "") for index, f in enumerate(findings)]


class PolicyCheckControls:
    def __init__(self, ui, inputs):
        self.ui, self.inputs = ui, inputs
        self.revision = 0
        self.busy = self.closed = self.ready = False
        self.result = self.completed_sources = self.completed_stamps = None
        self.result_revision = None
        self.imported_source = None
        self.result_stale = False
        self.restore_revision = 0
        self.result_listeners = []
        ui.label("Check inclusion/exclusion-list policy. No annotations are changed.").classes("text-sm")
        with ui.expansion("Restore CriticalFindings JSON").classes("w-full"):
            self.saved_findings = FileSource(ui, "CriticalFindings JSON", (".json",), inputs.data_dir, self.restore_changed)
            self.restore_button = ui.button("Load saved findings", on_click=self.load_saved)
            ui.label("Restores findings without ZIP/HDF5 or analysis. Full policy reports are not contained in this artifact. Limit: 50 MiB.").classes("text-sm")
        self.run_button = ui.button("Run policy check", on_click=self.run_check)
        with ui.column().classes("w-full gap-1") as self.progress_container:
            self.progress_label = ui.label().classes("text-sm")
            self.progress = ui.linear_progress(value=0).classes("w-full")
        self.status = ui.label().classes("text-sm")
        with ui.column().classes("w-full min-w-0") as self.results:
            self.summary = ui.label().classes("text-sm")
            self.result_source = ui.label("Last successful check. Filters affect display only, not downloads.").classes("text-sm")
            self.empty = ui.label("No findings.")
            self.grid = ui.aggrid({
                "columnDefs": [
                    {"field": "document", "sort": "asc", "sortIndex": 0},
                    {"field": "annotator", "sort": "asc", "sortIndex": 1},
                    {"field": "begin", "width": 80, "filter": "agNumberColumnFilter"},
                    {"field": "end", "width": 80, "filter": "agNumberColumnFilter"},
                    {"field": "sctid", "headerName": "SCTID", "width": 120},
                    {"field": "fsn", "headerName": "FSN", "flex": 2, "minWidth": 350},
                    {"field": "covered_text", "headerName": "Covered text", "flex": 2, "minWidth": 350},
                    {"field": "check", "width": 120}, {"field": "layer", "width": 160},
                ],
                "defaultColDef": {"sortable": True, "resizable": True, "filter": "agTextColumnFilter",
                                  "floatingFilter": True, "editable": False},
                "rowData": [], ":getRowId": "params => String(params.data.row_id)",
            }).classes("w-full h-96 overflow-auto overscroll-contain")
            resizable_table(self.grid)
            ui.button("Clear filters", on_click=self.clear_filters).props("flat dense")
            self.downloads = []
            self.report_buttons = {}
            with ui.row().classes("w-full items-center"):
                for label, filename in (("CriticalFindings JSON", "critical-findings.json"),
                                        ("Markdown", "policy-report.md"),
                                        ("Masked Markdown", "policy-report.masked.md"),
                                        ("Report JSON", "policy-report.json")):
                    button = ui.button(label, on_click=lambda _, filename=filename: self.download(filename))
                    self.downloads.append(button)
                    self.report_buttons[filename] = button
                    if "masked" in filename:
                        button.tooltip("Masks document/annotator names, not clinical text. Not full anonymization.")
        inputs.listeners.append(self.changed)
        ui.context.client.on_delete(self.close)
        self.ready = True
        self.refresh()

    @property
    def result_current(self):
        return self.result is not None and not self.result_stale and (self.imported_source is not None or self.result_revision == self.revision)

    def restore_changed(self):
        if self.ready and not self.closed:
            self.restore_revision += 1
            self.refresh()

    async def load_saved(self):
        from nicegui import run
        source = self.saved_findings.snapshot()
        if self.closed or self.busy or source is None:
            return
        token = self.restore_revision
        self.busy = True
        self.status.set_text("Loading saved findings…")
        self.refresh()
        try:
            result, stamp = await run.io_bound(_saved_findings, source)
            if self.closed or token != self.restore_revision:
                return
            self.result, self.result_revision = result, self.revision
            self.imported_source, self.result_stale = source, False
            self.completed_sources, self.completed_stamps = (source,), (stamp,)
            self.render_result()
            self.result_source.set_text(f"Restored: {source.path.name}. Findings and original JSON only; full policy reports unavailable. Filters affect display only.")
            self.status.set_text("Findings restored in tab 1 and available for generation in tab 2. No analysis or review changes.")
            for listener in self.result_listeners:
                listener()
        except Exception:
            if not self.closed and token == self.restore_revision:
                self.status.set_text("Could not restore CriticalFindings JSON (limit 50 MiB). Previous result retained.")
        finally:
            self.busy = False
            if not self.closed:
                self.refresh()

    def changed(self, _=None):
        if not self.ready or self.closed:
            return
        self.revision += 1
        self.saved_findings.refresh_directory()
        self.status.set_text("Shared inputs changed. Restored findings remain available; generation validates their scope/ID settings."
                             if self.imported_source is not None else "Inputs changed. Run policy check to obtain current results.")
        self.refresh()

    def refresh(self):
        selected = (self.inputs.project.snapshot() is not None and self.inputs.lists.snapshot() is not None
                    and (not self.inputs.is_store or self.inputs.scope.value is not None))
        self.run_button.set_enabled(selected and not self.busy)
        self.progress_container.set_visibility(self.busy)
        self.restore_button.set_enabled(not self.busy and self.saved_findings.snapshot() is not None)
        self.results.set_visibility(self.result_current)
        for filename, button in self.report_buttons.items():
            button.set_enabled(self.result_current and not self.busy and filename in self.result.reports)

    async def run_check(self):
        from nicegui import run
        project, lists = self.inputs.project.snapshot(), self.inputs.lists.snapshot()
        if self.closed or self.busy or project is None or lists is None:
            return
        revision = self.revision
        self.busy = True
        self.status.set_text("Checking policy…")
        self.progress.set_value(0.0)
        self.progress_label.set_text("Preparing policy check…")
        self.refresh()
        progress_owner = TemporaryDirectory(prefix="snomed-nicegui-policy-progress-")
        progress_path = Path(progress_owner.name) / "progress.json"
        try:
            settings = self.inputs.settings()
            task = asyncio.create_task(run.io_bound(_checked_policy, project, lists, settings, progress_path))
            while not task.done():
                await asyncio.sleep(0.15)
                try:
                    update = json.loads(progress_path.read_text(encoding="utf-8"))
                    self.progress.set_value(float(update["value"]))
                    self.progress_label.set_text(str(update["label"]))
                except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                    pass
            result, stamps = await task
            self.progress.set_value(1.0)
            self.progress_label.set_text("Policy check finished.")
            if self.closed:
                return
            if revision != self.revision:
                self.status.set_text("Inputs changed during checking. Older results discarded; run again.")
                return
            self.result, self.result_revision = result, revision
            self.imported_source, self.result_stale = None, False
            self.completed_sources, self.completed_stamps = (project, lists), stamps
            self.render_result()
            self.result_source.set_text("Last successful policy check. Filters affect display only, not downloads.")
            self.status.set_text("Policy check finished. No annotations changed.")
            for listener in self.result_listeners:
                listener()
        except (AnnotationStoreError, ValueError) as error:
            if not self.closed and revision == self.revision:
                self.status.set_text(f"Policy check failed: {error}. Previous successful result retained.")
        except Exception:
            if not self.closed and revision == self.revision:
                self.status.set_text("Policy check failed. Check the annotation source, HDF5 and annotation settings. Previous successful result retained.")
        finally:
            progress_owner.cleanup()
            self.busy = False
            if not self.closed:
                self.refresh()

    def render_result(self):
        result = self.result
        self.grid.options["rowData"] = finding_rows(result.findings)
        self.grid.update()
        self.empty.set_visibility(not result.findings)
        self.grid.set_visibility(bool(result.findings))
        critical = sum(not f.ignored for f in result.findings)
        inclusion = sum(f.list_type == "whitelist" for f in result.findings)
        self.summary.set_text(
            f"{critical} critical · {len(result.findings) - critical} ignored · "
            f"{inclusion} inclusion-list · {len(result.findings) - inclusion} exclusion-list · "
            f"{len({f.document for f in result.findings})} documents · "
            f"{len({f.annotator for f in result.findings})} annotators · "
            f"{result.critical_documents} critical document/annotator pairs")

    async def clear_filters(self):
        await self.grid.run_grid_method("setFilterModel", None)

    async def download(self, filename):
        from nicegui import run
        result, revision = self.result, self.revision
        if self.closed or self.busy or not self.result_current or filename not in result.reports:
            return
        try:
            stamps = await run.io_bound(_stamps, *self.completed_sources)
            if stamps != self.completed_stamps:
                raise ValueError("Inputs changed.")
        except Exception:
            if not self.closed and revision == self.revision:
                self.result_stale = True
                self.changed()
                for listener in self.result_listeners:
                    listener()
                self.status.set_text("Source files changed or are unavailable. Restore findings or run policy check again before downloading.")
            return
        if not self.closed and revision == self.revision and result is self.result and not self.busy:
            self.ui.download.content(result.reports[filename], filename)

    def close(self):
        self.closed = True
        self.revision += 1
        if self.changed in self.inputs.listeners:
            self.inputs.listeners.remove(self.changed)
        self.saved_findings.close()
        self.restore_revision += 1
        self.result = self.completed_sources = self.imported_source = None
