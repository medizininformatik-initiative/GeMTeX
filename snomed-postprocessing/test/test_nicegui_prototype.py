"""Offline model/bootstrap checks; these do not validate the NiceGUI/browser runtime."""
import io
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from snomed_post_processing.gui.nicegui import app
from snomed_post_processing.gui.nicegui.suggestions import load_suggestions_preview
from test.test_nicegui_suggestions import payload, encoded


def preview_state():
    data = payload()
    data["suggestions"] = [deepcopy(data["suggestions"][0]) for _ in range(3)]
    for index, suggestion in enumerate(data["suggestions"]):
        suggestion["finding"]["document"] = f"document-{index}.txt"
    data["suggestions"][2]["candidates"] = []
    data["suggestions"][2]["context_candidates"] = []
    return load_suggestions_preview(encoded(data))


class PreviewStateTest(unittest.TestCase):
    def setUp(self):
        self.state = preview_state()
        self.candidate_id = self.state.findings[0].candidates[0].row_id

    def test_no_finding_or_candidate_preselected(self):
        self.assertIsNone(self.state.selected_finding)
        self.assertIsNone(self.state.selected_candidate_id)

    def test_page_states_are_independent(self):
        other = preview_state()
        self.state.select_finding(self.state.findings[0].row_id)
        self.state.preview_candidate(self.candidate_id)
        self.assertIsNone(other.selected_finding_id)
        self.assertIsNone(other.selected_candidate_id)

    def test_navigation_uses_stable_identity_not_visible_position(self):
        visible = list(reversed(self.state.findings))
        selected = self.state.select_finding(visible[0].row_id)
        self.assertEqual(selected.suggestion_index, 2)
        self.assertEqual(len(self.state.findings), 3)

    def test_changing_finding_clears_candidate_preview(self):
        self.state.select_finding(self.state.findings[0].row_id)
        self.state.preview_candidate(self.candidate_id)
        self.state.select_finding(self.state.findings[1].row_id)
        self.assertIsNone(self.state.selected_candidate_id)

    def test_repeated_navigation_preserves_candidate_preview(self):
        row_id = self.state.findings[0].row_id
        self.state.select_finding(row_id)
        self.state.preview_candidate(self.candidate_id)
        self.state.select_finding(row_id)
        self.assertEqual(self.state.selected_candidate_id, self.candidate_id)

    def test_unknown_identity_does_not_change_selection(self):
        row_id = self.state.findings[0].row_id
        self.state.select_finding(row_id)
        with self.assertRaises(ValueError):
            self.state.select_finding("forged")
        self.assertEqual(self.state.selected_finding_id, row_id)

    def test_candidate_must_belong_to_current_finding(self):
        with self.assertRaises(ValueError):
            self.state.preview_candidate(self.candidate_id)
        self.state.select_finding(self.state.findings[1].row_id)
        with self.assertRaises(ValueError):
            self.state.preview_candidate(self.candidate_id)
        self.assertIsNone(self.state.selected_candidate_id)

    def test_diagnostic_context_can_be_inspected_but_remains_nonselectable(self):
        self.state.select_finding(self.state.findings[1].row_id)
        candidate = self.state.preview_candidate(self.state.findings[1].candidates[-1].row_id)
        self.assertFalse(candidate.selectable)

    def test_string_codes_numeric_scores_and_competition_ranks_survive(self):
        candidates = self.state.findings[1].candidates[:3]
        self.assertEqual([item.rank for item in candidates], [1, 1, 3])
        self.assertEqual([item.score for item in candidates], [9.0000000001, 9.0, 4.0])
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
        from test.test_nicegui_suggestions import fake_ui, switch_document
        ui, grids, labels = fake_ui(preview_state())
        findings, candidates = grids
        switch_document(ui, 1)
        original_rows = findings.options["rowData"]
        select = findings.on.call_args[0][1]
        preview = candidates.on.call_args[0][1]
        select(SimpleNamespace(args={"data": original_rows[0]}))
        candidate_rows = candidates.options["rowData"]
        self.assertEqual([row["rank"] for row in candidate_rows[:3]], [1, 1, 3])
        context_id = candidate_rows[-1]["row_id"]
        preview(SimpleNamespace(args={"data": {"row_id": context_id}}))
        self.assertTrue(any(label.text.startswith("Diagnostic context only") for label in labels))
        select(SimpleNamespace(args={"data": original_rows[0]}))
        self.assertIs(candidates.options["rowData"], candidate_rows)
        self.assertIs(findings.options["rowData"], original_rows)
        switch_document(ui, 2)
        select(SimpleNamespace(args={"data": findings.options["rowData"][0]}))
        self.assertEqual(candidates.options["rowData"], [])
        preview(SimpleNamespace(args={"data": {"row_id": context_id}}))
        ui.notify.assert_called_once()

    def test_tables_are_stacked_full_width_and_candidate_text_cannot_collapse(self):
        from test.test_nicegui_suggestions import fake_ui
        ui, grids, _ = fake_ui()
        columns = [call.args[0] for call in ui.column.return_value.classes.call_args_list]
        self.assertEqual(columns[:3], ["w-full min-w-0 gap-4", "w-full min-w-0", "w-full min-w-0"])
        self.assertEqual(columns[3:], ["w-full min-w-0 gap-1", "w-full min-w-0 gap-1"])
        ui.element.return_value.classes.assert_any_call("grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 w-full min-w-0")
        covered_text = next(column for column in grids[0].options["columnDefs"] if column["field"] == "text")
        self.assertEqual(covered_text["minWidth"], 400)
        self.assertGreater(covered_text["flex"], 0)
        candidates = {column["field"]: column for column in grids[1].options["columnDefs"]}
        self.assertEqual(candidates["fsn"]["minWidth"], 240)
        self.assertEqual(candidates["rank"]["width"], 80)
        self.assertGreater(candidates["fsn"]["flex"], 0)

    def test_carousel_does_not_cache_the_moved_workspace(self):
        from test.test_nicegui_suggestions import fake_ui
        ui, _, _ = fake_ui()
        props = ui.carousel.return_value.props.call_args.args[0].split()
        self.assertNotIn("keep-alive", props)

    def test_tables_contain_scroll_chaining_without_disabling_internal_scrolling(self):
        from test.test_nicegui_suggestions import fake_ui
        _, grids, _ = fake_ui()
        for grid in grids:
            classes = grid.classes.call_args.args[0].split()
            self.assertIn("overflow-auto", classes)
            self.assertIn("overscroll-contain", classes)

    def test_score_formatting_is_display_only_with_full_precision_row_values(self):
        from test.test_nicegui_suggestions import fake_ui, payload, encoded
        from snomed_post_processing.gui.nicegui.review_panel import _candidate_rows
        from snomed_post_processing.gui.nicegui.suggestions import load_suggestions_preview
        _, grids, _ = fake_ui()
        score = next(column for column in grids[1].options["columnDefs"] if column["field"] == "score")
        self.assertEqual(score[":valueFormatter"], "params => params.value == null ? '' : params.value.toFixed(2)")
        self.assertEqual(score["filter"], "agNumberColumnFilter")
        source = load_suggestions_preview(encoded(payload()))
        rows = _candidate_rows(source.findings[0])
        self.assertEqual(rows[0]["score"], 9.0000000001)
        self.assertIsInstance(rows[0]["score"], float)
        self.assertEqual([row["rank"] for row in rows[:3]], [1, 1, 3])
        self.assertEqual(dict(source.findings[0].candidates[0].details)["Lexical score"], 0.123456789012345)

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
