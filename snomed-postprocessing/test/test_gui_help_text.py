"""Contextual GUI help renders without changing defaults or contacting services."""
import json
import pathlib
import tempfile
import unittest

from streamlit.testing.v1 import AppTest

from test.test_gui_review_defaults import APP as SETTINGS_APP
from snomed_post_processing.sanitization.conditions import DEFAULT_CONDITION_ASSOCIATIONS


REVIEW_APP = '''
from snomed_post_processing.gui.sanitization_run_tab import (
    _render_automatic_conditions, _render_inception_apply_upload_controls,
)
_render_automatic_conditions([], [], [])
_render_inception_apply_upload_controls(
    project_source=None, reviewed_decisions=[], decisions_text="[]", selected_count=0,
    has_invalid_selected_rows=False, manual_review_layer="webanno.custom.ManualReview",
    id_prefix="http://snomed.info/id/", id_feature="id",
)
'''


class GuiHelpTextTest(unittest.TestCase):
    def healthy(self, app):
        self.assertFalse(app.exception, str(app.exception))
        return app

    def widget(self, app, kind, label):
        return next(item for item in getattr(app, kind) if item.label == label)

    def test_suggestion_sidebar_and_rule_help(self):
        app = self.healthy(AppTest.from_string(SETTINGS_APP).run())
        for label in ("Minimum BM25 score", "Minimum lexical overlap ratio", "Maximum retained candidates"):
            self.assertTrue(self.widget(app, "number_input", label).help)
        self.assertIn("three distinct", self.widget(app, "number_input", "Maximum retained candidates").help)
        self.assertTrue(any(item.value == "Replacement requirements" for item in app.header))
        self.assertIn("contains:", self.widget(app, "selectbox", "Ignore overlap mode").help)
        self.assertIn("Active release", self.widget(app, "checkbox", "Historical ancestor fallback").help)
        columns = json.loads(app.dataframe[0].proto.columns)
        for column in ("rule_id", "source_code", "action", "target_code", "override_policy"):
            self.assertTrue(columns[column]["help"], column)
        self.assertIn("active", columns["override_policy"]["help"])
        self.assertIn("keeps the annotation", columns["action"]["help"])
        self.assertTrue(self.widget(app, "button", "Apply rules to review").help)

    def test_automatic_condition_help_and_relationship_descriptions(self):
        app = self.healthy(AppTest.from_string(REVIEW_APP).run())
        associations = self.widget(app, "multiselect", "Historical association types")
        self.assertEqual(associations.value, list(DEFAULT_CONDITION_ASSOCIATIONS))
        self.assertTrue(all(" — " in option for option in associations.options))
        self.assertIn("disable", associations.help)
        checkbox = self.widget(app, "checkbox", "Enable BM25 automatic selection (heuristic)")
        self.assertFalse(checkbox.value)
        self.assertIn("three distinct", checkbox.help)
        self.assertIn("2/3", self.widget(app, "number_input", "Minimum BM25 gap dominance").help)
        self.assertIn("20%", self.widget(app, "number_input", "Minimum BM25 relative lead").help)
        self.assertIn("CAS files are unchanged", self.widget(app, "button", "Apply Conditions").help)

    def test_deployment_help_preserves_offline_defaults(self):
        app = self.healthy(AppTest.from_string(REVIEW_APP).run())
        connection = self.widget(app, "checkbox", "Check connection during dry-run")
        tls = self.widget(app, "checkbox", "Disable TLS verification")
        remote = self.widget(app, "checkbox", "Apply to INCEpTION now (imports project and uploads artifacts)")
        self.assertFalse(connection.value)
        self.assertFalse(tls.value)
        self.assertFalse(remote.value)
        self.assertIn("Contact INCEpTION", connection.help)
        self.assertIn("weakens", tls.help)
        self.assertIn("not a remote-project", self.widget(app, "checkbox", "Overwrite temporary pipeline outputs if needed").help)
        self.assertTrue(self.widget(app, "button", "Run INCEpTION deployment pipeline").help)

    def test_shared_file_mode_help(self):
        with tempfile.TemporaryDirectory() as directory:
            pathlib.Path(directory, "sample.hdf5").write_text("fixture", encoding="utf-8")
            app = AppTest.from_string('''
import pathlib
from unittest.mock import patch
import streamlit as st
from snomed_post_processing.gui.file_sources import render_file_source_selector
with patch("streamlit.segmented_control", side_effect=lambda *args, **kwargs: kwargs["default"]):
    for index, mode in enumerate(["Upload", "Data directory", "Server path"]):
        render_file_source_selector(
            f"File {index}", key=f"file_{index}", data_dir=pathlib.Path(st.session_state["root"]),
            suffixes=(".hdf5",), default_source=mode,
        )
''')
            app.session_state["root"] = directory
            self.healthy(app.run())
            self.assertIn("your computer", app.get("file_uploader")[0].proto.help)
            self.assertIn("subfolders", app.selectbox[0].help)
            self.assertIn("absolute path", app.text_input[0].help)

    def test_report_downloads_explain_format_and_masking_limits(self):
        app = self.healthy(AppTest.from_string('''
import streamlit as st
from snomed_post_processing.gui.policy_tab import render_policy_check_result
st.session_state["policy_check_result"] = {
    "critical_documents_found": 0, "critical_findings": [], "report_folder": "test-output",
    "findings_json_text": "{}", "findings_json_name": "findings.json",
    "markdown_text": "report", "markdown_name": "report.md",
    "masked_markdown_text": "masked", "masked_markdown_name": "report.masked.md",
    "json_text": "{}", "json_name": "report.json",
}
render_policy_check_result()
''').run())
        downloads = {item.proto.label: item.proto.help for item in app.get("download_button")}
        self.assertIn("not clinical text", downloads["Download masked markdown report"])
        self.assertIn("not full anonymization", downloads["Download masked markdown report"])
        self.assertIn("CriticalFindings JSON instead", downloads["Download report json"])

    def test_replacement_banners_explain_both_modes_without_changing_the_check(self):
        app = AppTest.from_string('''
import pathlib
import runpy
from unittest.mock import patch
import streamlit as st
from snomed_post_processing.gui.sidebar import GuiInputs
inputs = GuiInputs(
    load_annotators=False, hdf5_file=None, annotation_types_text="gemtex.Concept",
    ignore_overlap_types_text="", ignore_overlap_mode="overlap", id_prefix="", id_feature="id",
    data_dir=pathlib.Path("."), target_view=st.session_state["test_target_view"],
)
with patch("snomed_post_processing.gui.sidebar.render_sidebar", return_value=inputs), \\
     patch("snomed_post_processing.gui.policy_tab.render_policy_tab"), \\
     patch("snomed_post_processing.gui.sanitization_check_tab.render_sanitization_check_tab"), \\
     patch("snomed_post_processing.gui.sanitization_run_tab.render_sanitization_run_tab"):
    runpy.run_module("snomed_post_processing.gui.app", run_name="__main__")
''')
        for mode, description in (
            ("policy", "active concepts in the inclusion list and outside the exclusion list"),
            ("release", "Inclusion-list membership is not required. Exclusion lists apply only when enabled"),
        ):
            with self.subTest(mode=mode):
                app.session_state["test_target_view"] = mode
                self.healthy(app.run())
                self.assertEqual(app.tabs[0].label, "1. Check policy")
                self.assertTrue(any(description in item.value for item in app.info))
                clarification = [item.value for item in app.caption if "not the policy check in tab 1" in item.value]
                self.assertEqual(len(clarification), 1)
                self.assertIn("Explicit concept rules may override list restrictions", clarification[0])
                self.assertFalse(any("materialized" in item.value for item in app.info))


if __name__ == "__main__":
    unittest.main()
