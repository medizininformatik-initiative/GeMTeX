"""MIE findings-table port: filters, session persistence, and sanitization handoff."""
import unittest

from streamlit.testing.v1 import AppTest

from snomed_post_processing.gui.streamlit.policy_tab import (
    _check_label,
    _finding_count_summary,
    _finding_matches_filters,
    _finding_row,
)
from snomed_post_processing.uima_processing import CriticalFinding


FINDINGS = [
    CriticalFinding("bob", "b.txt", "200", "Beta", (8, 12), "blacklist", "excluded", layer="Concept", fsn="Beta (finding)"),
    CriticalFinding("alice", "a.txt", "101", "Alpha later", (10, 21), "whitelist", "missing", layer="Concept"),
    CriticalFinding("alice", "a.txt", "100", "Alpha", (0, 5), "whitelist", "missing", layer="Concept"),
    CriticalFinding("bob", "a.txt", None, "Ignored", (22, 29), "blacklist", "overlap", ignored=True),
]

APP = '''
import pathlib
from types import SimpleNamespace
from unittest.mock import patch
import streamlit as st
from snomed_post_processing.gui.streamlit.policy_tab import render_policy_tab
from snomed_post_processing.gui.streamlit.sidebar import GuiInputs
from test.test_gui_policy_tab import FINDINGS

st.session_state.setdefault("zip_file", pathlib.Path("project.zip"))
inputs = GuiInputs(
    load_annotators=False, hdf5_file=pathlib.Path("policy.hdf5"),
    annotation_types_text="Concept", ignore_overlap_types_text="",
    ignore_overlap_mode="overlap", id_prefix="", id_feature="id",
    data_dir=pathlib.Path("."), hdf5_temp_path=pathlib.Path("policy.hdf5"),
    target_view=st.session_state.get("test_target_view", "policy"),
)
def report_path(name, text):
    return SimpleNamespace(name=name, parent=pathlib.Path("reports"), read_text=lambda **kwargs: text)
def generate(**kwargs):
    st.session_state["generation_count"] = st.session_state.get("generation_count", 0) + 1
    st.session_state["generation_kwargs"] = kwargs
    return (
        report_path("report.md", "# Report"),
        report_path("masked.md", "# Masked"),
        report_path("report.json", "{}"),
        report_path("findings.json", "[]"),
        2, [] if st.session_state.get("test_empty") else FINDINGS,
    )
with patch("snomed_post_processing.gui.streamlit.policy_tab.save_uploaded_file", return_value=pathlib.Path("project.zip")), \\
     patch("snomed_post_processing.gui.streamlit.policy_tab.generate_report", side_effect=generate):
    render_policy_tab(inputs)
'''


class FindingTableHelpersTest(unittest.TestCase):
    def matches(self, finding, **kwargs):
        filters = dict(status="all", check="all", sctid_query="", text_query="")
        filters.update(kwargs)
        return _finding_matches_filters(finding, **filters)

    def test_row_mapping_preserves_missing_values_and_public_terminology(self):
        row = _finding_row(FINDINGS[3])
        self.assertEqual(row, {
            "sctid": "", "fsn": "", "covered_text": "Ignored",
            "status": "ignored", "check": "exclusion list", "annotation_layer": "",
        })
        self.assertEqual(_check_label("whitelist"), "inclusion list")
        self.assertEqual(_check_label("future-check"), "future-check")

    def test_combined_filters_and_missing_code(self):
        self.assertTrue(_finding_matches_filters(
            FINDINGS[0], status="critical", check="exclusion list", sctid_query="20", text_query="beta",
        ))
        for kwargs in (
            {"status": "ignored"}, {"check": "inclusion list"},
            {"sctid_query": "999"}, {"text_query": "alpha"},
        ):
            filters = dict(status="all", check="all", sctid_query="", text_query="")
            filters.update(kwargs)
            self.assertFalse(_finding_matches_filters(FINDINGS[0], **filters))
        self.assertFalse(self.matches(FINDINGS[3], sctid_query="1"))

    def test_summary_counts_ignored_and_checks_independently(self):
        self.assertEqual(
            _finding_count_summary(FINDINGS),
            "3 critical · 1 ignored · 2 inclusion-list · 2 exclusion-list",
        )


