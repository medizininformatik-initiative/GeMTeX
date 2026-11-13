"""NiceGUI suggestions inspection and explicit manual review; no CAS write-back."""
from .demo import create_demo_state
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


def build_page(ui) -> None:
    """Build once per visitor; imports replace state only after successful parsing."""
    state = create_demo_state()
    load_revision = 0
    active_document = None
    document_slides = {}

    def refresh_documents(session):
        finding_grid.options["rowData"] = [row for row in _finding_rows(state, session)
                                          if row["document"] == active_document]
        for document, _, heading in document_slides.values():
            reviewed = document in session.reviewed_documents
            heading.classes(add="text-green-700 font-semibold" if reviewed else "",
                            remove="" if reviewed else "text-green-700 font-semibold")

    def begin_load():
        nonlocal load_revision
        load_revision += 1
        return load_revision

    with ui.header():
        ui.label("SNOMED Postprocessing — NiceGUI prototype").classes("text-xl")
    banner = ui.label().classes("text-amber-900 bg-amber-100 p-3 rounded w-full")
    source = ui.label().classes("text-sm")
    scope = ui.label().classes("text-sm")
    with ui.expansion("Project and processing scope (not connected)").classes("w-full"):
        ui.label("Project ZIP, HDF5 and shared processing controls are not connected.")
        ui.label("Uploaded suggestions inherit their saved annotator scope; it cannot be broadened here.")
        ui.label("Saved generation settings are displayed as provenance, not revalidated against a project or HDF5.")
        ui.label("Grid filters affect display only, not the source artifact or its annotator scope.")

    with ui.tabs().classes("w-full") as tabs:
        check = ui.tab("check", label="1. Check policy")
        suggest = ui.tab("suggest", label="2. Suggest")
        review = ui.tab("review", label="3. Review & apply")
    with ui.tab_panels(tabs, value=review).props("keep-alive").classes("w-full"):
        with ui.tab_panel(check):
            ui.label("Policy checking is not connected in this prototype.")
            ui.button("Check policy").disable()
        with ui.tab_panel(suggest):
            ui.label("Rules and suggestion generation are not connected in this prototype.")
            ui.button("Generate suggestions").disable()
        with ui.tab_panel(review) as review_panel:
            upload_controls = ui.row().classes("w-full items-start")
            upload_status = ui.label().classes("text-sm")
            counts = ui.label().classes("text-sm")
            documents = ui.carousel(arrows=True, navigation=True).props(
                "height=auto navigation-position=top control-color=primary keep-alive"
            ).classes("w-full")
            empty = ui.label("No findings in the current artifact scope.")
            with ui.column().classes("w-full min-w-0 gap-4") as workspace:
                with ui.column().classes("w-full min-w-0"):
                    ui.label("Findings — click a row to inspect").classes("text-lg")
                    finding_grid = ui.aggrid({
                        "columnDefs": [
                            {"field": "annotator", "headerName": "Annotator"},
                            {"field": "code", "headerName": "Source SCTID"},
                            {"field": "text", "headerName": "Covered text", "flex": 2, "minWidth": 400},
                            {"field": "status", "headerName": "Status"},
                            {"field": "policy_issue", "headerName": "Policy check"},
                            {"field": "review", "headerName": "Manual review"},
                            {"field": "ignored", "headerName": "Ignored"},
                        ],
                        "defaultColDef": {"sortable": True, "filter": "agTextColumnFilter", "floatingFilter": True, "resizable": True, "editable": False},
                        "rowData": [],
                        ":getRowId": "params => params.data.row_id",
                        "rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True},
                    }).classes("w-full h-80 overflow-auto overscroll-contain")
                with ui.column().classes("w-full min-w-0"):
                    ui.label("Selected finding").classes("text-lg")
                    identity = ui.label("Select a finding. Nothing is preselected.")
                    with ui.element("div").classes("grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 w-full min-w-0"):
                        with ui.column().classes("w-full min-w-0 gap-1"):
                            ui.label("Annotation").classes("text-sm font-medium")
                            covered_text = ui.label().classes("whitespace-pre-wrap break-words")
                            finding_details = ui.label().classes("text-sm whitespace-pre-wrap break-words")
                        with ui.column().classes("w-full min-w-0 gap-1"):
                            ui.label("Suggestion rationale & retrieval").classes("text-sm font-medium")
                            proposed = ui.label().classes("text-sm whitespace-pre-wrap break-words")
                            rationale = ui.label().classes("text-sm whitespace-pre-wrap break-words")
                            limits = ui.label().classes("text-amber-900 whitespace-pre-wrap break-words")
                    candidate_grid = ui.aggrid({
                        "columnDefs": [
                            {"field": "rank", "headerName": "Rank", "width": 80, "filter": "agNumberColumnFilter"},
                            {"field": "code", "headerName": "SCTID", "width": 180},
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
                    preview = ui.label("Candidate clicks only preview; they do not approve anything.")
                    evidence = ui.label().classes("text-sm whitespace-pre-wrap")
                    controls = ReviewControls(ui, lambda: state, lambda: load_revision, begin_load, refresh_documents)
            ui.label("Review JSON only. Generation, rules/conditions, ZIP write-back and deployment remain disconnected.")

            def clear_inspection():
                state.selected_finding_id = None
                state.selected_candidate_id = None
                candidate_grid.options["rowData"] = []
                identity.set_text("Select a finding. Nothing is preselected.")
                for label in (covered_text, finding_details, proposed, rationale, limits, evidence):
                    label.set_text("")
                preview.set_text("No candidate selected. Inspecting a candidate stages no decision.")

            def change_document(value):
                nonlocal active_document
                entry = document_slides.get(value)
                if entry is None or entry[0] == active_document:
                    return
                active_document = entry[0]
                workspace.move(entry[1])
                clear_inspection()
                controls.refresh()

            documents.on_value_change(lambda event: change_document(event.value))

            def show_source():
                nonlocal active_document
                banner.set_text(
                    ("Synthetic preview only — load suggestions JSON to enable review. " if state.is_demo else "Suggestions and manual review. ")
                    + "No project/CAS is changed. Review is page-local until downloaded as JSON."
                )
                source.set_text(f"Source: {state.source_name}")
                saved_mode = state.metadata.get("target_view")
                mode = {"policy": "Policy rules", "release": "Active release"}.get(saved_mode, "not recorded") if isinstance(saved_mode, str) else "not recorded"
                scope.set_text(f"Saved annotator scope: {', '.join(state.source_annotators) or 'all annotators'} · Saved replacement mode: {mode}")
                total = len(state.findings) if state.is_demo else len(state.source_suggestions)
                counts.set_text(f"{total} saved suggestions · {len(state.findings)} in artifact scope before grid filters · explicit review only · Save/export include all documents")
                # Reuse one workspace; clearing old slides must not delete its widgets.
                workspace.move(review_panel)
                documents.clear()
                document_slides.clear()
                active_document = None
                clear_inspection()
                controls.reset()
                names = list(dict.fromkeys(row.document for row in state.findings))
                with documents:
                    for index, document in enumerate(names):
                        token = f"{load_revision}:{index}"
                        with ui.carousel_slide(name=token).classes("w-full min-w-0 px-12 pt-12") as slide:
                            heading = ui.label(document).classes("text-xl")
                            heading.tooltip("Green means document review is saved; it does not imply every finding has a replacement.")
                        document_slides[token] = (document, slide, heading)
                documents.set_visibility(bool(names))
                empty.set_visibility(not names)
                if names:
                    token = next(iter(document_slides))
                    documents.set_value(token)
                    change_document(token)

            def select_finding(event):
                previous_id = state.selected_finding_id
                try:
                    row_id = event.args["data"]["row_id"]
                    if not any(row.row_id == row_id and row.document == active_document for row in state.findings):
                        raise ValueError("Finding is not in the visible document.")
                    finding = state.select_finding(row_id)
                except (KeyError, TypeError, ValueError):
                    ui.notify("Select a valid finding from this preview.", type="warning")
                    return
                if finding.row_id == previous_id:
                    return finding
                identity.set_text(f"{finding.document} · {finding.annotator} · SCTID {finding.code}")
                covered_text.set_text(finding.text)
                finding_details.set_text(
                    f"Layer: {finding.layer or 'not recorded'} · Span: {finding.offset}\n"
                    f"Source FSN: {finding.source_fsn}\nIgnored: {finding.ignored}"
                )
                proposed.set_text(f"Saved proposed SCTID: {finding.proposed_code or 'none'} (not automatically accepted)")
                rationale.set_text(finding.reason)
                limits.set_text("Retrieval limits — candidate evidence may be incomplete:\n" + "\n".join(finding.retrieval_limits) if finding.retrieval_limits else "")
                candidate_grid.options["rowData"] = _candidate_rows(finding)
                preview.set_text("No candidate selected. Inspecting a candidate stages no decision.")
                evidence.set_text("")
                controls.refresh(update_grid=False)
                return finding

            def select_candidate(event):
                try:
                    candidate = state.preview_candidate(event.args["data"]["row_id"])
                except (KeyError, TypeError, ValueError):
                    ui.notify("Select a candidate from the current finding.", type="warning")
                    return
                role = "Selectable candidate" if candidate.selectable else "Diagnostic context only — not selectable"
                preview.set_text(f"{role}: {candidate.code} — {candidate.fsn}. No decision staged.")
                evidence.set_text("\n".join(f"{key}: {value}" for key, value in candidate.details))
                controls.refresh(update_grid=False)
                return candidate

            def finding_menu(event):
                if select_finding(event) is not None:
                    controls.open_menu(event)

            def candidate_menu(event):
                if select_candidate(event) is not None:
                    controls.open_menu(event, candidates=True)

            async def load_upload(event):
                nonlocal state, load_revision
                load_revision += 1
                revision = load_revision
                upload_status.set_text("Loading suggestions JSON; the previous preview remains visible until loading succeeds.")
                try:
                    if event.file.size() > MAX_SUGGESTIONS_BYTES:
                        raise SuggestionsPreviewError("Suggestions JSON exceeds the 50 MiB upload limit.")
                    content = await event.file.read()
                    from nicegui import run
                    loaded = await run.io_bound(load_suggestions_preview, content, event.file.name)
                except SuggestionsPreviewError as error:
                    if revision == load_revision:
                        upload_status.set_text(f"{error} Current preview unchanged.")
                        uploader.reset()
                    return
                except OSError:
                    if revision == load_revision:
                        upload_status.set_text("Could not read the uploaded file. Current preview unchanged.")
                        uploader.reset()
                    return
                if revision != load_revision:
                    return  # A newer upload or explicit demo reset superseded this load.
                state = loaded
                show_source()
                upload_status.set_text("Suggestions loaded. Previous review choices and flags reset; no decisions staged.")
                uploader.reset()

            def use_demo():
                nonlocal state, load_revision
                load_revision += 1
                state = create_demo_state()
                show_source()
                upload_status.set_text("Synthetic demo restored; uploaded data is no longer the active preview.")
                uploader.reset()

            with upload_controls:
                uploader = ui.upload(label="Load suggestions JSON", on_upload=load_upload,
                                     auto_upload=True, multiple=False, max_file_size=MAX_SUGGESTIONS_BYTES,
                                     on_rejected=lambda: upload_status.set_text("Upload rejected. Choose one JSON file up to 50 MiB; current preview unchanged.")) \
                    .props("accept=.json").classes("max-w-full")
                ui.button("Use synthetic demo", on_click=use_demo).tooltip("Replace this page's preview with artificial data; no files are changed.")
            # Native DOM right-clicks provide coordinates and immutable rendered row IDs;
            # AG Grid's serialized cellContextMenu event omits pointer coordinates.
            context_handler = """event => {
                const row = event.target.closest('.ag-row[row-id]');
                if (!row || event.shiftKey) return;
                event.preventDefault();
                emit({data: {row_id: row.getAttribute('row-id')}, clientX: event.clientX, clientY: event.clientY});
            }"""
            finding_grid.on("contextmenu", finding_menu, js_handler=context_handler)
            candidate_grid.on("contextmenu", candidate_menu, js_handler=context_handler)
            # Request row data only; unrestricted AG Grid events contain cycles.
            finding_grid.on("rowClicked", select_finding, args=["data"])
            candidate_grid.on("rowClicked", select_candidate, args=["data"])
            show_source()
