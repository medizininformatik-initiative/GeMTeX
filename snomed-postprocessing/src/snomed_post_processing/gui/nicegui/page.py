"""Read-only NiceGUI workspace for demo data or uploaded suggestions JSON."""
from .demo import create_demo_state
from .suggestions import MAX_SUGGESTIONS_BYTES, SuggestionsPreviewError, load_suggestions_preview


def _finding_rows(state):
    keys = ("row_id", "suggestion_index", "document", "annotator", "code", "text", "status", "policy_issue", "ignored")
    return [{key: getattr(row, key) for key in keys} for row in state.findings]


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
        with ui.tab_panel(review):
            upload_controls = ui.row().classes("w-full items-start")
            upload_status = ui.label().classes("text-sm")
            counts = ui.label().classes("text-sm")
            with ui.row().classes("w-full items-start"):
                with ui.column().classes("w-full lg:w-7/12"):
                    ui.label("Findings — click a row to inspect").classes("text-lg")
                    finding_grid = ui.aggrid({
                        "columnDefs": [
                            {"field": "suggestion_index", "headerName": "Original index", "filter": "agNumberColumnFilter",
                             "headerTooltip": "Original zero-based suggestion_index in the uploaded JSON, before scope filtering."},
                            {"field": "document", "headerName": "Document"},
                            {"field": "annotator", "headerName": "Annotator"},
                            {"field": "code", "headerName": "Source SCTID"},
                            {"field": "text", "headerName": "Covered text", "flex": 2},
                            {"field": "status", "headerName": "Status"},
                            {"field": "policy_issue", "headerName": "Policy check"},
                            {"field": "ignored", "headerName": "Ignored"},
                        ],
                        "defaultColDef": {"sortable": True, "filter": "agTextColumnFilter", "floatingFilter": True, "resizable": True, "editable": False},
                        "rowData": [],
                        ":getRowId": "params => params.data.row_id",
                        "rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True},
                    }).classes("w-full h-80")
                with ui.column().classes("w-full lg:flex-1"):
                    ui.label("Selected finding").classes("text-lg")
                    identity = ui.label("Select a finding. Nothing is preselected.")
                    covered_text = ui.label().classes("whitespace-pre-wrap")
                    finding_details = ui.label().classes("text-sm whitespace-pre-wrap")
                    rationale = ui.label().classes("text-sm whitespace-pre-wrap")
                    limits = ui.label().classes("text-amber-900 whitespace-pre-wrap")
                    candidate_grid = ui.aggrid({
                        "columnDefs": [
                            {"field": "rank", "headerName": "Rank", "filter": "agNumberColumnFilter"},
                            {"field": "code", "headerName": "SCTID"},
                            {"field": "fsn", "headerName": "FSN", "flex": 2},
                            {"field": "score", "headerName": "Score", "filter": "agNumberColumnFilter"},
                            {"field": "role", "headerName": "Candidate role"},
                        ],
                        "defaultColDef": {"sortable": True, "filter": "agTextColumnFilter", "resizable": True, "editable": False},
                        "rowData": [],
                        ":getRowId": "params => params.data.row_id",
                        "rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True},
                    }).classes("w-full h-64")
                    preview = ui.label("Candidate clicks only preview; they do not approve anything.")
                    evidence = ui.label().classes("text-sm whitespace-pre-wrap")
                    ui.button("Use candidate").tooltip("Disabled until backend decision staging is connected.").disable()
            ui.label("Decision staging, reviewed flags, JSON export, ZIP write-back and deployment are not connected.")

            def show_source():
                banner.set_text(
                    ("Synthetic preview only. " if state.is_demo else "Read-only suggestions JSON preview. ")
                    + "No project/CAS is changed and no decisions are staged."
                )
                source.set_text(f"Source: {state.source_name}")
                saved_mode = state.metadata.get("target_view")
                mode = {"policy": "Policy rules", "release": "Active release"}.get(saved_mode, "not recorded") if isinstance(saved_mode, str) else "not recorded"
                scope.set_text(f"Saved annotator scope: {', '.join(state.source_annotators) or 'all annotators'} · Saved replacement mode: {mode}")
                total = len(state.findings) if state.is_demo else len(state.source_suggestions)
                counts.set_text(f"{total} saved suggestions · {len(state.findings)} in artifact scope before grid filters · read-only")
                finding_grid.options["rowData"] = _finding_rows(state)
                candidate_grid.options["rowData"] = []
                identity.set_text("Select a finding. Nothing is preselected.")
                for label in (covered_text, finding_details, rationale, limits, evidence):
                    label.set_text("")
                preview.set_text("No candidate selected. Inspecting a candidate stages no decision.")

            def select_finding(event):
                previous_id = state.selected_finding_id
                try:
                    finding = state.select_finding(event.args["data"]["row_id"])
                except (KeyError, TypeError, ValueError):
                    ui.notify("Select a valid finding from this preview.", type="warning")
                    return
                if finding.row_id == previous_id:
                    return
                identity.set_text(f"{finding.document} · {finding.annotator} · SCTID {finding.code}")
                covered_text.set_text(finding.text)
                finding_details.set_text(
                    f"Original index: {finding.suggestion_index} · Layer: {finding.layer or 'not recorded'} · Span: {finding.offset}\n"
                    f"Source FSN: {finding.source_fsn}\nSaved candidate count: {finding.candidate_count} · Ignored: {finding.ignored}\n"
                    f"Saved proposed SCTID: {finding.proposed_code or 'none'} (not selected or approved)"
                )
                rationale.set_text(finding.reason)
                limits.set_text("Retrieval limits — candidate evidence may be incomplete:\n" + "\n".join(finding.retrieval_limits) if finding.retrieval_limits else "")
                candidate_grid.options["rowData"] = _candidate_rows(finding)
                preview.set_text("No candidate selected. Inspecting a candidate stages no decision.")
                evidence.set_text("")

            def select_candidate(event):
                try:
                    candidate = state.preview_candidate(event.args["data"]["row_id"])
                except (KeyError, TypeError, ValueError):
                    ui.notify("Select a candidate from the current finding.", type="warning")
                    return
                role = "Selectable candidate" if candidate.selectable else "Diagnostic context only — not selectable"
                preview.set_text(f"{role}: {candidate.code} — {candidate.fsn}. No decision staged.")
                evidence.set_text("\n".join(f"{key}: {value}" for key, value in candidate.details))

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
                upload_status.set_text("Suggestions loaded for this page only. No decisions staged.")
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
            # Request row data only; unrestricted AG Grid events contain cycles.
            finding_grid.on("rowClicked", select_finding, args=["data"])
            candidate_grid.on("rowClicked", select_candidate, args=["data"])
            show_source()
