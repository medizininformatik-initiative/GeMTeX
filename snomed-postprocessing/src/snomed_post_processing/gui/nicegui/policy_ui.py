"""Explicit, page-local policy checks; does not change suggestions or review state."""
from snomed_post_processing.pipelines.policy_check import PolicySettings, check_policy, project_annotators
from snomed_post_processing.terminology import policy_label
from snomed_post_processing.uima_processing.scope import normalize_annotators
from .file_sources import FileSource


def _stamps(project, lists):
    return project.stamp(), lists.stamp()


def _checked_policy(project, lists, settings):
    before = _stamps(project, lists)
    result = check_policy(project.path, lists.path, settings)
    if before != _stamps(project, lists):
        raise ValueError("Inputs changed during checking.")
    return result, before


def _annotators(project):
    before = project.stamp()
    result = project_annotators(project.path)
    if before != project.stamp():
        raise ValueError("Project changed during inspection.")
    return result


def finding_rows(findings):
    return [dict(row_id=index, document=f.document, annotator=f.annotator, sctid=f.code or "",
                 fsn=f.fsn or "", covered_text=f.covered_text, begin=f.offset[0], end=f.offset[1],
                 check=policy_label(f.list_type), layer=f.layer or "") for index, f in enumerate(findings)]


class PolicyCheckControls:
    def __init__(self, ui):
        self.ui = ui
        self.revision = 0
        self.busy = self.closed = self.ready = False
        self.result = self.completed_sources = self.completed_stamps = None
        self.result_revision = None
        self.project_path = None
        self.listeners = []
        self.result_listeners = []
        ui.label("Check inclusion/exclusion-list policy. No annotations are changed.").classes("text-sm")
        with ui.expansion("Project and policy inputs", value=True).classes("w-full"):
            with ui.row().classes("w-full items-center"):
                self.data_dir = ui.input("Server data directory", value="data", on_change=self.directory_changed)
                ui.button(icon="refresh", on_click=self.directory_changed).props("flat round dense").tooltip("Refresh server file lists")
            with ui.element("div").classes("grid grid-cols-1 lg:grid-cols-2 gap-4 w-full"):
                self.project = FileSource(ui, "INCEpTION project ZIP", (".zip",), self.data_dir, self.project_changed)
                self.lists = FileSource(ui, "SNOMED HDF5", (".hdf5", ".h5"), self.data_dir, self.changed)
            with ui.row().classes("w-full items-center"):
                self.annotators = ui.select({}, label="Annotators (empty = all)", multiple=True,
                                            new_value_mode="add-unique", value=[], on_change=self.changed).classes("grow")
                self.load_names = ui.button("Load annotators", on_click=self.load_annotators)
            with ui.expansion("Annotation settings").classes("w-full"):
                self.layers = ui.textarea("Target annotation types (one per line)",
                                          value="gemtex.Concept\nwebanno.custom.Concept", on_change=self.changed).classes("w-full")
                self.ignore = ui.textarea("Ignore overlap types (one per line)", value="", on_change=self.changed).classes("w-full")
                self.overlap = ui.select(["overlap", "covered-by", "contains", "exact"],
                                         label="Ignore overlap mode", value="overlap", on_change=self.changed)
                self.feature = ui.input("SNOMED ID feature", value="id", on_change=self.changed)
                self.prefix = ui.input("SNOMED ID prefix (empty for plain SCTIDs)",
                                       value="http://snomed.info/id/", on_change=self.changed).classes("w-full")
        with ui.row().classes("items-center"):
            self.run_button = ui.button("Run policy check", on_click=self.run_check)
            self.spinner = ui.spinner()
        self.status = ui.label().classes("text-sm")
        with ui.column().classes("w-full min-w-0") as self.results:
            self.summary = ui.label().classes("text-sm")
            ui.label("Last successful check. Filters affect display only, not downloads.").classes("text-sm")
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
            ui.button("Clear filters", on_click=self.clear_filters).props("flat dense")
            self.downloads = []
            with ui.row().classes("w-full items-center"):
                for label, filename in (("CriticalFindings JSON", "critical-findings.json"),
                                        ("Markdown", "policy-report.md"),
                                        ("Masked Markdown", "policy-report.masked.md"),
                                        ("Report JSON", "policy-report.json")):
                    button = ui.button(label, on_click=lambda _, filename=filename: self.download(filename))
                    self.downloads.append(button)
                    if "masked" in filename:
                        button.tooltip("Masks document/annotator names, not clinical text. Not full anonymization.")
        ui.context.client.on_delete(self.close)
        self.ready = True
        self.refresh()

    def changed(self, _=None):
        if not self.ready or self.closed:
            return
        self.revision += 1
        self.status.set_text("Inputs changed. Run policy check to obtain current results.")
        self.refresh()
        for listener in self.listeners:
            listener()

    def project_changed(self):
        if self.ready and not self.closed:
            if not self.project.uploading:
                source = self.project.snapshot()
                path = source.path if source is not None else None
                if path != self.project_path:
                    self.project_path = path
                    self.annotators.set_options({}, value=[])
            self.changed()

    def directory_changed(self, _=None):
        if not self.ready:
            return
        self.project.refresh_directory()
        self.lists.refresh_directory()
        self.changed()

    def refresh(self):
        selected = self.project.snapshot() is not None and self.lists.snapshot() is not None
        self.run_button.set_enabled(selected and not self.busy)
        self.load_names.set_enabled(self.project.snapshot() is not None and not self.busy)
        self.spinner.set_visibility(self.busy)
        current = self.result is not None and self.result_revision == self.revision
        self.results.set_visibility(current)
        for button in self.downloads:
            button.set_enabled(current and not self.busy)

    def settings(self):
        lines = lambda text: tuple(line.strip() for line in (text or "").splitlines() if line.strip())
        return PolicySettings(normalize_annotators(self.annotators.value or ()),
                              lines(self.layers.value) or ("gemtex.Concept",), lines(self.ignore.value),
                              self.overlap.value, self.prefix.value or "", (self.feature.value or "").strip())

    async def load_annotators(self):
        from nicegui import run
        project = self.project.snapshot()
        if project is None or self.busy or self.closed:
            return
        revision = self.revision
        self.busy = True
        self.status.set_text("Reading annotator names…")
        self.refresh()
        try:
            names = await run.io_bound(_annotators, project)
            if not self.closed and revision == self.revision:
                selected = list(normalize_annotators(self.annotators.value or ()))
                options = {**{name: name for name in selected}, **names}
                self.annotators.set_options(options, value=selected)
                self.status.set_text("Annotators loaded. Empty selection includes all annotators.")
        except Exception:
            if not self.closed and revision == self.revision:
                self.status.set_text("Could not read annotators. Use a project ZIP containing JSON CAS or XMI, not Java serialized CAS.")
        finally:
            self.busy = False
            if not self.closed:
                self.refresh()

    async def run_check(self):
        from nicegui import run
        project, lists = self.project.snapshot(), self.lists.snapshot()
        if self.closed or self.busy or project is None or lists is None:
            return
        revision, settings = self.revision, self.settings()
        self.busy = True
        self.status.set_text("Checking policy…")
        self.refresh()
        try:
            result, stamps = await run.io_bound(_checked_policy, project, lists, settings)
            if self.closed:
                return
            if revision != self.revision:
                self.status.set_text("Inputs changed during checking. Older results discarded; run again.")
                return
            self.result, self.result_revision = result, revision
            self.completed_sources, self.completed_stamps = (project, lists), stamps
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
            self.status.set_text("Policy check finished. No annotations changed.")
            for listener in self.result_listeners:
                listener()
        except Exception:
            if not self.closed and revision == self.revision:
                self.status.set_text("Policy check failed. Check the ZIP (JSON CAS/XMI), HDF5 and annotation settings. Previous successful result retained.")
        finally:
            self.busy = False
            if not self.closed:
                self.refresh()

    async def clear_filters(self):
        await self.grid.run_grid_method("setFilterModel", None)

    async def download(self, filename):
        from nicegui import run
        result, revision = self.result, self.revision
        if self.closed or self.busy or result is None or self.result_revision != revision:
            return
        try:
            stamps = await run.io_bound(_stamps, *self.completed_sources)
            if stamps != self.completed_stamps:
                raise ValueError("Inputs changed.")
        except Exception:
            if not self.closed and revision == self.revision:
                self.changed()
                self.status.set_text("Input files changed or are unavailable. Run policy check again before downloading.")
            return
        if not self.closed and revision == self.revision and result is self.result and not self.busy:
            self.ui.download.content(result.reports[filename], filename)

    def close(self):
        self.closed = True
        self.revision += 1
        self.project.close()
        self.lists.close()
        self.result = self.completed_sources = None
