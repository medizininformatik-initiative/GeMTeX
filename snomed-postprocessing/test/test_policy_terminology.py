"""Presentation terminology changes must not alter machine-facing policy data."""
from collections import Counter
import dataclasses
import io
import pathlib
import unittest

from click.testing import CliRunner
from streamlit.testing.v1 import AppTest

from snomed_post_processing.cli.app import create_concept_id_dump, suggest_sanitization_cli
from snomed_post_processing.findings_io.mapping import critical_finding_to_dict
from snomed_post_processing.gui.streamlit.sanitization_run_tab import _policy_issue_label, _status_label
from snomed_post_processing.hdf5_handling.metadata import (
    BlacklistMetadata, Hdf5MetadataSummary, format_hdf5_metadata_summary,
)
from snomed_post_processing.sanitization.json_io import sanitization_suggestion_to_dict
from snomed_post_processing.sanitization.models import SanitizationStatus, SanitizationSuggestion
from snomed_post_processing.sanitization.report import write_sanitization_markdown_report
from snomed_post_processing.snomed import Information
from snomed_post_processing.terminology import finding_reason_label, policy_label
from snomed_post_processing.uima_processing import CriticalFinding
from snomed_post_processing.uima_processing.markdown_report import log_final_tag_count, render_finding_sections


FINDING = CriticalFinding(
    annotator="reviewer", document="doc.txt", code="123", covered_text="text",
    offset=(0, 4), list_type="blacklist", reason="blacklisted",
)


class PolicyTerminologyTest(unittest.TestCase):
    def test_policy_and_reason_display_names(self):
        self.assertEqual(policy_label("whitelist"), "inclusion list")
        self.assertEqual(policy_label("blacklist"), "exclusion list")
        self.assertEqual(policy_label("other"), "other")
        self.assertEqual(finding_reason_label("not_in_whitelist"), "not on inclusion list")
        self.assertEqual(finding_reason_label("blacklisted"), "on exclusion list")
        self.assertEqual(finding_reason_label("custom reason"), "custom reason")
        self.assertEqual(_policy_issue_label(FINDING), "Reason: on exclusion list")
        self.assertEqual(
            _policy_issue_label(dataclasses.replace(FINDING, list_type="whitelist")),
            "Reason: not on inclusion list",
        )
        self.assertEqual(
            _status_label(SanitizationStatus.BLACKLISTED_NO_AUTO_SANITIZATION),
            "Excluded/no automatic sanitization",
        )

    def test_policy_report_headings_anchors_and_ignored_reasons(self):
        findings = [
            FINDING,
            dataclasses.replace(FINDING, list_type="whitelist", reason="not_in_whitelist"),
            dataclasses.replace(FINDING, ignored=True),
            dataclasses.replace(FINDING, list_type="whitelist", reason="not_in_whitelist", ignored=True),
        ]
        output, masked = io.StringIO(), io.StringIO()
        render_finding_sections(findings, output, masked)
        for report in (output.getvalue(), masked.getvalue()):
            self.assertIn("# Inclusion list\n", report)
            self.assertIn("# Exclusion list\n", report)
            self.assertIn("(#inclusion-list)", report)
            self.assertIn("(#exclusion-list)", report)
            self.assertIn("not on inclusion list", report)
            self.assertIn("on exclusion list", report)
            self.assertNotRegex(report.lower(), "whitelist|blacklist")
        self.assertIn("[Inclusion list](#inclusion-list)", Information.log_dump_pretext)
        self.assertIn("[Exclusion list](#exclusion-list)", Information.log_dump_pretext)

    def test_empty_report_counts_use_new_terms(self):
        output, masked = io.StringIO(), io.StringIO()
        log_final_tag_count(Counter(), Counter(), output, masked)
        self.assertIn("not on the inclusion list", output.getvalue())
        self.assertIn("on the exclusion list", output.getvalue())
        self.assertNotRegex(output.getvalue().lower(), "whitelist|blacklist")

    def test_suggestion_markdown_renames_status_but_not_json(self):
        suggestion = SanitizationSuggestion(
            finding=FINDING, status=SanitizationStatus.BLACKLISTED_NO_AUTO_SANITIZATION,
        )
        output = io.StringIO()
        write_sanitization_markdown_report([suggestion], output)
        self.assertIn("excluded_no_auto_sanitization", output.getvalue())
        self.assertNotIn("blacklisted_no_auto_sanitization", output.getvalue())
        payload = sanitization_suggestion_to_dict(suggestion)
        self.assertEqual(payload["status"], "blacklisted_no_auto_sanitization")
        self.assertEqual(payload["finding"]["list_type"], "blacklist")
        self.assertEqual(payload["finding"]["reason"], "blacklisted")
        self.assertEqual(critical_finding_to_dict(FINDING)["list_type"], "blacklist")

    def test_clinical_content_is_not_rewritten(self):
        finding = dataclasses.replace(FINDING, fsn="Blacklisted concept (finding)", covered_text="whitelist")
        output = io.StringIO()
        render_finding_sections([finding], output, io.StringIO())
        self.assertIn("Blacklisted concept (finding)", output.getvalue())
        self.assertIn("whitelist", output.getvalue())

    def test_metadata_labels_keep_actual_hdf5_paths(self):
        summary = Hdf5MetadataSummary(
            path=pathlib.Path("policy.hdf5"), has_concepts=False,
            policy_view_counts=(("whitelist", "0", 2), ("blacklist", "0", 1)),
            blacklist_metadata=(BlacklistMetadata("0", None, None, ()),),
        )
        text = format_hdf5_metadata_summary(summary)
        self.assertIn("Inclusion list", text)
        self.assertIn("Exclusion list", text)
        self.assertIn("HDF5: whitelist/0", text)
        self.assertIn("HDF5: metadata/blacklists/0", text)
        self.assertIn("Exclusion-list rule metadata", text)
        self.assertEqual(summary.policy_view_counts[0][0], "whitelist")

    def test_cli_help_uses_new_prose_and_preserves_flags(self):
        result = CliRunner().invoke(suggest_sanitization_cli, ["--help"], terminal_width=200)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("--custom-blacklist", result.output)
        self.assertIn("--enforce-embedded-blacklist", result.output)
        self.assertIn("--blacklist-suggestions", result.output)
        self.assertIn("inclusion-list findings", result.output)
        self.assertIn("exclusion-list findings", result.output)
        self.assertNotIn("whitelist findings", result.output)
        self.assertNotIn("blacklist findings", result.output)
        result = CliRunner().invoke(create_concept_id_dump, ["--help"], terminal_width=200)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("inclusion-list ('version')", result.output)
        self.assertIn("exclusion-list ('semantic')", result.output)


