"""Project-authored navigation shell around the shared NiceGUI workflow."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .page import WorkflowControls, build_workspace
from .shared_inputs import SharedInputControls

ASSETS = Path(__file__).parent / "assets"
ASSET_URL = "/workspace-assets"
STYLESHEET_VERSION = sha256((ASSETS / "shell.css").read_bytes()).hexdigest()[:12]
@dataclass
class ShellControls:
    workflow: WorkflowControls
    inputs_drawer: object


def register_assets(app):
    """Expose only the shell stylesheet; workflow files are never public assets."""
    app.add_static_files(ASSET_URL, str(ASSETS))


def _decorate_annotator_select(selector):
    selector.props("use-chips popup-content-class=workspace-annotator-options").classes("w-full min-w-0")
    selector.add_slot("option", '''
        <q-item v-bind="props.itemProps">
            <q-item-section side>
                <q-icon :name="props.selected ? 'check_box' : 'check_box_outline_blank'"
                        :color="props.selected ? 'primary' : 'grey-6'" />
            </q-item-section>
            <q-item-section><q-item-label>{{ props.opt.label }}</q-item-label></q-item-section>
        </q-item>
    ''')


def build_page(ui, events):
    ui.colors(primary="#2457a7", secondary="#e8eef8", positive="#2e7d52",
              negative="#c53d4d", warning="#b66a00", info="#276f9f")
    ui.add_head_html(
        f'<link rel="stylesheet" href="{ASSET_URL}/shell.css?v={STYLESHEET_VERSION}">'
    )

    with ui.right_drawer(value=False, bordered=True).props("width=400 breakpoint=1180").classes(
        "workspace-settings"
    ) as inputs_drawer:
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Inputs & settings").classes("text-lg font-semibold")
            ui.button(icon="close", on_click=inputs_drawer.hide).props("flat round").tooltip("Close inputs")
        shared_inputs = SharedInputControls(ui)
        _decorate_annotator_select(shared_inputs.annotators)
        _decorate_annotator_select(shared_inputs.excluded_annotators)

    with ui.header().classes("workspace-header items-center px-4 gap-3"):
        ui.icon("account_tree").classes("workspace-product-icon text-2xl")
        ui.label("SNOMED Postprocessing").classes("workspace-product-name")
        ui.space()
        ui.button("Inputs", icon="tune", on_click=inputs_drawer.toggle).props("flat no-caps").tooltip(
            "Shared inputs and generation settings"
        )

    with ui.column().classes("workspace-page"):
        with ui.column().classes("gap-1"):
            ui.label("Annotation workspace").classes("workspace-title")
            ui.label("Check policy, prepare suggestions, and review changes before export.").classes(
                "workspace-subtitle"
            )
        with ui.column().classes("workspace-content"):
            workflow = build_workspace(ui, events, shared_inputs)
            workflow.tabs.classes("workspace-tabs")

    return ShellControls(workflow, inputs_drawer)
