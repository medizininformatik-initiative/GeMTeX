"""First NiceGUI workspace: synthetic, read-only, and isolated per page."""
from dataclasses import asdict

from snomed_post_processing.gui.nicegui.demo import create_demo_state


def build_page(ui) -> None:
    """Build once per page request; callbacks update mounted elements in place."""
    state = create_demo_state()
    with ui.header():
        ui.label("SNOMED Postprocessing — NiceGUI prototype").classes("text-xl")
    ui.label(
        "Synthetic preview only. No project is loaded, no decisions are staged, and no files are written."
    ).classes("text-amber-900 bg-amber-100 p-3 rounded w-full")

    with ui.expansion("Project and processing scope (not connected)").classes("w-full"):
        ui.label("Project ZIP, HDF5, annotation layers and shared annotator scope will be connected here.")
        ui.label("The grid filters below affect display only; they are not annotator processing scope.")

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
            ui.label("3 artificial findings · 2 annotators · all rows read-only").classes("text-sm")
            with ui.row().classes("w-full items-start"):
                with ui.column().classes("w-full lg:w-7/12"):
                    ui.label("Findings — click a row to inspect").classes("text-lg")
                    finding_grid = ui.aggrid({
                        "columnDefs": [
                            {"field": "document", "headerName": "Document"},
                            {"field": "annotator", "headerName": "Annotator"},
                            {"field": "code", "headerName": "Source SCTID"},
                            {"field": "text", "headerName": "Covered text", "flex": 2},
                        ],
                        "defaultColDef": {"sortable": True, "filter": "agTextColumnFilter", "floatingFilter": True, "resizable": True, "editable": False},
                        "rowData": [
                            {key: getattr(row, key) for key in ("row_id", "document", "annotator", "code", "text")}
                            for row in state.findings
                        ],
                        ":getRowId": "params => params.data.row_id",
                        "rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True},
                    }).classes("w-full h-80")
                with ui.column().classes("w-full lg:flex-1"):
                    ui.label("Selected finding").classes("text-lg")
                    identity = ui.label("Select a finding. Nothing is preselected.")
                    covered_text = ui.label().classes("whitespace-pre-wrap")
                    rationale = ui.label().classes("text-sm")
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
                        ":getRowId": "params => params.data.code",
                        "rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True},
                    }).classes("w-full h-64")
                    preview = ui.label("Candidate clicks only preview; they do not approve anything.")
                    ui.button("Use candidate").tooltip("Disabled until backend decision staging is connected.").disable()
            ui.label("Decision staging, reviewed flags, JSON export, ZIP write-back and deployment are not connected.")

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
                rationale.set_text(finding.reason)
                candidate_grid.options["rowData"] = [
                    {**asdict(candidate), "role": "Selectable" if candidate.selectable else "Context only — not selectable"}
                    for candidate in finding.candidates
                ]
                preview.set_text("No candidate selected. Inspecting a candidate stages no decision.")

            def select_candidate(event):
                try:
                    candidate = state.preview_candidate(event.args["data"]["code"])
                except (KeyError, TypeError, ValueError):
                    ui.notify("Select a candidate from the current finding.", type="warning")
                    return
                role = "Selectable candidate" if candidate.selectable else "Diagnostic context only — not selectable"
                preview.set_text(f"{role}: {candidate.code} — {candidate.fsn}. No decision staged.")

            # Serialize row data only: unrestricted AG Grid events contain cycles.
            finding_grid.on("rowClicked", select_finding, args=["data"])
            candidate_grid.on("rowClicked", select_candidate, args=["data"])
