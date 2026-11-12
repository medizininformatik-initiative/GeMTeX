"""Offline model/bootstrap checks; these do not validate the NiceGUI/browser runtime."""
import io
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from snomed_post_processing.gui.nicegui import app
from snomed_post_processing.gui.nicegui.demo import create_demo_state


class PreviewStateTest(unittest.TestCase):
    def setUp(self):
        self.state = create_demo_state()

    def test_no_finding_or_candidate_preselected(self):
        self.assertIsNone(self.state.selected_finding)
        self.assertIsNone(self.state.selected_candidate_id)

    def test_page_states_are_independent(self):
        other = create_demo_state()
        self.state.select_finding(self.state.findings[0].row_id)
        self.state.preview_candidate("demo:0:selectable:0")
        self.assertIsNone(other.selected_finding_id)
        self.assertIsNone(other.selected_candidate_id)

    def test_navigation_uses_stable_identity_not_visible_position(self):
        visible = list(reversed(self.state.findings))
        selected = self.state.select_finding(visible[0].row_id)
        self.assertEqual(selected.suggestion_index, 2)
        self.assertEqual(len(self.state.findings), 3)

    def test_changing_finding_clears_candidate_preview(self):
        self.state.select_finding(self.state.findings[0].row_id)
        self.state.preview_candidate("demo:0:selectable:0")
        self.state.select_finding(self.state.findings[1].row_id)
        self.assertIsNone(self.state.selected_candidate_id)

    def test_repeated_navigation_preserves_candidate_preview(self):
        row_id = self.state.findings[0].row_id
        self.state.select_finding(row_id)
        self.state.preview_candidate("demo:0:selectable:0")
        self.state.select_finding(row_id)
        self.assertEqual(self.state.selected_candidate_id, "demo:0:selectable:0")

    def test_unknown_identity_does_not_change_selection(self):
        row_id = self.state.findings[0].row_id
        self.state.select_finding(row_id)
        with self.assertRaises(ValueError):
            self.state.select_finding("forged")
        self.assertEqual(self.state.selected_finding_id, row_id)

    def test_candidate_must_belong_to_current_finding(self):
        with self.assertRaises(ValueError):
            self.state.preview_candidate("demo:0:selectable:0")
        self.state.select_finding(self.state.findings[1].row_id)
        with self.assertRaises(ValueError):
            self.state.preview_candidate("demo:0:selectable:0")
        self.assertIsNone(self.state.selected_candidate_id)

    def test_diagnostic_context_can_be_inspected_but_remains_nonselectable(self):
        self.state.select_finding(self.state.findings[1].row_id)
        candidate = self.state.preview_candidate("demo:1:context:0")
        self.assertFalse(candidate.selectable)

    def test_string_codes_numeric_scores_and_competition_ranks_survive(self):
        candidates = self.state.findings[1].candidates[:3]
        self.assertEqual([item.rank for item in candidates], [1, 1, 3])
        self.assertEqual([item.score for item in candidates], [9.0, 9.0, 4.0])
        self.assertTrue(all(isinstance(item.code, str) for item in candidates))


class NiceGuiBootstrapTest(unittest.TestCase):
    def test_imports_do_not_load_either_gui_framework(self):
        result = subprocess.run(
            [sys.executable, "-I", "-c", "import sys; import snomed_post_processing.gui.nicegui.app; import snomed_post_processing.gui.nicegui.page; assert 'streamlit' not in sys.modules; assert 'nicegui' not in sys.modules"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unsupported_python_is_rejected_before_framework_import(self):
        with patch.object(app.sys, "version_info", (3, 9, 23)), patch.object(app.importlib.metadata, "version") as version:
            with self.assertRaisesRegex(RuntimeError, "Python 3.11"):
                app._load_ui()
        version.assert_not_called()

    def test_missing_nicegui_has_actionable_error(self):
        with patch.object(app.sys, "version_info", (3, 11, 0)), patch.object(
            app.importlib.metadata, "version", side_effect=app.importlib.metadata.PackageNotFoundError("nicegui")
        ):
            with self.assertRaisesRegex(RuntimeError, "nicegui extra"):
                app._load_ui()

    def test_unpinned_nicegui_is_rejected(self):
        with patch.object(app.sys, "version_info", (3, 11, 0)), patch.object(
            app.importlib.metadata, "version", return_value="0.0.0"
        ):
            with self.assertRaisesRegex(RuntimeError, "nicegui==4.0.0"):
                app._load_ui()

    def test_page_navigation_updates_detail_grid_not_finding_grid(self):
        from snomed_post_processing.gui.nicegui.page import build_page
        ui = MagicMock()
        grids, labels = [], []

        def grid(options):
            element = MagicMock()
            element.options = options
            element.classes.return_value = element
            grids.append(element)
            return element

        def label(text=""):
            element = MagicMock()
            element.classes.return_value = element
            labels.append((text, element))
            return element

        ui.aggrid.side_effect = grid
        ui.label.side_effect = label
        build_page(ui)
        findings, candidates = grids
        original_rows = findings.options["rowData"]
        select = findings.on.call_args[0][1]
        preview = candidates.on.call_args[0][1]
        select(SimpleNamespace(args={"data": original_rows[1]}))
        candidate_rows = candidates.options["rowData"]
        self.assertEqual([row["rank"] for row in candidate_rows[:3]], [1, 1, 3])
        preview(SimpleNamespace(args={"data": {"row_id": "demo:1:context:0"}}))
        preview_label = next(element for text, element in labels if text.startswith("Candidate clicks"))
        self.assertIn("Diagnostic context only", preview_label.set_text.call_args[0][0])
        select(SimpleNamespace(args={"data": original_rows[1]}))
        self.assertIs(candidates.options["rowData"], candidate_rows)
        self.assertIs(findings.options["rowData"], original_rows)
        select(SimpleNamespace(args={"data": original_rows[2]}))
        self.assertEqual(candidates.options["rowData"], [])
        preview(SimpleNamespace(args={"data": {"row_id": "demo:1:context:0"}}))
        ui.notify.assert_called_once()

    def test_registers_page_and_starts_one_server_without_reload_or_browser(self):
        ui = MagicMock()
        with patch.object(app, "_load_ui", return_value=ui):
            self.assertEqual(app.main([]), 0)
        ui.page.assert_called_once_with("/")
        ui.run.assert_called_once_with(host="127.0.0.1", port=8080, show=False,
                                       reload=False, title="SNOMED Postprocessing — NiceGUI prototype")

    def test_runtime_error_is_reported_without_starting_server(self):
        with patch.object(app, "_load_ui", side_effect=RuntimeError("Separate environment required")), redirect_stderr(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as exited:
                app.main([])
        self.assertEqual(exited.exception.code, 2)
        self.assertIn("Separate environment required", output.getvalue())

    def test_invalid_port_is_rejected_before_loading_framework(self):
        with patch.object(app, "_load_ui") as load, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                app.main(["--port", "0"])
        load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
