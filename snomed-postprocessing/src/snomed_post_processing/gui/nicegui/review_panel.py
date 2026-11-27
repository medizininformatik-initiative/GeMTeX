"""Per-page review panel: inspection, document navigation and review JSON controls."""
import hashlib

from snomed_post_processing.review_context import ReviewContext

from .state import PreviewState
from .tables import resizable_table
from .review_ui import ReviewControls


def _automatic_condition_label(item, *, include_target=True):
    kind = (item.get("automatic_condition") or {}).get("kind") if isinstance(item, dict) else None
    label = {"historical_association": "Historical", "bm25_gap": "BM25 gap"}.get(kind, "")
    target = item.get("replacement_code") if isinstance(item, dict) else None
    return f"{label} → {target}" if label and include_target and target else label


def _update_grid_rows(grid, rows):
    """Update an initialized AG Grid without replacing its sort/filter model."""
    previous = list(grid.options.get("rowData", ()))
    if not previous:
        grid.options["rowData"] = rows
        grid.update()
        return
    # NiceGUI wraps options in deeply observable dictionaries. A regular
    # assignment rebuilds the whole client grid and clears its sort/filter model.
    # Keep the server snapshot in sync without firing that observer; the explicit
    # AG Grid transaction below performs the client-side update.
    dict.__setitem__(grid.options, "rowData", rows)
    previous_by_id = {row["row_id"]: row for row in previous}
    current_by_id = {row["row_id"]: row for row in rows}
    def content(row):
        return {key: value for key, value in row.items() if key != "current"}

    transaction = {
        "remove": [row for row_id, row in previous_by_id.items() if row_id not in current_by_id],
        "add": [row for row_id, row in current_by_id.items() if row_id not in previous_by_id],
        "update": [row for row_id, row in current_by_id.items()
                   if row_id in previous_by_id and content(row) != content(previous_by_id[row_id])],
    }
    if any(transaction.values()):
        grid.run_grid_method("applyTransaction", transaction)


async def _displayed_row_ids(grid):
    """Return row IDs in the exact order currently displayed by AG Grid."""
    if getattr(grid.client, "has_socket_connection", False):
        try:
            row_ids = await grid.client.run_javascript(f'''
                const api = getElement({grid.id}).api;
                const rowIds = [];
                for (let index = 0; index < api.getDisplayedRowCount(); index++) {{
                    const rowId = api.getDisplayedRowAtIndex(index)?.data?.row_id;
                    if (typeof rowId === 'string') rowIds.push(rowId);
                }}
                return rowIds;
            ''')
            if isinstance(row_ids, list) and all(isinstance(row_id, str) for row_id in row_ids):
                return row_ids
        except (AttributeError, TypeError, RuntimeError, TimeoutError):
            pass
    rows = await grid.get_client_data(method="filtered_sorted")
    return [row["row_id"] for row in rows if isinstance(row, dict) and isinstance(row.get("row_id"), str)]


def _finding_rows(state, session=None):
    keys = ("row_id", "suggestion_index", "document", "annotator", "code", "text", "status", "policy_issue", "ignored")
    rows = [{key: getattr(row, key) for key in keys} for row in state.findings]
    if session is not None:
        for values, row in zip(rows, state.findings):
            values["review"] = session.status(row)
            values["automatic_condition"] = _automatic_condition_label(session.saved.get(row.suggestion_index, {}))
            values["document_reviewed"] = row.document in session.reviewed_documents
    return rows


def _candidate_rows(finding, session=None, inspected_id=None):
    chosen_id, chosen_label = None, ""
    if session is not None and not session.protected(finding):
        draft = session.drafts.get(finding.row_id)
        saved = session.saved.get(finding.suggestion_index, {})
        if draft is not None:
            chosen_id = draft.candidate_id if draft.action == "replace" else None
            chosen_label = "Chosen — pending Save"
        elif saved.get("apply") and saved.get("valid_choice"):
            ordinal = saved.get("manual_candidate_ordinal")
            if type(ordinal) is int and 0 <= ordinal < len(finding.candidates):
                chosen_id = finding.candidates[ordinal].row_id
            else:
                matches = [item for item in finding.candidates
                           if item.selectable and item.code == saved.get("replacement_code")]
                # Legacy decisions without exact evidence must not color duplicate-code rows alike.
                chosen_id = matches[0].row_id if len(matches) == 1 else None
            chosen_label = "Chosen — saved"
    rows = []
    for item in finding.candidates:
        chosen = item.selectable and item.row_id == chosen_id
        inspected = item.row_id == inspected_id
        proposed = bool(item.selectable and finding.proposed_code and item.code == finding.proposed_code)
        label = (chosen_label if chosen else "Inspecting only" if inspected
                 else "Saved proposal — not accepted" if proposed else "Not chosen")
        if chosen and inspected:
            label += " · inspecting"
        if proposed and (chosen or inspected):
            label += " · saved proposal"
        rows.append({"row_id": item.row_id, "rank": item.rank, "code": item.code, "fsn": item.fsn,
                     "score": item.score, "role": "Selectable" if item.selectable else "Context only — not selectable",
                     "chosen": chosen, "inspected": inspected, "proposed": proposed, "selection": label})
    return rows


