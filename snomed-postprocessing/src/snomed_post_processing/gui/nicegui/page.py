"""NiceGUI page shell and workflow tab composition."""
from dataclasses import dataclass

from .policy_ui import PolicyCheckControls
from .shared_inputs import SharedInputControls
from .review_panel import ReviewPanelControls
from .suggestion_ui import SuggestionControls
from .store_restoration_ui import StoreRestorationControls
from .deployment_ui import InceptionDeploymentControls


@dataclass
class WorkflowControls:
    tabs: object
    inputs: SharedInputControls
    policy: PolicyCheckControls
    suggestions: SuggestionControls
    review: ReviewPanelControls


def build_page(ui, events):
    """Build independent workflow panels once per visitor."""
    with ui.left_drawer(bordered=True).props("width=360") as sidebar:
        shared_inputs = SharedInputControls(ui)
    with ui.header():
        ui.button("Inputs", icon="menu", on_click=sidebar.toggle).props("flat color=white").tooltip("Show or hide shared inputs")
        ui.label("SNOMED Postprocessing").classes("text-xl")
    return build_workspace(ui, events, shared_inputs)


def build_workspace(ui, events, shared_inputs):
    """Compose the same persistent workflow inside either application shell."""
    review_controls = None

    def change_tab(event):
        if review_controls is not None:
            review_controls.keyboard.active = event.value == "review"

    with ui.tabs().classes("w-full") as tabs:
        tabs.on_value_change(change_tab)
        check = ui.tab("check", label="1. Check policy")
        suggest = ui.tab("suggest", label="2. Suggest")
        review = ui.tab("review", label="3. Review & apply")
    with ui.tab_panels(tabs, value="check").props("keep-alive").classes("w-full"):
        with ui.tab_panel(check):
            policy_controls = PolicyCheckControls(ui, shared_inputs)
        with ui.tab_panel(suggest):
            suggestion_controls = SuggestionControls(ui, shared_inputs, policy_controls, lambda: review_controls)
        with ui.tab_panel(review) as review_panel:
            provenance = ui.label().classes("text-sm")
            review_controls = ReviewPanelControls(ui, review_panel, provenance=provenance,
                                                  data_dir=shared_inputs.data_dir)
            StoreRestorationControls(ui, shared_inputs, review_controls)
            InceptionDeploymentControls(ui, shared_inputs, review_controls)
    suggestion_controls.connect_review()
    review_controls.keyboard.active = tabs.value == "review"
    return WorkflowControls(tabs, shared_inputs, policy_controls, suggestion_controls, review_controls)
