"""Event adapters for explicit review; no framework imports at module load."""
import copy

from .review import MAX_DECISIONS_BYTES, ReviewError, ReviewSession, load_review


class ReviewControls:
    def __init__(self, ui, get_state, get_revision, begin_load, refresh_grid):
        self.ui, self.get_state = ui, get_state
        self.get_revision, self.begin_load = get_revision, begin_load
        self.refresh_grid = refresh_grid
        self.session = ReviewSession(get_state())
        self.status = ui.label().classes("text-sm whitespace-pre-wrap")
        self.menu = ui.context_menu().props("no-parent-event")
        self.menu_target = None
        ui.label("Findings: right-click for Accept Suggestion, Delete, Manual Review or Keep Original. Selected finding candidates: right-click for Apply. Save choices commits staged actions; Shift + right-click opens the browser menu.").classes("text-sm")
        with ui.row():
            self.save = ui.button("Save choices", on_click=lambda: self.command("save"))
            self.discard = ui.button("Discard pending changes", on_click=lambda: self.command("discard"))
        with ui.row():
            self.export = ui.button("Download reviewed decisions JSON", on_click=self.download)
        ui.label("Save document flags with Save choices. Reviewed is progress, not proof of replacements for all findings.")
        ui.label("Import replaces current review. Imported rule/deletion/manual-edit decisions are retained, not revalidated; edit them in Streamlit.")
        self.upload = ui.upload(label="Load reviewed decisions JSON (replaces current review)", on_upload=self.load,
                                auto_upload=True, multiple=False, max_file_size=MAX_DECISIONS_BYTES,
                                on_rejected=lambda: self.status.set_text("Decisions upload rejected; current review unchanged.")) \
            .props("accept=.json").classes("max-w-full")

    def reset(self):
        self.session = ReviewSession(self.get_state())
        self.refresh()

    def refresh(self, *, update_grid=True):
        state = self.get_state()
        row = state.selected_finding
        enabled = state.source_name is not None
        self.menu.close()
        self.menu_target = None
        self.save.set_enabled(enabled and self.session.dirty)
        self.discard.set_enabled(enabled and self.session.dirty)
        self.export.set_enabled(enabled and not self.session.dirty)
        self.upload.set_enabled(enabled)
        self.status.set_text((self.session.status(row) + " · " if row else "")
                             + f"{len(self.session.drafts)} pending choices · {len(self.session.draft_reviewed)} pending document flags · "
                             + f"{len(self.session.reviewed_documents)} saved reviewed documents · {len(self.session.rules)} protected imported rules.")
        if update_grid:
            self.refresh_grid(self.session)

    def toggle_document(self, document, source):
        if self.get_state() is not source:
            self.ui.notify("This document is from an older upload.", type="warning")
            return
        row = next((row for row in source.findings if row.document == document), None)
        if row is None:
            return
        try:
            reviewed = self.session.draft_reviewed.get(document, document in self.session.reviewed_documents)
            self.session.mark_document(row.row_id, not reviewed)
            self.refresh()
        except ReviewError as error:
            self.ui.notify(str(error), type="warning")

    def open_menu(self, event, *, candidates=False):
        state = self.get_state()
        row = state.selected_finding
        if row is None:
            return
        target = (state, self.session, row.row_id, state.selected_candidate_id)
        self.menu_target = target
        # Quasar treats its anchor as "inside" for outside-click dismissal.
        self.menu.props["target"] = f"#{event.sender.html_id}"
        candidate = next((c for c in row.candidates if c.row_id == state.selected_candidate_id), None)
        enabled = state.source_name is not None and not self.session.protected(row)
        actions = (("Apply", "candidate", enabled and bool(candidate and candidate.selectable)),) if candidates else (
            ("Accept Suggestion", "accept", enabled and self.session.proposed_candidate(row.row_id) is not None),
            ("Delete", "delete", enabled),
            ("Manual Review", "manual_edit", enabled),
            ("Keep Original", "keep", enabled),
        )
        self.menu.clear()
        with self.menu:
            for label, command, available in actions:
                item = self.ui.menu_item(label, on_click=lambda _, command=command: self.menu_command(target, command))
                item.set_enabled(available)
                if command == "accept":
                    item.tooltip("Use the saved proposed SCTID only when it matches one selectable candidate. Otherwise choose a candidate below and use Apply.")
        self.menu.run_method("show", {"clientX": event.args["clientX"], "clientY": event.args["clientY"]})

    def menu_command(self, target, command):
        state = self.get_state()
        if (self.menu_target is not target or target[0] is not state or target[1] is not self.session
                or target[2:] != (state.selected_finding_id, state.selected_candidate_id)):
            self.ui.notify("This menu no longer matches the current finding. Right-click again.", type="warning")
            return
        self.command(command)

    def command(self, command):
        state = self.get_state()
        try:
            if command == "accept":
                self.session.accept_suggestion(state.selected_finding_id)
            elif command == "candidate":
                if state.selected_candidate_id is None:
                    raise ReviewError("Inspect a selectable candidate first.")
                self.session.stage(state.selected_finding_id, state.selected_candidate_id)
            elif command in ("delete", "manual_edit"):
                self.session.stage(state.selected_finding_id, action=command)
            elif command == "keep":
                self.session.stage(state.selected_finding_id)
            elif command == "save":
                self.session.save()
            elif command == "discard":
                self.session.discard()
            self.refresh()
        except ReviewError as error:
            self.ui.notify(str(error), type="warning")

    async def download(self):
        original_state, original_session = self.get_state(), self.session
        revision = original_session.revision
        try:
            if original_session.dirty:
                raise ReviewError("Save choices or discard pending changes before exporting reviewed decisions.")
            # Copy only review data, not the immutable source tuple or navigation.
            # The worker must never iterate dictionaries being changed by a UI save.
            snapshot = ReviewSession(original_state, saved=copy.deepcopy(original_session.saved),
                                     rules=copy.deepcopy(original_session.rules),
                                     reviewed_documents=set(original_session.reviewed_documents),
                                     imported_metadata=copy.deepcopy(original_session.imported_metadata))
            from nicegui import run
            text = await run.io_bound(snapshot.export_text)
            if self.get_state() is not original_state or self.session is not original_session or self.session.revision != revision:
                raise ReviewError("Review changed while preparing the download. Download again after saving choices.")
            self.ui.download.content(text, "reviewed_sanitization_decisions.json", media_type="application/json")
        except ReviewError as error:
            self.ui.notify(str(error), type="warning")

    async def load(self, event):
        revision = self.begin_load()
        original_state, original_session = self.get_state(), self.session
        edit_revision = self.session.revision
        self.status.set_text("Loading reviewed decisions; the current review remains until loading succeeds.")
        try:
            self.session._require_source()
            if event.file.size() > MAX_DECISIONS_BYTES:
                raise ReviewError("Reviewed decisions JSON exceeds the 50 MiB upload limit.")
            content = await event.file.read()
            from nicegui import run
            loaded = await run.io_bound(load_review, content, original_state)
        except (ReviewError, OSError) as error:
            if revision == self.get_revision():
                message = str(error) if isinstance(error, ReviewError) else "Could not read uploaded reviewed decisions JSON."
                self.status.set_text(message + " Current review unchanged.")
                self.upload.reset()
            return
        if revision != self.get_revision() or self.get_state() is not original_state or self.session is not original_session:
            return
        if self.session.revision != edit_revision:
            self.status.set_text("Review changed while importing. Import again to replace it; current review unchanged.")
            self.upload.reset()
            return
        self.session = loaded
        self.refresh()
        self.status.set_text("Reviewed decisions restored; prior saved/pending choices and flags replaced. No CAS changed.")
        self.upload.reset()
