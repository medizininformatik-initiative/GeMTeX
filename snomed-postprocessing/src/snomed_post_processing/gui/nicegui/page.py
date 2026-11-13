"""NiceGUI page shell and workflow tab composition; no CAS write-back."""
from .policy_ui import PolicyCheckControls
from .review_panel import ReviewPanelControls
from .suggestion_ui import SuggestionControls


def build_page(ui, events) -> None:
    """Build independent workflow panels once per visitor."""
    review_controls = None
    with ui.left_drawer(bordered=True).props("width=360") as sidebar:
        ui.label("Shared inputs").classes("text-lg font-medium")
        ui.label("Used by Check policy and Suggest. Changing inputs never starts processing.").classes("text-sm")
    with ui.header():
        ui.button("Inputs", icon="menu", on_click=sidebar.toggle).props("flat color=white").tooltip("Show or hide shared inputs")
        ui.label("SNOMED Postprocessing — NiceGUI prototype").classes("text-xl")
    banner = ui.label().classes("text-amber-900 bg-amber-100 p-3 rounded w-full")
    source = ui.label().classes("text-sm")
    scope = ui.label().classes("text-sm")
    with ui.expansion("Saved suggestions scope").classes("w-full") as saved_scope:
        ui.label("Loaded suggestions inherit their saved annotator scope; it cannot be broadened here.")
        ui.label("Saved generation settings are displayed as provenance, not revalidated against a project or HDF5.")
        ui.label("Grid filters affect display only, not the source artifact or its annotator scope.")

    def change_tab(event):
        active = event.value == "review"
        if review_controls is not None:
            review_controls.keyboard.active = active
        for element in (banner, source, scope, saved_scope):
            element.set_visibility(active)

    with ui.tabs().classes("w-full") as tabs:
        tabs.on_value_change(change_tab)
        check = ui.tab("check", label="1. Check policy")
        suggest = ui.tab("suggest", label="2. Suggest")
        review = ui.tab("review", label="3. Review & apply")
    with ui.tab_panels(tabs, value=check).props("keep-alive").classes("w-full"):
        with ui.tab_panel(check):
            policy_controls = PolicyCheckControls(ui)
            policy_controls.inputs.move(sidebar)
        with ui.tab_panel(suggest):
            suggestion_controls = SuggestionControls(ui, policy_controls, lambda: review_controls)
        with ui.tab_panel(review) as review_panel:
            review_controls = ReviewPanelControls(ui, review_panel, banner=banner, source=source, scope=scope)
    suggestion_controls.connect_review()
    review_controls.keyboard.active = tabs.value == "review"
