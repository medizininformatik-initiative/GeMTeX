"""Per-page review panel: inspection, document navigation and review JSON controls."""
from snomed_post_processing.review_context import ReviewContext

from .state import PreviewState
from .review_ui import ReviewControls
from .suggestions import MAX_SUGGESTIONS_BYTES, SuggestionsPreviewError, load_suggestions_preview


def _finding_rows(state, session=None):
    keys = ("row_id", "suggestion_index", "document", "annotator", "code", "text", "status", "policy_issue", "ignored")
    rows = [{key: getattr(row, key) for key in keys} for row in state.findings]
    if session is not None:
        for values, row in zip(rows, state.findings):
            values["review"] = session.status(row)
            values["document_reviewed"] = row.document in session.reviewed_documents
    return rows


def _candidate_rows(finding):
    return [
        {"row_id": item.row_id, "rank": item.rank, "code": item.code, "fsn": item.fsn,
         "score": item.score, "role": "Selectable" if item.selectable else "Context only — not selectable"}
        for item in finding.candidates
    ]


class ReviewPanelControls:
    def __init__(self, ui, panel, *, banner, source, scope):
        self.ui, self.panel = ui, panel
        self.banner, self.source, self.scope = banner, source, scope
        self.state = PreviewState()
        self.review_context = ReviewContext()
        self.load_revision = 0
        self.active_document = None
        self.document_slides = {}
        self.keyboard = ui.keyboard(on_key=self.handle_key)
        self.keyboard.active = False

        upload_controls = ui.row().classes("w-full items-start")
        self.upload_status = ui.label().classes("text-sm")
        self.counts = ui.label().classes("text-sm")
        # Do not keep-alive slides: cached panels retain stale DOM for the moved grid.
        self.documents = ui.carousel(arrows=False, navigation=True).props(
            "height=auto navigation-position=top control-color=primary"
        ).classes("w-full")
        self.empty = ui.label("No findings in the current artifact scope.")
        with ui.column().classes("w-full min-w-0 gap-4") as self.workspace:
            with ui.column().classes("w-full min-w-0"):
                # ui.label("Findings — click a row to inspect").classes("text-lg")
                self.finding_grid = ui.aggrid({
                    "columnDefs": [
                        {"field": "annotator", "headerName": "Annotator"},
                        {"field": "code", "headerName": "Source SCTID", "width": 120},
                        {"field": "text", "headerName": "Covered text", "flex": 2, "minWidth": 350},
                        {"field": "status", "headerName": "Status", "minWidth": 220},
                        {"field": "policy_issue", "headerName": "Policy check"},
                        {"field": "review", "headerName": "Manual review", "minWidth": 250},
                        {"field": "ignored", "headerName": "Ignored", "maxWidth": 100},
                    ],
                    "defaultColDef": {"sortable": True, "filter": "agTextColumnFilter", "floatingFilter": True, "resizable": True, "editable": False},
                    "rowData": [],
                    ":getRowId": "params => params.data.row_id",
                    "rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True},
                }).classes("w-full h-80 overflow-auto overscroll-contain")
            with ui.column().classes("w-full min-w-0"):
                ui.label("Selected finding").classes("text-lg")
                # identity = ui.label("Select a finding. Nothing is preselected.")
                with ui.element("div").classes("grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 w-full min-w-0"):
                    with ui.column().classes("w-full min-w-0 gap-1"):
                        ui.label("Annotation").classes("text-sm font-medium")
                        self.covered_text = ui.label().classes("whitespace-pre-wrap break-words")
                        self.finding_details = ui.label().classes("text-sm whitespace-pre-wrap break-words")
                    with ui.column().classes("w-full min-w-0 gap-1"):
                        ui.label("Suggestion rationale & retrieval").classes("text-sm font-medium")
                        self.proposed = ui.label().classes("text-sm whitespace-pre-wrap break-words")
                        self.rationale = ui.label().classes("text-sm whitespace-pre-wrap break-words")
                        # limits = ui.label().classes("text-amber-900 whitespace-pre-wrap break-words")
                self.candidate_grid = ui.aggrid({
                    "columnDefs": [
                        {"field": "rank", "headerName": "Rank", "width": 80, "filter": "agNumberColumnFilter"},
                        {"field": "code", "headerName": "SCTID", "width": 120},
                        {"field": "fsn", "headerName": "FSN", "flex": 2, "minWidth": 240},
                        {"field": "score", "headerName": "Score", "width": 120, "filter": "agNumberColumnFilter",
                         ":valueFormatter": "params => params.value == null ? '' : params.value.toFixed(2)",
                         "headerTooltip": "Displayed to two decimal places only. Sorting, ranks and saved JSON retain full precision; raw scores remain in candidate evidence."},
                        {"field": "role", "headerName": "Candidate role", "width": 200},
                    ],
                    "defaultColDef": {"sortable": True, "filter": "agTextColumnFilter", "resizable": True, "editable": False},
                    "rowData": [],
                    ":getRowId": "params => params.data.row_id",
                    "rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True},
                }).classes("w-full h-64 overflow-auto overscroll-contain")
                self.preview = ui.label("Candidate clicks only preview; they do not approve anything.")
                self.evidence = ui.label().classes("text-sm whitespace-pre-wrap")
                self.controls = ReviewControls(ui, lambda: self.state, lambda: self.load_revision,
                                               self.begin_load, self.refresh_documents)
        ui.label("Review JSON only. ZIP write-back and deployment remain disconnected.")
        with ui.expansion("Explicit concept rule decisions", value=True).classes("w-full") as self.rule_area:
            self.rule_summary = ui.label().classes("text-sm")
            self.rule_grid = ui.aggrid({
                "columnDefs": [{"field": "apply", "headerName": "Apply", "cellDataType": "boolean",
                                ":editable": "params => params.data.editable", "width": 90}]
                              + [{"field": field} for field in ("document", "annotator", "layer", "offset", "source", "action", "target", "rule")]
                              + [{"field": "override_allowed", "headerName": "Override policy"},
                                 {"field": "override", "headerName": "Policy actually overridden"}],
                "defaultColDef": {"sortable": True, "filter": True, "resizable": True, "editable": False},
                "rowData": [], ":getRowId": "params => params.data.row_id",
            }).classes("w-full h-64 overflow-auto overscroll-contain")
            self.rule_grid.on("cellValueChanged", self.toggle_rule, args=["data"])
            ui.button("Keep manual decisions for conflicts", on_click=self.keep_manual_rules).props("flat dense")
            ui.button("Clear all pending rule decisions", on_click=self.clear_rules).props("flat dense")
            self.rule_source_download = ui.button("Download rule-only review source JSON", on_click=self.download_rule_source).props("flat dense")
            self.rule_source_download.tooltip("Save alongside reviewed decisions to restore a rule-only review after reload.")
            ui.label("Apply choices are staged. Save choices commits them; clearing rules leaves definitions and CAS unchanged.").classes("text-sm")
        self.documents.on_value_change(lambda event: self.change_document(event.value))
        with upload_controls:
            self.uploader = ui.upload(label="Load suggestions JSON", on_upload=self.load_upload,
                                      auto_upload=True, multiple=False, max_file_size=MAX_SUGGESTIONS_BYTES,
                                      on_rejected=lambda: self.upload_status.set_text("Upload rejected. Choose one JSON file up to 50 MiB; current preview unchanged.")) \
                .props("accept=.json").classes("max-w-full")
        # Native DOM right-clicks provide coordinates and immutable rendered row IDs;
        # AG Grid's serialized cellContextMenu event omits pointer coordinates.
        context_handler = """event => {
            const row = event.target.closest('.ag-row[row-id]');
            if (!row || event.shiftKey) return;
            event.preventDefault();
            emit({data: {row_id: row.getAttribute('row-id')}, clientX: event.clientX, clientY: event.clientY});
        }"""
        self.finding_grid.on("contextmenu", self.finding_menu, js_handler=context_handler)
        self.candidate_grid.on("contextmenu", self.candidate_menu, js_handler=context_handler)
        # Request row data only; unrestricted AG Grid events contain cycles.
        self.finding_grid.on("rowClicked", self.select_finding, args=["data"])
        self.candidate_grid.on("rowClicked", self.select_candidate, args=["data"])
        self.show_source()

    def publish_generated(self, state):
        """Explicitly replace generic review; retain same-input rule choices only."""
        import copy
        previous = self.controls.session
        binding = state.metadata.get("nicegui_generation_binding")
        keep_rules = binding is not None and previous.active_rule_binding == binding
        self.begin_load()
        self.state = state
        self.show_source()
        if keep_rules:
            session = self.controls.session
            for name in ("rules", "draft_rules", "rule_binding", "draft_rule_binding", "rules_stale", "draft_rules_stale"):
                setattr(session, name, copy.deepcopy(getattr(previous, name)))
            self.controls.refresh()

    def refresh_rules(self, session):
        binding = session.active_rule_binding
        self.rule_source_download.set_visibility(not self.state.source_suggestions)
        self.rule_rows = {f"{self.load_revision}:{session.revision}:{index}": index
                          for index, _ in enumerate(session.effective_rules)}
        self.rule_grid.options["rowData"] = [dict(
            row_id=key, apply=bool(item.get("apply")), editable=binding is not None,
            document=item["document"], annotator=item["annotator"], layer=item["layer"], offset=str(item["offset"]),
            source=item["source_code"], action=item["action"], target=item.get("replacement_code") or "",
            rule=item["concept_rule"]["rule_id"], override_allowed=bool(item["concept_rule"].get("override_policy")),
            override=bool(item.get("policy_overridden")))
            for key, index in self.rule_rows.items() for item in (session.effective_rules[index],)]
        self.rule_grid.update()
        self.rule_area.set_visibility(bool(session.effective_rules) or session.draft_rules is not None)
        self.rule_summary.set_text(f"{len(session.effective_rules)} rules · {len(session.rule_conflicts()[1])} manual conflicts"
                                   + (" · inputs changed; reapply or clear" if session.invalid_rules else "")
                                   + (" · imported rules are read-only" if binding is None else ""))

    def toggle_rule(self, event):
        import copy
        from .review import ReviewError
        try:
            data = event.args["data"]
            session = self.controls.session
            index = self.rule_rows.get(data["row_id"])
            if index is None or session.active_rule_binding is None or session.invalid_rules or type(data["apply"]) is not bool:
                raise ReviewError("This rule is read-only or from an older review. Reapply rules first.")
            rules = copy.deepcopy(session.effective_rules)
            item = rules[index]
            item["rule_reviewed_by_human"] = bool(item.get("rule_reviewed_by_human")) or item.get("apply") != data["apply"]
            item["apply"] = item["resolved"] = data["apply"]
            session.stage_rules(rules, session.active_rule_binding)
            self.controls.refresh()
        except (KeyError, TypeError, ReviewError) as error:
            self.ui.notify(str(error) if isinstance(error, ReviewError) else "Select a current rule Apply checkbox.", type="warning")

    def download_rule_source(self):
        if self.state.source_name is not None and not self.state.source_suggestions:
            from snomed_post_processing.sanitization.json_io import sanitization_suggestions_json_text
            keys = ("annotators", "id_prefix", "id_feature", "nicegui_generation_binding", "target_view")
            metadata = {key: self.state.metadata[key] for key in keys if key in self.state.metadata}
            self.ui.download.content(sanitization_suggestions_json_text([], metadata=metadata), "rule-only-suggestions.json")

    def clear_rules(self):
        if self.state.source_name is not None:
            self.controls.session.stage_rules([], self.controls.session.active_rule_binding)
            self.controls.refresh()

    def keep_manual_rules(self):
        session = self.controls.session
        safe, conflicts = session.rule_conflicts()
        if conflicts:
            session.stage_rules(safe, session.active_rule_binding)
            self.controls.refresh()

    def handle_key(self, event):
        if self.document_slides:
            self.ui.notify(event)

    def begin_load(self):
        self.load_revision += 1
        return self.load_revision

    def refresh_documents(self, session):
        self.finding_grid.options["rowData"] = [row for row in _finding_rows(self.state, session)
                                              if row["document"] == self.active_document]
        if hasattr(self, "rule_grid"):
            self.refresh_rules(session)
        for document, _, heading, toggle, tip in self.document_slides.values():
            reviewed = document in session.reviewed_documents
            pending = document in session.draft_reviewed
            effective = session.draft_reviewed.get(document, reviewed)
            action = "Unmark document reviewed" if effective else "Mark document reviewed"
            toggle.props["icon"] = "check_circle" if effective else "check_circle_outline"
            toggle.props["color"] = "amber-8" if pending else "green-7" if reviewed else "grey-6"
            toggle.props["aria-label"] = action
            toggle.set_enabled(self.state.source_name is not None)
            tip.set_text(action + (" (pending; Save choices)" if pending else ""))
            heading.classes(add="text-green-700 font-semibold" if reviewed else "",
                            remove="" if reviewed else "text-green-700 font-semibold")

    def clear_inspection(self):
        self.state.selected_finding_id = None
        self.state.selected_candidate_id = None
        self.candidate_grid.options["rowData"] = []
        # identity.set_text("Select a finding. Nothing is preselected.")
        # for label in (covered_text, finding_details, proposed, rationale, limits, evidence):
        for label in (self.covered_text, self.finding_details, self.proposed, self.rationale, self.evidence):
            label.set_text("")
        self.preview.set_text("No candidate selected. Inspecting a candidate stages no decision.")

    def change_document(self, value):
        entry = self.document_slides.get(value)
        if entry is None or entry[0] == self.active_document:
            return
        self.active_document = entry[0]
        self.workspace.move(entry[1])
        self.clear_inspection()
        self.controls.refresh()

    def show_source(self):
        self.review_context = ReviewContext.from_metadata(self.state.metadata)
        self.banner.set_text(
            "Suggestions and manual review. "
            + "No project/CAS is changed. Review is page-local until downloaded as JSON."
        )
        self.source.set_text(f"Source: {self.state.source_name or 'No suggestions loaded'}")
        saved_mode = self.state.metadata.get("target_view")
        mode = {"policy": "Policy rules", "release": "Active release"}.get(saved_mode, "not recorded") if isinstance(saved_mode, str) else "not recorded"
        self.scope.set_text(f"Saved annotator scope: {', '.join(self.state.source_annotators) or 'all annotators'} · Saved replacement mode: {mode}")
        total = len(self.state.source_suggestions)
        self.counts.set_text(f"{total} saved suggestions · {len(self.state.findings)} in artifact scope before grid filters · explicit review only · Save/export include all documents")
        # Reuse one workspace; clearing old slides must not delete its widgets.
        self.workspace.move(self.panel)
        self.documents.clear()
        self.document_slides.clear()
        self.active_document = None
        self.clear_inspection()
        self.controls.reset()
        names = list(dict.fromkeys(row.document for row in self.state.findings))
        with self.documents:
            for index, document in enumerate(names):
                token = f"{self.load_revision}:{index}"
                with self.ui.carousel_slide(name=token).classes("w-full min-w-0 px-12 pt-12") as slide:
                    with self.ui.row().classes("items-center gap-2 flex-nowrap"):
                        toggle = self.ui.button(icon="check_circle_outline", on_click=lambda _, document=document, source=self.state:
                                               self.controls.toggle_document(document, source)).props("flat round dense")
                        with toggle:
                            tip = self.ui.tooltip("Mark document reviewed")
                        heading = self.ui.label(document).classes("text-xl min-w-0 break-words")
                        heading.tooltip("Green means document review is saved; it does not imply every finding has a replacement.")
                self.document_slides[token] = (document, slide, heading, toggle, tip)
        self.documents.set_visibility(bool(names))
        self.empty.set_visibility(not names)
        if names:
            token = next(iter(self.document_slides))
            self.documents.set_value(token)
            self.change_document(token)

    def select_finding(self, event):
        previous_id = self.state.selected_finding_id
        try:
            row_id = event.args["data"]["row_id"]
            if not any(row.row_id == row_id and row.document == self.active_document for row in self.state.findings):
                raise ValueError("Finding is not in the visible document.")
            finding = self.state.select_finding(row_id)
        except (KeyError, TypeError, ValueError):
            self.ui.notify("Select a valid finding from this preview.", type="warning")
            return
        if finding.row_id == previous_id:
            return finding
        # identity.set_text(f"{finding.document} · {finding.annotator} · SCTID {finding.code}")
        text = finding.text
        backend_finding = self.state.source_suggestions[finding.suggestion_index].finding
        if not self.review_context.missing_documents((backend_finding,)):
            text = self.review_context.label(backend_finding)
        self.covered_text.set_text(text)
        self.finding_details.set_text(
            f"Source FSN: {finding.source_fsn}\n"
            f"Span: {finding.offset} · Layer: {finding.layer or 'not recorded'}"
        )
        self.proposed.set_text(f"Saved proposed SCTID: {finding.proposed_code or 'none'} (not automatically accepted)")
        self.rationale.set_text(finding.reason)
        # limits.set_text("Retrieval limits — candidate evidence may be incomplete:\n" + "\n".join(finding.retrieval_limits) if finding.retrieval_limits else "")
        self.candidate_grid.options["rowData"] = _candidate_rows(finding)
        self.preview.set_text("No candidate selected. Inspecting a candidate stages no decision.")
        self.evidence.set_text("")
        self.controls.refresh(update_grid=False)
        return finding

    def select_candidate(self, event):
        try:
            candidate = self.state.preview_candidate(event.args["data"]["row_id"])
        except (KeyError, TypeError, ValueError):
            self.ui.notify("Select a candidate from the current finding.", type="warning")
            return
        role = "Selectable candidate" if candidate.selectable else "Diagnostic context only — not selectable"
        self.preview.set_text(f"{role}: {candidate.code} — {candidate.fsn}. No decision staged.")
        self.evidence.set_text("\n".join(f"{key}: {value}" for key, value in candidate.details))
        self.controls.refresh(update_grid=False)
        return candidate

    def finding_menu(self, event):
        if self.select_finding(event) is not None:
            self.controls.open_menu(event)

    def candidate_menu(self, event):
        if self.select_candidate(event) is not None:
            self.controls.open_menu(event, candidates=True)

    async def load_upload(self, event):
        self.load_revision += 1
        revision = self.load_revision
        self.upload_status.set_text("Loading suggestions JSON; the previous preview remains visible until loading succeeds.")
        try:
            if event.file.size() > MAX_SUGGESTIONS_BYTES:
                raise SuggestionsPreviewError("Suggestions JSON exceeds the 50 MiB upload limit.")
            content = await event.file.read()
            from nicegui import run
            loaded = await run.io_bound(load_suggestions_preview, content, event.file.name)
        except SuggestionsPreviewError as error:
            if revision == self.load_revision:
                self.upload_status.set_text(f"{error} Current preview unchanged.")
                self.uploader.reset()
            return
        except OSError:
            if revision == self.load_revision:
                self.upload_status.set_text("Could not read the uploaded file. Current preview unchanged.")
                self.uploader.reset()
            return
        if revision != self.load_revision:
            return  # A newer upload superseded this load.
        self.state = loaded
        self.show_source()
        self.upload_status.set_text("Suggestions loaded. Previous review choices and flags reset; no decisions staged.")
        self.uploader.reset()
