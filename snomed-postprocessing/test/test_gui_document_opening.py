"""Document opening controls do not filter or discard review decisions."""
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from snomed_post_processing.gui.streamlit import sanitization_run_tab as tab

APP = '''
import streamlit as st
from test.test_automatic_conditions import suggestion, candidate
from snomed_post_processing.gui.streamlit.sanitization_run_tab import (
    _suggestions_to_review_rows, _render_document_review_sections, _document_reviewed_key,
)
st.session_state.setdefault(_document_reviewed_key("reviewed.txt"), True)
suggestions = [suggestion(0, document="choice.txt", candidates=[candidate("200"), candidate("300")]),
               suggestion(1, document="no-target.txt", candidates=[]),
               suggestion(2, document="reviewed.txt")]
rows = _suggestions_to_review_rows(suggestions)
st.session_state["test_decisions"] = _render_document_review_sections(rows)
'''


class DocumentOpeningTest(unittest.TestCase):
    def healthy(self, app):
        self.assertFalse(app.exception, str(app.exception))
        return app

    def button(self, app, label):
        return next(button for button in app.button if button.label == label)

    def opened(self, app):
        return {document: any(document in expander.label and expander.proto.expanded for expander in app.expander)
                for document in ("choice.txt", "no-target.txt", "reviewed.txt")}

    def test_buttons_have_individual_help_and_do_not_filter_documents(self):
        app = self.healthy(AppTest.from_string(APP).run())
        self.assertTrue(any("not filters" in caption.value for caption in app.caption))
        baseline = app.session_state["test_decisions"]
        expected = {
            "All": (True, True, True),
            "Unreviewed": (True, True, False),
            "Needs choice": (True, False, False),
            "No replacement": (False, True, False),
            "Collapse all": (False, False, False),
        }
        for label, flags in expected.items():
            with self.subTest(label=label):
                self.assertTrue(self.button(app, label).help)
                self.button(app, label).click().run()
                self.healthy(app)
                self.assertEqual(tuple(self.opened(app).values()), flags)
                self.assertEqual(app.session_state["test_decisions"], baseline)
                self.assertEqual(len(app.expander), 3)
        revision = app.session_state["sanitization_section_opening_revision"]
        self.button(app, "Collapse all").click().run()
        self.healthy(app)
        self.assertEqual(app.session_state["sanitization_section_opening_revision"], revision + 1)
        self.assertFalse(any(self.opened(app).values()))

    def test_saved_manual_choice_survives_expansion_changes_and_is_not_unresolved(self):
        app = self.healthy(AppTest.from_string(APP).run())
        select = app.selectbox[0]
        choice = next(value for value in select.options if value.startswith("300"))
        # AppTest exposes formatted labels; the underlying value is code + FSN.
        select.select_index(len(select.options) - 1)
        next(box for box in app.checkbox if box.label == "Apply this replacement").check()
        self.button(app, "Save choices").click().run()
        self.healthy(app)
        before = app.session_state["test_decisions"]
        selected = next(item for item in before if item["document"] == "choice.txt")
        self.assertTrue(selected["apply"])
        self.assertEqual(selected["replacement_code"], "300", choice)
        for label in ("Needs choice", "All", "Collapse all", "No replacement"):
            self.button(app, label).click().run()
            self.healthy(app)
            self.assertEqual(app.session_state["test_decisions"], before)
            if label == "Needs choice":
                self.assertFalse(self.opened(app)["choice.txt"])

    def test_needs_choice_checks_resolution_and_review_progress(self):
        row = {"#": 1, "_needs_choice": True, "Apply": False,
               "Suggested replacement": "200 — target", "Delete annotation": False, "Needs manual edit": False}
        state = {}
        with patch.object(tab.st, "session_state", state):
            self.assertTrue(tab._document_matches_focus("doc", [row], "Needs choice"))
            for field in ("Apply", "Delete annotation", "Needs manual edit"):
                self.assertFalse(tab._document_matches_focus("doc", [{**row, field: True}], "Needs choice"))
            state[tab._document_reviewed_key("doc")] = True
            self.assertFalse(tab._document_matches_focus("doc", [row], "Needs choice"))
            self.assertFalse(tab._document_matches_focus("doc", [row], "Unreviewed"))
            self.assertTrue(tab._document_matches_focus("doc", [row], "All"))

    def test_no_replacement_means_unselected_not_necessarily_no_candidates(self):
        row = {"Suggested replacement": tab.NO_REPLACEMENT_LABEL, "_valid_choices": ("200 — target",)}
        with patch.object(tab.st, "session_state", {}):
            self.assertTrue(tab._document_matches_focus("doc", [row], "No replacement"))
            self.assertFalse(tab._document_matches_focus("doc", [row], "Collapse all"))


if __name__ == "__main__":
    unittest.main()
