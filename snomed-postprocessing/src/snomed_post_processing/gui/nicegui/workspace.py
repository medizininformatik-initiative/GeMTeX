"""Project-authored navigation shell around the shared NiceGUI workflow."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .page import WorkflowControls, build_workspace
from .shared_inputs import SharedInputControls

ASSETS = Path(__file__).parent / "assets"
ASSET_URL = "/workspace-assets"
STYLESHEET_VERSION = sha256((ASSETS / "shell.css").read_bytes()).hexdigest()[:12]
STEPS = (
    ("check", "Check policy", "fact_check"),
    ("suggest", "Suggestions & rules", "auto_fix_high"),
    ("review", "Review & apply", "rate_review"),
)


@dataclass
class ShellControls:
    workflow: WorkflowControls
    navigation: object
    inputs_drawer: object
    navigation_buttons: dict
    collapse_button: object


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

    buttons = {}
    compact_navigation = False
    with ui.left_drawer(bordered=True).props("width=236 breakpoint=980").classes(
        "workspace-navigation"
    ) as navigation:
        with ui.column().classes("w-full workspace-navigation-content"):
            caption = ui.label("Workflow").classes("workspace-navigation-caption")
            for key, label, icon in STEPS:
                buttons[key] = ui.button(
                    label,
                    icon=icon,
                    on_click=lambda _, target=key: workflow.tabs.set_value(target),
                ).props("flat no-caps").classes("workspace-navigation-item").tooltip(label)
            ui.separator().classes("my-2")

            def collapse():
                nonlocal compact_navigation
                compact_navigation = not compact_navigation
                navigation.props(f"width={72 if compact_navigation else 236}")
                caption.set_visibility(not compact_navigation)
                for key, label, _ in STEPS:
                    buttons[key].set_text("" if compact_navigation else label)
                collapse_button.set_text("" if compact_navigation else "Collapse")
                collapse_button.props(f"icon={'chevron_right' if compact_navigation else 'chevron_left'}")

            collapse_button = ui.button(
                "Collapse", icon="chevron_left", on_click=collapse
            ).props("flat no-caps").classes("workspace-navigation-item").tooltip(
                "Expand or collapse navigation"
            )

    with ui.header().classes("workspace-header items-center px-4 gap-3"):
        ui.button(icon="menu", on_click=navigation.toggle).props("flat round").tooltip(
            "Show or hide navigation"
        )
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

    def highlight(value):
        for key, button in buttons.items():
            button.classes(
                add="workspace-navigation-item-active" if key == value else "",
                remove="" if key == value else "workspace-navigation-item-active",
            )

    workflow.tabs.on_value_change(lambda event: highlight(event.value))
    highlight(workflow.tabs.value)
    return ShellControls(workflow, navigation, inputs_drawer, buttons, collapse_button)