class PolicyTableGuiTest(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_string(APP).run()
        self.assertHealthy()

    def assertHealthy(self):
        self.assertFalse(self.app.exception, str(self.app.exception))

    def widget(self, kind, label):
        return next(widget for widget in getattr(self.app, kind) if widget.label == label)

    def run_check(self):
        self.widget("button", "Run policy check").click().run()
        self.assertHealthy()

    def test_result_persists_without_regeneration_and_preserves_handoff(self):
        self.assertEqual(len(self.app.dataframe), 0)
        self.run_check()
        self.assertEqual(self.app.session_state["generation_count"], 1)
        self.assertEqual(self.app.session_state["critical_findings"], FINDINGS)
        self.assertEqual(self.app.session_state["critical_findings_json_text"], "[]")
        self.assertEqual(self.app.session_state["critical_findings_json_name"], "findings.json")
        self.assertEqual(self.app.session_state["generation_kwargs"]["annotation_types"], ["Concept"])
        self.assertEqual(len(self.app.dataframe), 3)
        self.assertEqual(self.app.dataframe[0].value["sctid"].tolist(), ["100", "101"])
        self.assertEqual(self.widget("metric", "Critical findings").value, "3")
        self.assertEqual(self.widget("metric", "Ignored findings").value, "1")
        self.app.run()
        self.assertHealthy()
        self.assertEqual(len(self.app.dataframe), 3)
        self.assertEqual(self.app.session_state["generation_count"], 1)
        labels = {item.label for item in self.app.get("download_button")}
        self.assertEqual(labels, {
            "Download CriticalFindings JSON", "Download markdown report",
            "Download masked markdown report", "Download report json",
        })

    def test_filters_empty_state_and_reset_leave_original_results_unchanged(self):
        self.run_check()
        self.widget("selectbox", "Status").select("critical")
        self.widget("selectbox", "Check").select("inclusion list")
        self.widget("text_input", "SCTID contains").input(" 100 ")
        self.widget("text_input", "Covered text contains").input(" ALPHA ").run()
        self.assertHealthy()
        self.assertEqual(len(self.app.dataframe), 1)
        self.assertEqual(self.app.dataframe[0].value["sctid"].tolist(), ["100"])
        self.widget("text_input", "Covered text contains").input("no match").run()
        self.assertEqual(len(self.app.dataframe), 0)
        self.assertTrue(any("No findings match" in item.value for item in self.app.info))
        self.widget("button", "Clear all filters").click().run()
        self.assertHealthy()
        self.assertEqual(len(self.app.dataframe), 3)
        self.assertEqual(self.widget("selectbox", "Status").value, "all")
        self.assertEqual(self.widget("selectbox", "Check").value, "all")
        self.assertEqual(self.widget("text_input", "SCTID contains").value, "")
        self.assertEqual(self.widget("text_input", "Covered text contains").value, "")
        self.assertEqual(self.app.session_state["generation_count"], 1)
        self.assertEqual(self.app.session_state["policy_check_result"]["critical_findings"], FINDINGS)
        self.assertEqual(self.app.session_state["critical_findings"], FINDINGS)

    def test_empty_findings_keep_downloads_and_success_message(self):
        self.app.session_state["test_empty"] = True
        self.run_check()
        self.assertEqual(len(self.app.dataframe), 0)
        self.assertTrue(any("No findings to display" in item.value for item in self.app.success))
        self.assertEqual(len(self.app.get("download_button")), 4)

    def test_release_mode_still_explains_policy_check_scope(self):
        self.app.session_state["test_target_view"] = "release"
        self.app.run()
        self.assertTrue(any("This tab still runs the policy check" in item.value for item in self.app.info))


if __name__ == "__main__":
    unittest.main()