class ReviewPanelControls:
    def __init__(self, ui, panel, *, provenance, data_dir=None):
        self.ui, self.panel = ui, panel
        self.provenance = provenance
        self.data_dir = data_dir or "data"
        self.state = PreviewState()
        self.review_context = ReviewContext()
        self.load_revision = 0
        self.active_document = None
        self.document_slides = {}
        self._keyboard_busy = False
        self._finding_grid_binding = None
        self.deployment = None
        self.keyboard = ui.keyboard(on_key=self.handle_key, repeating=False)
        self.keyboard.active = False
        add_head_html = getattr(ui, "add_head_html", None)
        if add_head_html is not None:
            add_head_html("""
                <script>
                if (!window.snomedReviewSpaceGuard) {
                    window.snomedReviewSpaceGuard = true;
                    document.addEventListener('keydown', event => {
                        if (event.code !== 'Space' || event.defaultPrevented || event.altKey ||
                            event.ctrlKey || event.metaKey || event.shiftKey) return;
                        const target = event.target;
                        if (!(target instanceof Element) || target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement ||
                            target instanceof HTMLSelectElement || target.isContentEditable ||
                            target.closest('button, a, [role="button"]')) return;
                        event.preventDefault();
                    }, true);
                }
                </script>
            """)

        with ui.expansion("Restore reviewed decisions", value=False).classes("w-full") as self.restore_review:
            self.restore_review_note = ui.label(
                "Restore decisions after loading the matching suggestions in tab 2. Import replaces the current review; no CAS is changed."
            ).classes("text-sm")
        ui.label("Restore suggestions in tab 2, then use Load in review (replaces review). Reviewed decisions can be restored below after their matching suggestions.").classes("text-sm")
        self.counts = ui.label().classes("text-sm")
        self.conditions = ui.column().classes("w-full min-w-0")
        self.document_navigator = ui.column().classes("w-full min-w-0")
        # Do not keep-alive slides: cached panels retain stale DOM for the moved grid.
        self.documents = ui.carousel(arrows=False, navigation=False).props(
            "height=auto"
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
                        {"field": "review", "headerName": "Review state", "minWidth": 250},
                        {"field": "automatic_condition", "headerName": "Automatic condition", "minWidth": 210},
                        {"field": "ignored", "headerName": "Ignored", "maxWidth": 100},
                    ],
                    "defaultColDef": {"sortable": True, "filter": "agTextColumnFilter", "floatingFilter": True, "resizable": True, "editable": False},
                    "rowData": [],
                    ":getRowId": "params => params.data.row_id",
                    "rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True},
                }).classes("review-finding-grid w-full h-80 overflow-auto overscroll-contain")
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
                        {"field": "selection", "headerName": "Review selection", "minWidth": 240, "tooltipField": "selection"},
                    ],
                    "defaultColDef": {"sortable": True, "filter": "agTextColumnFilter", "resizable": True, "editable": False},
                    "rowData": [],
                    ":getRowId": "params => params.data.row_id",
                    ":getRowStyle": """params => ({
                        backgroundColor: params.data.chosen ? '#dcfce7' : params.data.inspected ? '#dbeafe' : params.data.proposed ? '#fef9c3' : 'transparent',
                        color: params.data.chosen ? '#14532d' : params.data.inspected ? '#1e3a8a' : params.data.proposed ? '#713f12' : 'inherit',
                        boxShadow: params.data.inspected ? 'inset 4px 0 0 #2563eb' : 'none'
                    })""",
                }).classes("review-candidate-grid w-full h-64 overflow-auto overscroll-contain")
                ui.label("Pale yellow = saved proposal, not accepted; blue = inspecting only; green = chosen replacement (pending or saved, see Review selection). A blue edge marks inspection of a green row. Clicking never applies a replacement.").classes("text-sm")
                self.preview = ui.label("Candidate clicks only preview; they do not approve anything.")
                self.evidence = ui.label().classes("text-sm whitespace-pre-wrap")
                self.controls = ReviewControls(ui, lambda: self.state, lambda: self.load_revision,
                                               self.begin_load, self.refresh_documents,
                                               conditions_container=self.conditions,
                                               restore_container=self.restore_review,
                                               data_dir=self.data_dir)
        ui.label("Sanitized-ZIP download and explicit new-project upload are combined under INCEpTION deployment; preserved SQLite CAS also retains its offline-package workflow.")
        with ui.expansion("Explicit concept rule decisions", value=False).classes("w-full") as self.rule_area:
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
        with self.document_navigator:
            ui.label("Documents in loaded artifact — filter and click to open").classes("text-lg")
            self.document_position = ui.label().classes("text-sm")
            ui.label("A/D: previous/next finding · Space: accept a unique saved suggestion · W/S: previous/next document (current table filters/order; no wrap). Typing and arrow keys are unchanged.").classes("text-sm")
            ui.label("Tables: drag the lower-right corner to resize height; drag column borders to resize width.").classes("text-sm")
            self.document_grid = ui.aggrid({
                "columnDefs": [
                    {"field": "document", "headerName": "Document", "flex": 2, "minWidth": 240},
                    {"field": "findings", "headerName": "Findings", "width": 110, "filter": "agNumberColumnFilter"},
                    {"field": "review", "headerName": "Saved document review", "minWidth": 200},
                    {"field": "automatic", "headerName": "Automatic conditions", "minWidth": 190},
                    {"field": "pending", "headerName": "Pending edits", "width": 150, "filter": "agNumberColumnFilter",
                     "headerTooltip": "Pending candidate/action choices plus a pending document-review flag. Concept-rule edits are shown separately below."},
                ],
                "defaultColDef": {"sortable": True, "filter": "agTextColumnFilter", "floatingFilter": True,
                                  "resizable": True, "editable": False},
                "rowData": [], ":getRowId": "params => params.data.row_id",
                "rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True},
            }).classes("review-document-grid w-full h-80 overflow-auto overscroll-contain")
            self.document_grid.on("rowClicked", self.select_document, args=["data", "rowIndex"])
        for grid in (self.finding_grid, self.candidate_grid, self.rule_grid):
            resizable_table(grid)
        resizable_table(self.document_grid, min_height=320)
        self.documents.on_value_change(lambda event: self.change_document(event.value))
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
        self.rule_rows = {
            f"{self.load_revision}:{hashlib.sha256(repr((item.get('document'), item.get('annotator'), item.get('layer'), item.get('offset'), item.get('source_code'), (item.get('concept_rule') or {}).get('rule_id'), index)).encode()).hexdigest()[:16]}": index
            for index, item in enumerate(session.effective_rules)
        }
        rows = [dict(
            row_id=key, apply=bool(item.get("apply")), editable=binding is not None,
            document=item["document"], annotator=item["annotator"], layer=item["layer"], offset=str(item["offset"]),
            source=item["source_code"], action=item["action"], target=item.get("replacement_code") or "",
            rule=item["concept_rule"]["rule_id"], override_allowed=bool(item["concept_rule"].get("override_policy")),
            override=bool(item.get("policy_overridden")))
            for key, index in self.rule_rows.items() for item in (session.effective_rules[index],)]
        _update_grid_rows(self.rule_grid, rows)
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
            keys = ("annotators", "id_prefix", "id_feature", "nicegui_generation_binding", "target_view", "store_scope", "annotation_source_file")
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

    async def handle_key(self, event):
        from types import SimpleNamespace

        key = event.key.name
        if (not self.keyboard.active or not self.document_slides or self._keyboard_busy
                or not event.action.keydown or event.action.repeat or any(event.modifiers)
                or key not in ("a", "d", "w", "s", "space", "Space", " ")):
            return
        self._keyboard_busy = True
        try:
            if key in ("space", "Space", " "):
                row_id = self.state.selected_finding_id
                if row_id is not None and self.controls.session.proposed_candidate(row_id) is not None:
                    self.controls.command("accept")
                return
            documents = key in ("w", "s")
            step = -1 if key in ("a", "w") else 1
            grid = self.document_grid if documents else self.finding_grid
            state = self.state
            stamp = (self.load_revision, self.active_document, self.state.selected_finding_id)
            # Use displayed order, but trust only identities from the current artifact.
            try:
                displayed_ids = await _displayed_row_ids(grid)
            except (TimeoutError, RuntimeError):
                # A closing client/unavailable grid leaves inspection untouched.
                return
            if (not self.keyboard.active or self.state is not state or stamp !=
                    (self.load_revision, self.active_document, self.state.selected_finding_id)):
                return
            allowed = (set(self.document_slides) if documents else
                       {row.row_id for row in self.state.findings if row.document == self.active_document})
            ids = list(dict.fromkeys(row_id for row_id in displayed_ids if row_id in allowed))
            current = (next((token for token, entry in self.document_slides.items()
                             if entry[0] == self.active_document), None)
                       if documents else self.state.selected_finding_id)
            index = ids.index(current) + step if current in ids else (0 if step > 0 else len(ids) - 1)
            if not 0 <= index < len(ids):
                return
            target = SimpleNamespace(args={"data": {"row_id": ids[index]}})
            if documents:
                self.select_document(target)
            else:
                self.select_finding(target)
                grid.run_row_method(ids[index], "setSelected", True, True)
            grid.run_grid_method("ensureIndexVisible", index)
        finally:
            self._keyboard_busy = False

    def begin_load(self):
        self.load_revision += 1
        return self.load_revision

    def refresh_documents(self, session):
        self.refresh_document_overview(session)
        self.refresh_candidates()
        rows = [row for row in _finding_rows(self.state, session) if row["document"] == self.active_document]
        binding = (self.state, self.active_document)
        if binding == self._finding_grid_binding:
            _update_grid_rows(self.finding_grid, rows)
        else:
            self.finding_grid.options["rowData"] = rows
            self._finding_grid_binding = binding
        if hasattr(self, "rule_grid"):
            self.refresh_rules(session)
        if self.deployment is not None:
            self.deployment.review_changed()
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

    def refresh_document_overview(self, session):
        automatic = {}
        for item in session.saved.values():
            label = _automatic_condition_label(item, include_target=False)
            if label:
                automatic.setdefault(item.get("document"), set()).add(label)
        automatically_reviewed = set(session.imported_metadata.get("automatic_reviewed_documents", []))
        rows = {document: dict(
                    row_id=token, document=document, findings=0,
                    review=("Automatically reviewed" if document in automatically_reviewed
                            else "Reviewed" if document in session.reviewed_documents else "Not marked"),
                    automatic=", ".join(sorted(automatic.get(document, ()))),
                    pending=int(document in session.draft_reviewed), current=document == self.active_document,
                ) for token, (document, *_) in self.document_slides.items()}
        for finding in self.state.findings:
            if finding.document in rows:
                rows[finding.document]["findings"] += 1
                rows[finding.document]["pending"] += int(finding.row_id in session.drafts)
        _update_grid_rows(self.document_grid, list(rows.values()))
        names = list(rows)
        position = names.index(self.active_document) + 1 if self.active_document in rows else 0
        self.document_position.set_text(f"{len(names)} documents · Current: {position}/{len(names)}"
                                        + (f" · {self.active_document}" if position else ""))
        self.document_navigator.set_visibility(bool(names))

    def select_document(self, event):
        try:
            token = event.args["data"]["row_id"]
            if token not in self.document_slides:
                return
            row_index = event.args.get("rowIndex")
        except (AttributeError, KeyError, TypeError):
            return
        self.documents.set_value(token)
        self.change_document(token)
        # Keep the clicked row visible after the document workspace changes.
        if type(row_index) is int and row_index >= 0:
            self.document_grid.run_grid_method("ensureIndexVisible", row_index)

    def refresh_candidates(self, *, preserve_view=True):
        finding = self.state.selected_finding
        rows = _candidate_rows(finding, self.controls.session, self.state.selected_candidate_id) if finding else []
        if preserve_view:
            _update_grid_rows(self.candidate_grid, rows)
        else:
            self.candidate_grid.options["rowData"] = rows
            self.candidate_grid.update()

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
        self.document_grid.run_row_method(value, "setSelected", True, True)
        self.workspace.move(entry[1])
        self.clear_inspection()
        self.controls.refresh()

    def show_source(self):
        self.review_context = ReviewContext.from_metadata(self.state.metadata)
        saved_mode = self.state.metadata.get("target_view")
        mode = {"policy": "Policy rules", "release": "Active release"}.get(saved_mode, "not recorded") if isinstance(saved_mode, str) else "not recorded"
        self.provenance.set_text(
            f"Source: {self.state.source_name or 'No suggestions loaded'} · "
            f"Saved annotator scope: {', '.join(self.state.source_annotators) or 'all annotators'} · "
            f"Saved replacement mode: {mode}"
        )
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
        self.refresh_candidates(preserve_view=False)
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
        self.refresh_candidates()
        self.controls.refresh(update_grid=False)
        return candidate

    def finding_menu(self, event):
        if self.select_finding(event) is not None:
            self.controls.open_menu(event)

    def candidate_menu(self, event):
        if self.select_candidate(event) is not None:
            self.controls.open_menu(event, candidates=True)
