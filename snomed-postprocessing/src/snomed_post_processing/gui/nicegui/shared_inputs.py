"""Page-local shared input controls, settings and explicit annotator inspection."""
from snomed_post_processing.pipelines.policy_check import PolicySettings, project_annotators
from snomed_post_processing.uima_processing.scope import normalize_annotators, resolve_annotator_scope
from .file_sources import FileSource
from snomed_post_processing.annotation_source import store_scopes, default_store_scope, AnnotationStoreError


def _annotators(project, scope=None):
    before = project.stamp()
    result = project_annotators(project.path, **({"store_scope": scope} if scope is not None else {}))
    if before != project.stamp():
        raise ValueError("Project changed during inspection.")
    return result


class SharedInputControls:
    def __init__(self, ui):
        self.revision = 0
        self.busy = self.closed = self.ready = False
        self.available_annotators = ()
        self.project_path = None
        self.listeners = []
        ui.label("Shared inputs").classes("text-lg font-medium")
        ui.label("Used by Check policy and Suggest. Changing inputs never starts processing.").classes("text-sm")
        with ui.expansion("Project and policy inputs", value=True).classes("w-full") as self.container:
            with ui.row().classes("w-full items-center"):
                self.data_dir = ui.input("Server data directory", value="data", on_change=self.directory_changed)
                ui.button(icon="refresh", on_click=self.directory_changed).props("flat round dense").tooltip("Refresh server file lists")
            with ui.column().classes("gap-4 w-full min-w-0"):
                self.source_kind = ui.select(["INCEpTION project", "Annotation store (SQLite)"], label="Annotation source",
                                             value="INCEpTION project", on_change=self.source_changed)
                self.zip_project = FileSource(ui, "INCEpTION project ZIP", (".zip",), self.data_dir, self.project_changed)
                self.store = FileSource(ui, "Annotation store SQLite", (".sqlite", ".sqlite3", ".db"), self.data_dir, self.project_changed)
                with ui.column().classes("w-full") as self.store_selection:
                    ui.label("Read-only schema v2 snapshot. Select an export/view scope; combined scopes require unambiguous document/annotator identities.").classes("text-sm")
                    self.scope = ui.select({}, label="SQLite export / view", value=None, on_change=self.changed).classes("w-full")
                    self.inspect_store = ui.button("Inspect SQLite scopes", on_click=self.load_store_scopes)
                self.lists = FileSource(ui, "SNOMED HDF5", (".hdf5", ".h5"), self.data_dir, self.changed)
            with ui.row().classes("w-full items-center"):
                self.annotators = ui.select({}, label="Include annotators (empty = all)", multiple=True,
                                            new_value_mode="add-unique", value=[], on_change=self.changed).classes("grow")
                self.excluded_annotators = ui.select({}, label="Exclude annotators (takes precedence)", multiple=True,
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

    def effective_annotators(self):
        return resolve_annotator_scope(self.available_annotators, self.annotators.value or (),
                                       self.excluded_annotators.value or ())

    def settings(self):
        lines = lambda text: tuple(line.strip() for line in (text or "").splitlines() if line.strip())
        return PolicySettings(self.effective_annotators(),
                              lines(self.layers.value) or ("gemtex.Concept",), lines(self.ignore.value),
                              self.overlap.value, "" if self.is_store else self.prefix.value or "",
                              "sctid" if self.is_store else (self.feature.value or "").strip(),
                              self.scope.value if self.is_store else None)

    @property
    def is_store(self):
        return self.source_kind.value == "Annotation store (SQLite)"

    @property
    def project(self):
        return self.store if self.is_store else self.zip_project

    def source_changed(self, _=None):
        if self.ready and not self.closed:
            self.project_path = None
            self.annotators.set_options({}, value=[])
            self.excluded_annotators.set_options({}, value=[])
            self.available_annotators = ()
            self.scope.set_options({}, value=None)
            self.project_changed()

    async def load_store_scopes(self):
        from nicegui import run
        source = self.store.snapshot()
        if source is None or self.busy or self.closed:
            return
        revision = self.revision
        self.busy = True
        self.refresh()
        try:
            before = source.stamp()
            options = await run.io_bound(store_scopes, source.path)
            if not self.closed and revision == self.revision and source.stamp() == before:
                self.scope.set_options(options, value=self.scope.value if self.scope.value in options else default_store_scope(options))
                self.changed()
                self.status.set_text("SQLite scopes loaded. Select a scope, then run the desired action explicitly.")
        except Exception:
            if not self.closed and revision == self.revision:
                self.status.set_text("Could not inspect SQLite. Use a closed, checkpointed schema v2 annotation-store snapshot.")
        finally:
            self.busy = False
            if not self.closed:
                self.refresh()

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
                    self.excluded_annotators.set_options({}, value=[])
                    self.available_annotators = ()
                    self.scope.set_options({}, value=None)
            self.changed()

    def directory_changed(self, _=None):
        if not self.ready or self.closed:
            return
        self.zip_project.refresh_directory()
        self.store.refresh_directory()
        self.lists.refresh_directory()
        self.changed()

    def refresh(self):
        self.zip_project.container.set_visibility(not self.is_store)
        self.store.container.set_visibility(self.is_store)
        self.store_selection.set_visibility(self.is_store)
        self.feature.set_visibility(not self.is_store)
        self.prefix.set_visibility(not self.is_store)
        self.inspect_store.set_enabled(self.store.snapshot() is not None and not self.busy)
        self.load_names.set_enabled(self.project.snapshot() is not None and not self.busy
                                    and (not self.is_store or self.scope.value is not None))

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
            names = await run.io_bound(_annotators, project, **({"scope": self.scope.value} if self.is_store else {}))
            if not self.closed and revision == self.revision:
                selected = list(normalize_annotators(self.annotators.value or ()))
                excluded = list(normalize_annotators(self.excluded_annotators.value or ()))
                self.available_annotators = tuple(names)
                options = {**{name: name for name in selected + excluded}, **names}
                self.annotators.set_options(options, value=selected)
                self.excluded_annotators.set_options(options, value=excluded)
                self.status.set_text("Annotators loaded. Exclusions take precedence; empty selections include all.")
        except AnnotationStoreError as error:
            if not self.closed and revision == self.revision:
                self.status.set_text(str(error))
        except Exception:
            if not self.closed and revision == self.revision:
                self.status.set_text("Could not read annotators. Check the selected ZIP or SQLite scope.")
        finally:
            self.busy = False
            if not self.closed:
                self.refresh()

    def close(self):
        self.closed = True
        self.revision += 1
        self.zip_project.close()
        self.store.close()
        self.lists.close()
        self.listeners.clear()
