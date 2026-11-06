"""Reviewer-requested GUI defaults and persistence, without external services."""
import unittest

from streamlit.testing.v1 import AppTest

from snomed_post_processing.gui.sanitization_check_tab import DEFAULT_GUI_ASSOCIATION_TYPES
from snomed_post_processing.sanitization.models import (
    DEFAULT_ALLOWED_ASSOCIATION_TYPES,
    SUPPORTED_ASSOCIATION_TYPES,
)


APP = '''
from types import SimpleNamespace
from unittest.mock import patch
import streamlit as st
from snomed_post_processing.gui.sidebar import render_sidebar
from snomed_post_processing.gui.sanitization_check_tab import render_sanitization_check_tab

# AppTest's button-group serializer does not round-trip single-value segmented controls
# in the installed Streamlit version; these unrelated selectors stay at their defaults.
with patch("streamlit.segmented_control", side_effect=lambda *args, **kwargs: kwargs["default"]):
    with patch("snomed_post_processing.gui.sidebar.render_file_source_selector",
               return_value=SimpleNamespace(value=None)):
        inputs = render_sidebar()
    st.session_state["critical_findings"] = []
    render_sanitization_check_tab(inputs)
'''


class GuiReviewDefaultsTest(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_string(APP).run()
        self.assertFalse(self.app.exception, str(self.app.exception))

    def widget(self, kind, label):
        return next(widget for widget in getattr(self.app, kind) if widget.label == label)

    def test_fallbacks_enabled_and_lexical_minimum_zero(self):
        for label in (
            "Historical ancestor fallback",
            "Semantic BM25 fallback",
            "Include exclusion-list findings in BM25 fallback",
        ):
            self.assertTrue(self.widget("checkbox", label).value)
        self.assertEqual(self.widget("number_input", "Minimum lexical overlap ratio").value, 0.0)

    def test_gui_association_defaults_and_inline_descriptions(self):
        widget = self.widget("multiselect", "Allowed historical association types")
        expected = set(SUPPORTED_ASSOCIATION_TYPES) - {"MOVED_FROM", "REFERS_TO"}
        self.assertEqual(set(widget.value), expected)
        self.assertEqual(set(DEFAULT_GUI_ASSOCIATION_TYPES), expected)
        self.assertEqual(DEFAULT_ALLOWED_ASSOCIATION_TYPES, ("SAME_AS", "REPLACED_BY"))
        self.assertTrue(all(" — " in option for option in widget.options))
        self.assertFalse(any("Association type meanings" in item.value for item in self.app.markdown))
        self.assertFalse(any("explanations are listed below" in item.value for item in self.app.caption))

    def test_no_human_is_not_selected_by_default(self):
        self.assertEqual(
            self.widget("text_area", "Ignore faulty target annotations overlapping these types").value,
            "",
        )

    def test_explicit_settings_survive_form_submission_and_rerun(self):
        self.widget("checkbox", "Historical ancestor fallback").uncheck()
        self.widget("checkbox", "Semantic BM25 fallback").uncheck()
        self.widget("checkbox", "Include exclusion-list findings in BM25 fallback").uncheck()
        self.widget("number_input", "Minimum lexical overlap ratio").set_value(0.35)
        self.widget("multiselect", "Allowed historical association types").set_value([])
        self.widget("text_area", "Ignore faulty target annotations overlapping these types").set_value(
            "webanno.custom.No_Human"
        )
        self.widget("button", "Apply suggestion settings").click().run()
        self.app.run()
        self.assertFalse(self.app.exception, str(self.app.exception))
        for label in (
            "Historical ancestor fallback",
            "Semantic BM25 fallback",
            "Include exclusion-list findings in BM25 fallback",
        ):
            self.assertFalse(self.widget("checkbox", label).value)
        self.assertEqual(self.widget("number_input", "Minimum lexical overlap ratio").value, 0.35)
        self.assertEqual(self.widget("multiselect", "Allowed historical association types").value, [])
        self.assertTrue(any("historical associations none" in item.value for item in self.app.info))
        self.assertEqual(
            self.widget("text_area", "Ignore faulty target annotations overlapping these types").value,
            "webanno.custom.No_Human",
        )


if __name__ == "__main__":
    unittest.main()
