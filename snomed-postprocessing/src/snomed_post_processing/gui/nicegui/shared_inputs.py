"""Page-local shared input controls, settings and explicit annotator inspection."""
from snomed_post_processing.pipelines.policy_check import PolicySettings, project_annotators
from snomed_post_processing.uima_processing.scope import normalize_annotators
from .file_sources import FileSource


def _annotators(project):
    before = project.stamp()
    result = project_annotators(project.path)
    if before != project.stamp():
        raise ValueError("Project changed during inspection.")
    return result


class SharedInputControls:
    def __init__(self, ui):
        self.revision = 0
        self.busy = self.closed = self.ready = False
        self.project_path = None
        self.listeners = []
        ui.label("Shared inputs").classes("text-lg font-medium")
        ui.label("Used by Check policy and Suggest. Changing inputs never starts processing.").classes("text-sm")
        with ui.expansion("Project and policy inputs", value=True).classes("w-full") as self.container:
            with ui.row().classes("w-full items-center"):
                self.data_dir = ui.input("Server data directory", value="data", on_change=self.directory_changed)
                ui.button(icon="refresh", on_click=self.directory_changed).props("flat round dense").tooltip("Refresh server file lists")
            with ui.column().classes("gap-4 w-full min-w-0"):
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
            self.status = ui.label().classes("text-sm")
        ui.context.client.on_delete(self.close)
        self.ready = True
        self.refresh()

    def settings(self):
        lines = lambda text: tuple(line.strip() for line in (text or "").splitlines() if line.strip())
        return PolicySettings(normalize_annotators(self.annotators.value or ()),
                              lines(self.layers.value) or ("gemtex.Concept",), lines(self.ignore.value),
                              self.overlap.value, self.prefix.value or "", (self.feature.value or "").strip())

    def changed(self, _=None):
        if not self.ready or self.closed:
            return
        self.revision += 1
        self.status.set_text("Inputs changed. Run the desired action explicitly.")
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
        if not self.ready or self.closed:
            return
        self.project.refresh_directory()
        self.lists.refresh_directory()
        self.changed()

    def refresh(self):
        self.load_names.set_enabled(self.project.snapshot() is not None and not self.busy)

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

    def close(self):
        self.closed = True
        self.revision += 1
        self.project.close()
        self.lists.close()
        self.listeners.clear()
