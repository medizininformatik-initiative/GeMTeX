"""Large tie groups stay searchable without auto-selecting a replacement."""
import dataclasses
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from test.test_bm25_ties import write_tied_hdf5, finding
from snomed_post_processing.gui.streamlit.sanitization_run_tab import (
    NO_REPLACEMENT_LABEL, _browser_identity, _stage_browser_selection,
    _candidate_ranks, _replacement_options_and_hints,
)
from snomed_post_processing.sanitization.semantic_bm25 import SemanticBm25Resolver


APP = '''
import streamlit as st
from snomed_post_processing.gui.streamlit.sanitization_run_tab import (
    _suggestions_to_review_rows, _render_manual_choice_cards, _restore_decision_state,
)
if st.session_state.get("restore"):
    _restore_decision_state(st.session_state.pop("restore"), {})
rows = _suggestions_to_review_rows(st.session_state["sanitization_suggestions"])
st.session_state["rows"] = rows
st.session_state["sanitization_review_decisions"] = _render_manual_choice_cards(rows, "doc.txt")
'''


class GuiBm25BrowserTest(unittest.TestCase):
    def setUp(self):
        # Streamlit otherwise shows this warning only once per process, hiding regressions.
        warning_state = patch("streamlit.elements.lib.policies._shown_default_value_warning", False)
        warning_state.start()
        self.addCleanup(warning_state.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = pathlib.Path(directory.name) / "concepts.hdf5"
        self.codes = write_tied_hdf5(path)
        with SemanticBm25Resolver(path, max_candidates=5, min_score=0, min_lexical_score=0, allow_blacklist_findings=True) as resolver:
            self.suggestion = resolver.suggest(finding())
        self.app = self.new_app(self.suggestion)

    def new_app(self, suggestion, restore=None):
        app = AppTest.from_string(APP)
        app.session_state["sanitization_suggestions"] = [suggestion]
        if restore:
            app.session_state["restore"] = restore
        app.run()
        self.healthy(app)
        return app

    def healthy(self, app=None):
        app = app if app is not None else self.app
        self.assertFalse(app.exception, str(app.exception))
        self.assertFalse(any("default value" in item.value and "Session State API" in item.value
                             for item in app.warning), [item.value for item in app.warning])

    def button(self, label):
        return next(item for item in self.app.button if item.label == label)

    def pending_key(self):
        return _browser_identity(self.app.session_state["rows"][0]) + "_selected_code"

    def test_large_tie_has_no_default_and_scrollable_read_only_browser(self):
        self.assertEqual(self.app.selectbox[0].value, NO_REPLACEMENT_LABEL)
        self.assertEqual(len(self.app.selectbox[0].options), 1)
        self.assertFalse(self.app.checkbox[-1].value)
        self.assertTrue(self.button("Use selected candidate").disabled)
        browser = self.app.expander[0]
        self.assertFalse(browser.proto.expanded)
        self.assertEqual(len(browser.dataframe[0].value), 12)
        self.assertEqual(set(browser.dataframe[0].value["Rank"]), {1})
        _, hints = _replacement_options_and_hints(self.suggestion)
        self.assertTrue(all(hint.startswith("rank #1 ·") for hint in hints.values()))
        self.assertEqual(browser.dataframe[0].proto.selection_mode, [0])  # single row
        self.assertTrue(any("No clear lexical leader" in item.value for item in self.app.info))

    def test_pick_beyond_first_five_filter_save_and_restore_by_sctid(self):
        code = self.codes[-1]
        # Simulate the table's selection callback; its index-to-code mapping is separately tested below.
        self.app.session_state[self.pending_key()] = code
        self.app.run()
        self.button("Use selected candidate").click().run()
        self.healthy()
        self.assertTrue(self.app.selectbox[0].value.startswith(code + " —"))
        self.assertEqual(len(self.app.selectbox[0].options), 2)
        self.assertFalse(self.app.session_state["sanitization_review_decisions"][0]["apply"])
        self.app.text_input[0].set_value("word0").run()
        self.healthy()
        self.assertEqual(self.app.session_state[self.pending_key()], code)
        self.assertTrue(self.app.selectbox[0].value.startswith(code + " —"))
        self.button("Save choices").click().run()
        self.healthy()
        saved = self.app.session_state["sanitization_review_decisions"]
        self.assertEqual(saved[0]["replacement_code"], code)
        self.assertTrue(saved[0]["apply"])
        self.assertTrue(saved[0]["reviewed_by_human"])
        restored = self.new_app(self.suggestion, restore=saved)
        self.assertEqual(restored.session_state["sanitization_review_decisions"][0]["replacement_code"], code)
        self.assertTrue(restored.session_state["sanitization_review_decisions"][0]["apply"])
        # Changing an already-applied choice stages the new code without applying it before Save.
        self.app.session_state[self.pending_key()] = self.codes[0]
        self.app.run()
        self.button("Use selected candidate").click().run()
        self.healthy()
        self.assertFalse(self.app.session_state["sanitization_review_decisions"][0]["apply"])
        self.button("Save choices").click().run()
        self.healthy()
        self.assertEqual(self.app.session_state["sanitization_review_decisions"][0]["replacement_code"], self.codes[0])
        self.assertTrue(self.app.session_state["sanitization_review_decisions"][0]["apply"])

    def test_restored_action_checkboxes_use_state_without_duplicate_defaults(self):
        previous = self.app.session_state["sanitization_review_decisions"][0]
        for action, label in (("delete", "Delete this annotation"), ("manual_edit", "Needs manual edit")):
            with self.subTest(action=action):
                decision = dict(previous, action=action, apply=False,
                                delete_annotation=action == "delete", manual_edit=action == "manual_edit")
                restored = self.new_app(self.suggestion, restore=[decision])
                self.assertTrue(next(item for item in restored.checkbox if item.label == label).value)
                self.healthy(restored)

    def test_equal_scores_share_competition_rank_not_rounded_display_rank(self):
        candidates = tuple(dataclasses.replace(item, score=score) for item, score in zip(
            self.suggestion.candidates, (12, 12 - 1e-10, 7.1111112, 7.1111111)))
        self.assertEqual(_candidate_ranks(candidates), [1, 1, 3, 4])
        suggestion = dataclasses.replace(self.suggestion, candidates=candidates)
        options, hints = _replacement_options_and_hints(suggestion)
        self.assertEqual([hints[option].split(" ·")[0] for option in options], ["rank #1", "rank #1", "rank #3", "rank #4"])
        # A filtered view keeps the ranks from the complete saved candidate list.
        app = self.new_app(self.suggestion)
        app.text_input[0].set_value(self.codes[-1]).run()
        self.healthy(app)
        self.assertEqual(app.dataframe[0].value["Rank"].tolist(), [1])

    def test_callback_uses_rendered_snapshot_not_current_filter_positions(self):
        state = {"old_table": {"selection": {"rows": [1]}}}
        with patch("streamlit.session_state", state):
            _stage_browser_selection("old_table", ("1001", "1011"), "pending")
        self.assertEqual(state["pending"], "1011")
        self.assertEqual(_browser_identity(self.app.session_state["rows"][0]),
                         _browser_identity(dict(self.app.session_state["rows"][0], **{"#": 99})))

    def test_empty_filter_and_stale_or_diagnostic_code_cannot_be_used(self):
        self.app.session_state[self.pending_key()] = "not-selectable"
        self.app.text_input[0].set_value("no-match").run()
        self.healthy()
        self.assertTrue(self.button("Use selected candidate").disabled)
        self.assertTrue(any("No saved candidates" in item.value for item in self.app.info))
        self.assertEqual(self.app.selectbox[0].value, NO_REPLACEMENT_LABEL)

    def test_small_ties_keep_dropdown_and_retrieval_limits_are_visible(self):
        small = dataclasses.replace(self.suggestion, candidates=self.suggestion.candidates[:3], candidate_count=3)
        app = self.new_app(small)
        self.assertFalse(app.expander)
        self.assertEqual(len(app.selectbox[0].options), 4)
        self.assertEqual(app.selectbox[0].value, NO_REPLACEMENT_LABEL)
        limited = dataclasses.replace(self.suggestion, retrieval_limits=("SNOGIT hit limit",))
        app = self.new_app(limited)
        self.assertTrue(any("At least " in item.value for item in app.info))
        self.assertTrue(any("additional candidates may exist" in item.value for item in app.warning))


if __name__ == "__main__":
    unittest.main()
