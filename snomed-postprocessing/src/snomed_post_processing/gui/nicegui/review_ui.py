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
        with ui.row():
            self.use = ui.button("Use candidate", on_click=lambda: self.command("candidate")) \
                .tooltip("Stage the inspected selectable candidate; Save choices commits it. Row clicks alone never approve.")
            self.keep = ui.button("Keep original", on_click=lambda: self.command("keep")) \
                .tooltip("Stage an explicit human-reviewed Keep; preserves annotation and ID.")
            self.save = ui.button("Save choices", on_click=lambda: self.command("save"))
            self.discard = ui.button("Discard pending changes", on_click=lambda: self.command("discard"))
        with ui.row():
            self.mark = ui.button("Mark document reviewed", on_click=lambda: self.command("reviewed"))
            self.unmark = ui.button("Unmark document reviewed", on_click=lambda: self.command("unreviewed"))
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
        enabled = not state.is_demo
        protected = bool(row and self.session.protected(row))
        candidate = next((c for c in row.candidates if c.row_id == state.selected_candidate_id), None) if row else None
        self.use.set_enabled(enabled and bool(row) and not protected and bool(candidate and candidate.selectable))
        self.keep.set_enabled(enabled and bool(row) and not protected)
        self.save.set_enabled(enabled and self.session.dirty)
        self.discard.set_enabled(enabled and self.session.dirty)
        self.mark.set_enabled(enabled and bool(row))
        self.unmark.set_enabled(enabled and bool(row))
        self.export.set_enabled(enabled and not self.session.dirty)
        self.upload.set_enabled(enabled)
        self.status.set_text((self.session.status(row) + " · " if row else "")
                             + f"{len(self.session.drafts)} pending choices · {len(self.session.draft_reviewed)} pending document flags · "
                             + f"{len(self.session.reviewed_documents)} saved reviewed documents · {len(self.session.rules)} protected imported rules.")
        if update_grid:
            self.refresh_grid(self.session)

    def command(self, command):
        state = self.get_state()
        try:
            if command == "candidate":
                if state.selected_candidate_id is None:
                    raise ReviewError("Inspect a selectable candidate first.")
                self.session.stage(state.selected_finding_id, state.selected_candidate_id)
            elif command == "keep":
                self.session.stage(state.selected_finding_id)
            elif command == "save":
                self.session.save()
            elif command == "discard":
                self.session.discard()
            elif command in ("reviewed", "unreviewed"):
                self.session.mark_document(state.selected_finding_id, command == "reviewed")
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