RELEASE_APP = '''
from types import SimpleNamespace
from unittest.mock import patch
import streamlit as st
from snomed_post_processing.gui.streamlit.sidebar import render_sidebar
from snomed_post_processing.gui.streamlit.sanitization_check_tab import render_sanitization_check_tab
with patch("streamlit.segmented_control", side_effect=lambda label, **kwargs: "Active release" if label == "Allowed replacement concepts" else kwargs["default"]):
    with patch("snomed_post_processing.gui.streamlit.sidebar.render_file_source_selector", return_value=SimpleNamespace(value=None)):
        inputs = render_sidebar()
    st.session_state["observed_mode"] = inputs.release_blacklist_mode
    st.session_state["critical_findings"] = []
    render_sanitization_check_tab(inputs)
'''


class PolicyTerminologyGuiTest(unittest.TestCase):
    def test_release_labels_and_modes(self):
        app = AppTest.from_string(RELEASE_APP).run()
        self.assertFalse(app.exception, str(app.exception))
        self.assertEqual(app.session_state["observed_mode"], "none")
        embedded = next(item for item in app.checkbox if item.label == "Enforce embedded HDF5 exclusion list")
        custom = next(item for item in app.checkbox if item.label == "Use custom exclusion-list rule file")
        embedded.check()
        custom.check().run()
        self.assertFalse(app.exception, str(app.exception))
        self.assertEqual(app.session_state["observed_mode"], "embedded+custom")
        self.assertTrue(any("Custom exclusion-list mode is selected" in item.value for item in app.warning))
        for kind in ("checkbox", "caption", "info", "warning"):
            for item in getattr(app, kind):
                text = item.label if kind == "checkbox" else item.value
                self.assertNotRegex(text.lower(), "whitelist|blacklist")


if __name__ == "__main__":
    unittest.main()
