"""Event adapters for explicit review; no framework imports at module load."""
import copy
from contextlib import nullcontext

from snomed_post_processing.sanitization import ASSOCIATION_TYPE_DESCRIPTIONS, SUPPORTED_ASSOCIATION_TYPES
from snomed_post_processing.sanitization.conditions import DEFAULT_CONDITION_ASSOCIATIONS

from .file_sources import FileSource
from .review import MAX_DECISIONS_BYTES, ReviewError, ReviewSession, load_review


class ReviewControls:
    def __init__(self, ui, get_state, get_revision, begin_load, refresh_grid, *, conditions_container=None, restore_container=None, data_dir="data"):
        self.ui, self.get_state = ui, get_state
        self.get_revision, self.begin_load = get_revision, begin_load
        self.refresh_grid = refresh_grid
        self.data_dir = data_dir
        self.session = ReviewSession(get_state())
        self.before_export = None
        self.notice = ui.label().classes(
            "w-full rounded-md border px-4 py-3 font-medium whitespace-pre-wrap shadow-sm"
        ).props('role="alert" aria-live="assertive"')
        self.notice.set_visibility(False)
        self.status = ui.label().classes("text-sm whitespace-pre-wrap text-slate-700")
        self.menu = ui.context_menu().props("no-parent-event")
        self.menu_target = None
        ui.label("Findings: right-click for Accept Suggestion, Remove concept ID, Delete, Manual Review or Keep Original. Selected finding candidates: right-click for Apply. Save choices commits staged actions; Shift + right-click opens the browser menu.").classes("text-sm")
        with ui.row():
            self.save = ui.button("Save choices", on_click=lambda: self.command("save"))
            self.discard = ui.button("Discard pending changes", on_click=lambda: self.command("discard"))
        with conditions_container if conditions_container is not None else nullcontext():
            with ui.expansion("Automatic conditions", value=False).classes("w-full") as self.conditions_panel:
                ui.label(
                    "Historical associations apply only to inclusion-list findings. BM25 gap selection is an opt-in heuristic. "
                    "Manual, imported and concept-rule decisions are preserved; no CAS files change here."
                ).classes("text-sm")
                self.condition_associations = ui.select(
                    {name: f"{name} — {ASSOCIATION_TYPE_DESCRIPTIONS.get(name, '')}"
                     for name in SUPPORTED_ASSOCIATION_TYPES},
                    multiple=True,
                    value=list(DEFAULT_CONDITION_ASSOCIATIONS),
                    label="Historical association types",
                ).props("use-chips clearable").classes("w-full")
                self.condition_bm25 = ui.checkbox("Enable BM25 automatic selection (heuristic)", value=False)
                self.condition_bm25_exclusions = ui.checkbox(
                    "Include exclusion-list findings in BM25 automatic selection", value=False,
                )
                with ui.row().classes("w-full gap-4 flex-wrap"):
                    self.condition_dominance = ui.number(
                        "Minimum BM25 gap dominance", value=2 / 3, min=0, max=1, step=0.05,
                    ).classes("w-full md:flex-1 md:min-w-80")
                    self.condition_lead = ui.number(
                        "Minimum BM25 relative lead", value=0.20, min=0, max=1, step=0.05,
                    ).classes("w-full md:flex-1 md:min-w-80")
                ui.label(
                    "BM25 requires at least three distinct comparable targets, a unique leader and complete retrieval. "
                    "D compares the first score gap with the largest later gap; M is the first gap divided by the top score."
                ).classes("text-sm")
                with ui.row():
                    self.apply_conditions_button = ui.button("Apply Conditions", on_click=self.apply_conditions)
                    self.undo_conditions_button = ui.button("Undo Automatic Conditions", on_click=self.undo_conditions)
                self.condition_status = ui.label().classes("text-sm whitespace-pre-wrap")
        with ui.row():
            self.export = ui.button("Download reviewed decisions JSON", on_click=self.download)
        ui.label("Save document flags with Save choices. Reviewed is progress, not proof of replacements for all findings.")
        ui.label("Import replaces current review. Imported deletion, manual-review and ID-removal actions remain editable after validation. Reapply imported rules against current inputs in tab 2 to edit their Apply choices.")
        with restore_container if restore_container is not None else nullcontext():
            self.saved_decisions = FileSource(
                ui, "Reviewed decisions JSON", (".json",), self.data_dir, self.restore_source_changed,
                max_upload_bytes=MAX_DECISIONS_BYTES,
            )
            self.upload = self.saved_decisions.uploader
            self.restore_button = ui.button("Load saved decisions", on_click=self.load_saved)
            ui.label("Select a reviewed-decisions JSON file from upload, the data directory, or a server path, then load it explicitly. Limit: 50 MiB.").classes("text-sm")

    def _show_notice(self, message="", *, level="info"):
        colors = {
            "info": "border-blue-300 bg-blue-50 text-blue-950",
            "success": "border-green-400 bg-green-50 text-green-950",
            "warning": "border-amber-400 bg-amber-50 text-amber-950",
            "error": "border-red-500 bg-red-50 text-red-950",
        }
        self.notice.classes(
            remove="border-blue-300 bg-blue-50 text-blue-950 border-green-400 bg-green-50 text-green-950 border-amber-400 bg-amber-50 text-amber-950 border-red-500 bg-red-50 text-red-950",
            add=colors[level],
        )
        self.notice.set_text(message)
        self.notice.set_visibility(bool(message))

    def reset(self):
        self.session = ReviewSession(self.get_state())
        self.condition_status.set_text("")
        self._show_notice()
        self.refresh()

    def refresh(self, *, update_grid=True):
        state = self.get_state()
        row = state.selected_finding
        enabled = state.source_name is not None
        self.menu.close()
        self.menu_target = None
        self.save.set_enabled(enabled and self.session.dirty)
        self.discard.set_enabled(enabled and self.session.dirty)
        self.export.set_enabled(enabled and not self.session.dirty and not self.session.invalid_rules)
        self.saved_decisions.set_enabled(enabled)
        self.restore_button.set_enabled(enabled and self.saved_decisions.snapshot() is not None)
        self.apply_conditions_button.set_enabled(enabled)
        self.undo_conditions_button.set_enabled(enabled and self.session.conditions_undo is not None)
        self.status.set_text((self.session.status(row) + " · " if row else "")
                             + f"{len(self.session.drafts)} pending choices · {len(self.session.draft_reviewed)} pending document flags · "
                             + f"{len(self.session.reviewed_documents)} saved reviewed documents · {len(self.session.effective_rules)} rule decisions"
                             + (" · pending rule changes" if self.session.draft_rules is not None else "")
                             + (" · rule inputs changed; reapply or clear rules" if self.session.invalid_rules else ""))
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
            ("Remove concept ID", "clear_id", enabled),
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
            elif command in ("clear_id", "delete", "manual_edit"):
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

    def apply_conditions(self):
        try:
            reviewed_before = set(self.session.reviewed_documents)
            result = self.session.apply_automatic_conditions(
                tuple(self.condition_associations.value or ()),
                bm25_enabled=bool(self.condition_bm25.value),
                bm25_min_dominance=float(self.condition_dominance.value),
                bm25_min_relative_lead=float(self.condition_lead.value),
                bm25_include_exclusion_findings=bool(self.condition_bm25_exclusions.value),
            )
            self.condition_status.set_text(
                f"Conditions updated {result.changed} row(s); left {result.skipped} unchanged; "
                f"newly reviewed {len(result.reviewed_documents - reviewed_before)} document(s)."
            )
            self.refresh()
        except (ReviewError, TypeError, ValueError) as error:
            self.ui.notify(str(error), type="warning")

    def undo_conditions(self):
        try:
            result = self.session.undo_automatic_conditions()
            self.condition_status.set_text(
                f"Undid {result.changed} automatic selection(s); "
                f"preserved {result.skipped} changed/manual selection(s)."
            )
            self.refresh()
        except ReviewError as error:
            self.ui.notify(str(error), type="warning")

    async def download(self):
        original_state, original_session = self.get_state(), self.session
        revision = original_session.revision
        try:
            if original_session.dirty:
                raise ReviewError("Save choices or discard pending changes before exporting reviewed decisions.")
            if self.before_export is not None:
                await self.before_export()
            # Copy only review data, not the immutable source tuple or navigation.
            # The worker must never iterate dictionaries being changed by a UI save.
            snapshot = ReviewSession(original_state, saved=copy.deepcopy(original_session.saved),
                                     rules=copy.deepcopy(original_session.rules),
                                     reviewed_documents=set(original_session.reviewed_documents),
                                     imported_metadata=copy.deepcopy(original_session.imported_metadata),
                                     rules_stale=original_session.rules_stale)
            from nicegui import run
            text = await run.io_bound(snapshot.export_text)
            if self.get_state() is not original_state or self.session is not original_session or self.session.revision != revision:
                raise ReviewError("Review changed while preparing the download. Download again after saving choices.")
            self.ui.download.content(text, "reviewed_sanitization_decisions.json", media_type="application/json")
        except ReviewError as error:
            self.ui.notify(str(error), type="warning")

    def restore_source_changed(self):
        if hasattr(self, "restore_button"):
            self.restore_button.set_enabled(self.get_state().source_name is not None and self.saved_decisions.snapshot() is not None)

    def _restore_success(self, loaded):
        self.session = loaded
        self.condition_status.set_text("")
        self.refresh()
        detail = (f" {loaded.remapped_findings} reordered finding(s) were matched by annotation identity."
                  if loaded.remapped_findings else "")
        self._show_notice(
            "Reviewed decisions restored; prior saved/pending choices and flags replaced. No CAS changed." + detail,
            level="success",
        )

    def _restore_failure(self, message):
        self._show_notice(message + " Current review unchanged.", level="error")
        self.ui.notify("Review restore failed — see the highlighted message in Review & apply.", type="negative")

    async def load_saved(self):
        from nicegui import run
        source = self.saved_decisions.snapshot()
        if source is None or self.get_state().source_name is None:
            return
        revision = self.begin_load()
        original_state, original_session = self.get_state(), self.session
        edit_revision = self.session.revision
        self._show_notice("Loading reviewed decisions; the current review remains until loading succeeds.", level="info")
        try:
            content = await run.io_bound(source.path.read_bytes)
            loaded = await run.io_bound(load_review, content, original_state)
        except (ReviewError, OSError) as error:
            if revision == self.get_revision():
                message = str(error) if isinstance(error, ReviewError) else "Could not read reviewed decisions JSON."
                self._restore_failure(message)
            return
        if revision != self.get_revision() or self.get_state() is not original_state or self.session is not original_session:
            return
        if self.session.revision != edit_revision:
            self._show_notice("Review changed while importing. Import again to replace it; current review unchanged.", level="warning")
            return
        self._restore_success(loaded)

    async def load(self, event):
        revision = self.begin_load()
        original_state, original_session = self.get_state(), self.session
        edit_revision = self.session.revision
        self._show_notice("Loading reviewed decisions; the current review remains until loading succeeds.", level="info")
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
                self._restore_failure(message)
                self.upload.reset()
            return
        if revision != self.get_revision() or self.get_state() is not original_state or self.session is not original_session:
            return
        if self.session.revision != edit_revision:
            self._show_notice("Review changed while importing. Import again to replace it; current review unchanged.", level="warning")
            self.upload.reset()
            return
        self._restore_success(loaded)
        self.upload.reset()
