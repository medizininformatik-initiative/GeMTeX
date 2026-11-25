"""Local shell/SDK checks; no browser, clinical inputs or external services."""
import subprocess
import sys
import unittest
from importlib.util import find_spec
from unittest.mock import MagicMock, patch

from snomed_post_processing.gui import app as launcher
from snomed_post_processing.gui.nicegui import frontend as app
from snomed_post_processing.gui.nicegui.workspace import ASSETS, ASSET_URL, STYLESHEET_VERSION, register_assets


class WorkspaceBootstrapTest(unittest.TestCase):
    def test_launcher_forwards_options_without_starting_streamlit(self):
        for selector in (["--frontend", "nicegui"], ["--frontend=nicegui"]):
            with patch.object(app, "main", return_value=7) as start, patch.object(launcher.subprocess, "call") as streamlit:
                self.assertEqual(launcher.main([*selector, "--port", "8081", "--show"]), 7)
                start.assert_called_once_with(["--port", "8081", "--show"])
                streamlit.assert_not_called()

    def test_imports_have_no_framework_or_server_side_effects(self):
        result = subprocess.run([sys.executable, "-I", "-c",
            "import sys; import snomed_post_processing.gui.nicegui.frontend; "
            "import snomed_post_processing.gui.nicegui.workspace; "
            "assert 'nicegui' not in sys.modules; assert 'streamlit' not in sys.modules; "
            "assert 'sqlalchemy' not in sys.modules"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reuses_guarded_runtime_without_reload(self):
        from snomed_post_processing.gui.nicegui import app as runtime
        ui, events = MagicMock(), object()
        with patch.object(runtime, "_load_ui", return_value=(ui, events)), patch(
            "snomed_post_processing.gui.nicegui.workspace.register_assets") as assets:
            self.assertEqual(app.main(["--port", "8081"]), 0)
        assets.assert_called_once()
        ui.run.assert_called_once_with(host="127.0.0.1", port=8081, show=False,
                                       reload=False, title="SNOMED Postprocessing — Workspace")
        ui.page.assert_called_once_with("/")

    def test_only_bundled_styling_is_exposed(self):
        sdk_app = MagicMock()
        register_assets(sdk_app)
        sdk_app.add_static_files.assert_called_once_with(ASSET_URL, str(ASSETS))
        self.assertTrue((ASSETS / "shell.css").is_file())
        self.assertEqual(len(STYLESHEET_VERSION), 12)
        self.assertFalse((ASSETS / "fonts").exists())
        css = (ASSETS / "shell.css").read_text(encoding="utf-8")
        self.assertNotIn("http", css)
        self.assertNotIn("@font-face", css)
        self.assertNotIn(".q-field__label", css)
        self.assertIn(".workspace-content .q-expansion-item", css)
        self.assertIn(".q-expansion-item--expanded", css)


@unittest.skipUnless(find_spec("nicegui"), "requires the NiceGUI extra")
class WorkspaceShellTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from nicegui import Client, events, ui
        from nicegui.page import page
        from snomed_post_processing.gui.nicegui.workspace import build_page
        self.client = Client(page("/workspace-test"))
        self.other = None
        with self.client:
            self.shell = build_page(ui, events)

    async def asyncTearDown(self):
        if self.other:
            self.other.delete()
        self.client.delete()

    async def test_navigation_preserves_one_shared_workflow_and_review_drafts(self):
        from test.test_nicegui_suggestions import encoded, payload
        from snomed_post_processing.gui.nicegui.suggestions import load_suggestions_preview
        shell, workflow = self.shell, self.shell.workflow
        self.assertIs(workflow.policy.inputs, workflow.inputs)
        self.assertIs(workflow.suggestions.inputs, workflow.inputs)
        with self.client:
            workflow.review.publish_generated(load_suggestions_preview(encoded(payload()), "synthetic.json"))
        session = workflow.review.controls.session
        row = workflow.review.state.findings[0]
        session.stage(row.row_id, action="none")
        for target in ("suggest", "review", "check", "review"):
            workflow.tabs.set_value(target)
            self.assertIs(workflow.review.controls.session, session)
            self.assertTrue(session.drafts)
            self.assertEqual(workflow.review.keyboard.active, target == "review")
            self.assertIn("workspace-navigation-item-active", shell.navigation_buttons[target]._classes)
        self.assertFalse(workflow.inputs.closed)
        self.assertFalse(session.saved)
        self.assertIsNone(workflow.suggestions.completed)
        self.assertFalse(shell.inputs_drawer.value)

    async def test_annotator_choices_use_chips_and_checkmarks_without_changing_scope_rules(self):
        included = self.shell.workflow.inputs.annotators
        excluded = self.shell.workflow.inputs.excluded_annotators
        for selector in (included, excluded):
            self.assertTrue(selector.props["use-chips"])
            self.assertEqual(selector.props["popup-content-class"], "workspace-annotator-options")
            self.assertIn("props.itemProps", selector.slots["option"].template)
            self.assertIn("props.selected", selector.slots["option"].template)
        included.set_options({"Alice": "Alice", "Bob": "Bob"}, value=["Alice"])
        excluded.set_options({"Alice": "Alice", "Bob": "Bob"}, value=[])
        self.shell.workflow.inputs.available_annotators = ("Alice", "Bob")
        self.assertEqual(self.shell.workflow.inputs.settings().annotators, ("alice",))
        included.set_value(["Alice", "Bob"])
        self.assertEqual(self.shell.workflow.inputs.settings().annotators, ("alice", "bob"))
        included.set_value([])
        self.assertEqual(self.shell.workflow.inputs.settings().annotators, ())
        excluded.set_value(["Alice"])
        self.assertEqual(self.shell.workflow.inputs.settings().annotators, ("bob",))
        self.assertIsNone(self.shell.workflow.suggestions.completed)

    async def test_clients_have_independent_state(self):
        from nicegui import Client, events, ui
        from nicegui.page import page
        from snomed_post_processing.gui.nicegui.workspace import build_page
        self.other = Client(page("/workspace-other-test"))
        with self.other:
            other = build_page(ui, events)
        self.shell.workflow.tabs.set_value("suggest")
        self.shell.workflow.inputs.prefix.set_value("changed")
        self.assertEqual(other.workflow.tabs.value, "check")
        self.assertNotEqual(other.workflow.inputs.prefix.value, "changed")
        self.assertIsNot(self.shell.workflow.review.controls.session, other.workflow.review.controls.session)
