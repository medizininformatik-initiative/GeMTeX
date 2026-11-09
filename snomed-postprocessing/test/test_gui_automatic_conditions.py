"""Conditional review actions, including widget persistence and safe undo."""
import dataclasses
import unittest

from streamlit.testing.v1 import AppTest

from test import test_concept_rules as fixtures
from test.test_gui_concept_rules import APP
from test.test_automatic_conditions import candidate, suggestion
from test.test_bm25_conditions import bm25_suggestion
from snomed_post_processing.gui.sanitization_run_tab import _document_reviewed_key


CONDITIONS_APP = APP.replace(
    '    return result\nwith patch',
    '''    number = st.session_state.get("test_generic_edit_row")
    if str(kwargs.get("key", "")).startswith("sanitization_review_editor_") and number is not None:
        result = result.copy()
        result.loc[result["#"] == number, "Apply"] = False
        if st.session_state.get("test_generic_delete"):
            result.loc[result["#"] == number, "Delete annotation"] = True
    return result
with patch''',
)


class GuiAutomaticConditionsTest(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.ConceptRulesTest("test_defaults_and_rule_json_roundtrip")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.source = fixture.project.read_bytes()
        self.suggestions = [
            suggestion(0, document="one.txt"),
            suggestion(1, document="one.txt", list_type="blacklist"),
            suggestion(2, document="two.txt"),
            suggestion(3, document="ambiguous.txt", candidates=[candidate(), candidate("300", "REPLACED_BY")]),
        ]
        self.app = AppTest.from_string(CONDITIONS_APP)
        self.app.session_state["test_hdf5"] = fixture.hdf5
        self.app.session_state["test_root"] = fixture.root
        self.app.session_state["zip_file"] = fixture.project
        self.app.session_state["sanitization_suggestions"] = self.suggestions
        self.app.run()
        self.healthy()

    def healthy(self):
        self.assertFalse(self.app.exception, str(self.app.exception))
        self.assertEqual(self.fixture.project.read_bytes(), self.source)

    def button(self, label):
        return next(item for item in self.app.button if item.label == label)

    def apply(self):
        self.button("Apply Conditions").click().run()
        self.healthy()

    def decisions(self):
        return {item["suggestion_index"]: item for item in self.app.session_state["sanitization_review_decisions"]}

    def test_conditions_replace_bulk_buttons_and_only_select_inclusion_historical_sources(self):
        labels = {item.label for item in self.app.button}
        self.assertFalse(any(label.startswith(("Apply all", "Apply first", "Clear all single", "Clear all manual", "Clear manual choices")) for label in labels))
        self.assertTrue(self.button("Undo Automatic Conditions").disabled)
        self.assertFalse(any(item["apply"] for item in self.decisions().values()))
        self.apply()
        decisions = self.decisions()
        self.assertEqual([decisions[i]["apply"] for i in range(4)], [True, False, True, False])
        self.assertTrue(decisions[0]["resolved"])
        self.assertFalse(decisions[0]["reviewed_by_human"])
        self.assertEqual(decisions[0]["automatic_condition"]["kind"], "historical_association")
        self.assertFalse(self.app.session_state[_document_reviewed_key("one.txt")])
        self.assertTrue(self.app.session_state[_document_reviewed_key("two.txt")])
        self.assertFalse(self.button("Undo Automatic Conditions").disabled)
        self.app.run()
        self.healthy()
        self.assertEqual(self.decisions(), decisions)

    def test_repeated_apply_retains_original_undo_and_restores_document_flags(self):
        self.apply()
        self.apply()
        self.button("Undo Automatic Conditions").click().run()
        self.healthy()
        self.assertFalse(any(item["apply"] for item in self.decisions().values()))
        self.assertFalse(self.app.session_state[_document_reviewed_key("two.txt")])
        self.assertTrue(self.button("Undo Automatic Conditions").disabled)

    def test_manual_checkbox_change_after_apply_is_not_overwritten_by_undo(self):
        self.apply()
        self.app.session_state["test_generic_edit_row"] = 1
        self.button("Save single/no-choice selections").click().run()
        self.healthy()
        self.app.session_state["test_generic_edit_row"] = None
        self.assertTrue(self.decisions()[0]["reviewed_by_human"])
        self.assertFalse(self.decisions()[0]["apply"])
        self.button("Undo Automatic Conditions").click().run()
        self.healthy()
        self.assertFalse(self.decisions()[0]["apply"])
        self.assertTrue(self.decisions()[0]["reviewed_by_human"])
        self.assertFalse(self.decisions()[2]["apply"])
        self.assertTrue(any("preserved 1" in item.value for item in self.app.info))

    def test_manual_deletion_before_apply_is_protected(self):
        self.app.session_state["test_generic_edit_row"] = 1
        self.app.session_state["test_generic_delete"] = True
        self.button("Save single/no-choice selections").click().run()
        self.healthy()
        self.app.session_state["test_generic_edit_row"] = None
        self.apply()
        self.assertEqual(self.decisions()[0]["action"], "delete")
        self.assertNotIn("automatic_condition", self.decisions()[0])
        self.assertTrue(self.decisions()[2]["apply"])

    def test_condition_can_select_nonfirst_target_and_undo_restores_dropdown(self):
        next(item for item in self.app.multiselect if item.label == "Historical association types").set_value(["REPLACED_BY"])
        self.apply()
        self.assertEqual(self.decisions()[3]["replacement_code"], "300")
        self.assertTrue(self.decisions()[3]["apply"])
        self.assertFalse(self.decisions()[0]["apply"])
        self.button("Undo Automatic Conditions").click().run()
        self.healthy()
        self.assertFalse(self.decisions()[3]["apply"])
        self.assertEqual(self.decisions()[3]["replacement_code"], "200")

    def test_changed_suggestions_clear_automatic_state_and_stale_undo(self):
        self.apply()
        changed = list(self.suggestions)
        changed[0] = dataclasses.replace(changed[0], finding=dataclasses.replace(changed[0].finding, code="different"))
        self.app.session_state["sanitization_suggestions"] = changed
        self.app.run()
        self.healthy()
        self.assertFalse(any(item["apply"] for item in self.decisions().values()))
        self.assertTrue(self.button("Undo Automatic Conditions").disabled)
        self.assertFalse(self.app.session_state[_document_reviewed_key("two.txt")])

    def test_restored_manual_keep_decisions_are_not_automatically_selected(self):
        self.app.session_state["test_restore"] = (list(self.decisions().values()), {})
        self.app.run()
        self.healthy()
        self.apply()
        self.assertFalse(any(item["apply"] for item in self.decisions().values()))

    def add_bm25(self, *items):
        self.app.session_state["sanitization_suggestions"] = self.suggestions + list(items)
        self.app.run()
        self.healthy()

    def enable_bm25(self):
        next(item for item in self.app.checkbox if item.label == "Enable BM25 automatic selection (heuristic)").check()

    def test_bm25_is_opt_in_and_shares_the_last_run_undo(self):
        self.add_bm25(bm25_suggestion([12, 7, 6, 5, 4], index=4))
        self.assertFalse(next(item for item in self.app.checkbox if item.label == "Enable BM25 automatic selection (heuristic)").value)
        self.apply()
        self.assertFalse(self.decisions()[4]["apply"])
        self.enable_bm25()
        self.apply()
        selected = self.decisions()[4]
        self.assertTrue(selected["apply"])
        self.assertEqual(selected["automatic_condition"]["candidate_count"], 5)
        self.assertEqual(selected["automatic_condition"]["kind"], "bm25_gap")
        self.assertTrue(self.app.session_state[_document_reviewed_key("bm25.txt")])
        self.apply()  # An identical run does not overwrite the last changing run.
        self.button("Undo Automatic Conditions").click().run()
        self.healthy()
        self.assertFalse(self.decisions()[4]["apply"])
        self.assertTrue(self.decisions()[0]["apply"])  # Earlier historical run is untouched.
        self.assertFalse(self.app.session_state[_document_reviewed_key("bm25.txt")])

    def test_all_bm25_gaps_and_threshold_controls_affect_selection(self):
        self.add_bm25(bm25_suggestion([12, 7, 6, 5, 4], index=4),
                      bm25_suggestion([12, 7, 6, 0], index=5, document="later-gap.txt"))
        next(item for item in self.app.multiselect if item.label == "Historical association types").set_value([])
        self.enable_bm25()
        self.apply()
        self.assertTrue(self.decisions()[4]["apply"])
        self.assertFalse(self.decisions()[5]["apply"])
        self.assertFalse(self.decisions()[0]["apply"])
        next(item for item in self.app.number_input if item.label == "Minimum BM25 gap dominance").set_value(0.4)
        self.apply()
        self.assertTrue(self.decisions()[5]["apply"])
        self.assertAlmostEqual(self.decisions()[5]["automatic_condition"]["dominance"], 5 / 11)
        self.button("Undo Automatic Conditions").click().run()
        self.healthy()
        self.assertTrue(self.decisions()[4]["apply"])
        self.assertFalse(self.decisions()[5]["apply"])
        self.assertAlmostEqual(self.decisions()[4]["automatic_condition"]["min_dominance"], 2 / 3)

    def test_exclusion_source_and_mixed_score_channels_stay_manual_with_bm25_enabled(self):
        mixed = bm25_suggestion(index=5, document="mixed.txt")
        mixed = dataclasses.replace(mixed, candidates=(mixed.candidates[0],
            dataclasses.replace(mixed.candidates[1], source="snogit", source_member="SNOGIT.dat"), mixed.candidates[2]))
        self.add_bm25(bm25_suggestion(index=4, list_type="blacklist"), mixed)
        self.enable_bm25()
        self.apply()
        self.assertFalse(self.decisions()[4]["apply"])
        self.assertFalse(self.decisions()[5]["apply"])
        self.assertTrue(any(item.label == "BM25 score-gap assessment" for item in self.app.expander))

    def test_saved_bm25_checkbox_edits_survive_undo(self):
        self.add_bm25(bm25_suggestion(index=4))
        self.enable_bm25()
        self.apply()
        self.app.session_state["test_generic_edit_row"] = 5
        document = next(item for item in self.app.expander if "bm25.txt" in item.label)
        next(item for item in document.button if item.label == "Save single/no-choice selections").click().run()
        self.healthy()
        self.app.session_state["test_generic_edit_row"] = None
        self.assertTrue(self.decisions()[4]["reviewed_by_human"])
        self.assertFalse(self.decisions()[4]["apply"])
        self.button("Undo Automatic Conditions").click().run()
        self.healthy()
        self.assertTrue(self.decisions()[4]["reviewed_by_human"])
        self.assertFalse(self.decisions()[4]["apply"])
        self.assertFalse(self.decisions()[0]["apply"])

    def test_restored_automatic_provenance_is_retained_without_old_undo_history(self):
        self.apply()
        saved = self.decisions()
        # Explicitly loading a saved state replaces later local progress too.
        self.app.session_state["test_generic_edit_row"] = 1
        self.button("Save single/no-choice selections").click().run()
        self.healthy()
        self.app.session_state["test_generic_edit_row"] = None
        self.assertTrue(self.decisions()[0]["reviewed_by_human"])
        self.app.session_state["test_restore"] = (list(saved.values()), {
            "reviewed_documents": ["two.txt"], "automatic_reviewed_documents": ["two.txt"],
        })
        self.app.run()
        self.healthy()
        self.assertEqual(self.decisions(), saved)
        self.assertTrue(self.button("Undo Automatic Conditions").disabled)


if __name__ == "__main__":
    unittest.main()
