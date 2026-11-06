"""Concept-rule form and rule-only review, without network or CAS write actions."""
import dataclasses
import unittest

from streamlit.testing.v1 import AppTest

from test import test_concept_rules as fixtures
from snomed_post_processing.gui.concept_rules import _rules_from_editor, ACTION_LABELS
from snomed_post_processing.sanitization.concept_rules import DEFAULT_CONCEPT_RULES, rules_json_text
from snomed_post_processing.sanitization.models import SanitizationSuggestion, SanitizationStatus
from snomed_post_processing.uima_processing import CriticalFinding


APP = '''
import io
from unittest.mock import patch
import streamlit as st
from snomed_post_processing.gui.sidebar import GuiInputs
from snomed_post_processing.gui.concept_rules import render_concept_rules_form
from snomed_post_processing.gui.sanitization_run_tab import render_sanitization_run_tab, _restore_decision_state
inputs = GuiInputs(
    load_annotators=False, hdf5_file=st.session_state["test_hdf5"],
    annotation_types_text=st.session_state.get("test_annotation_types", "gemtex.Concept"), ignore_overlap_types_text="",
    ignore_overlap_mode="overlap", id_prefix="http://snomed.info/id/", id_feature="id",
    data_dir=st.session_state["test_root"],
)
if st.session_state.get("test_restore"):
    decisions, metadata = st.session_state.pop("test_restore")
    _restore_decision_state(decisions, metadata)
original_uploader = st.file_uploader
def uploader(*args, **kwargs):
    if kwargs.get("key") == "concept_rules_upload" and st.session_state.get("test_rule_upload"):
        return io.BytesIO(st.session_state["test_rule_upload"].encode())
    return original_uploader(*args, **kwargs)
original_editor = st.data_editor
def editor(data, **kwargs):
    result = original_editor(data, **kwargs)
    if str(kwargs.get("key", "")).startswith("concept_rule_review_editor") and st.session_state.get("test_rule_edit"):
        result = result.copy()
        result.loc[0, "Apply"] = False
    return result
with patch("streamlit.segmented_control", side_effect=lambda *args, **kwargs: kwargs["default"]), \\
     patch("streamlit.pills", side_effect=lambda *args, **kwargs: kwargs["default"]), \\
     patch("streamlit.data_editor", side_effect=editor), \\
     patch("streamlit.file_uploader", side_effect=uploader):
    render_concept_rules_form(inputs)
    render_sanitization_run_tab(inputs)
'''


class GuiConceptRulesTest(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.ConceptRulesTest("test_defaults_and_rule_json_roundtrip")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.app = AppTest.from_string(APP)
        self.app.session_state["test_hdf5"] = fixture.hdf5
        self.app.session_state["test_root"] = fixture.root
        self.app.session_state["zip_file"] = fixture.project
        self.app.run()
        self.assertHealthy()

    def assertHealthy(self):
        self.assertFalse(self.app.exception, str(self.app.exception))

    def widget(self, kind, label):
        return next(item for item in getattr(self.app, kind) if item.label == label)

    def apply_rules(self):
        self.widget("button", "Apply rules to review").click().run()
        self.assertHealthy()
        self.assertEqual(len(self.app.session_state["concept_rule_decisions"]), 6)

    def test_form_default_boolean_and_action_roundtrip(self):
        rows = [{**dataclasses.asdict(rule), "action": ACTION_LABELS[rule.action]} for rule in DEFAULT_CONCEPT_RULES]
        self.assertEqual(_rules_from_editor(rows), DEFAULT_CONCEPT_RULES)
        rows[1]["override_policy"] = False
        self.assertFalse(_rules_from_editor(rows)[1].override_policy)
        # Confirm the form is present before any suggestions/findings exist.
        self.assertFalse(self.widget("button", "Apply rules to review").disabled)
        container = next(item for item in self.app.expander if item.label == "Concept rules")
        self.assertFalse(container.proto.expanded)
        self.assertEqual([item.label for item in container.button], ["Apply rules to review"])
        self.assertFalse(any(item.label.startswith("Rule ") for item in self.app.text_area))

    def test_upload_loads_configuration_once_without_applying_rules(self):
        source = self.fixture.project.read_bytes()
        self.app.session_state["test_rule_upload"] = rules_json_text(DEFAULT_CONCEPT_RULES[:1])
        self.app.run()
        self.assertHealthy()
        self.assertEqual(self.app.session_state["concept_rules"], DEFAULT_CONCEPT_RULES[:1])
        self.assertNotIn("concept_rule_decisions", self.app.session_state.filtered_state)
        self.assertEqual(self.fixture.project.read_bytes(), source)
        self.widget("button", "Apply rules to review").click().run()
        self.assertHealthy()
        self.assertEqual(len(self.app.session_state["concept_rule_decisions"]), 3)
        # The same uploaded JSON must not reset subsequent configuration edits on reruns.
        self.app.session_state["concept_rules"] = DEFAULT_CONCEPT_RULES
        self.app.run()
        self.assertHealthy()
        self.assertEqual(self.app.session_state["concept_rules"], DEFAULT_CONCEPT_RULES)

    def test_rule_only_review_is_selected_persists_and_undoes(self):
        source = self.fixture.project.read_bytes()
        self.apply_rules()
        decisions = self.app.session_state["sanitization_review_decisions"]
        self.assertEqual(len(decisions), 6)
        self.assertTrue(all(item["apply"] and item["resolved"] for item in decisions))
        self.assertFalse(self.widget("button", "Run sanitization").disabled)
        self.app.run()
        self.assertHealthy()
        self.assertEqual(self.app.session_state["sanitization_review_decisions"], decisions)
        self.widget("button", "Undo concept rule decisions").click().run()
        self.assertHealthy()
        self.assertEqual(self.app.session_state["concept_rule_decisions"], [])
        self.assertTrue(self.widget("button", "Run sanitization").disabled)
        self.assertEqual(self.fixture.project.read_bytes(), source)

    def test_scope_change_blocks_stale_decisions_but_undo_remains_available(self):
        self.apply_rules()
        self.app.session_state["test_annotation_types"] = "gemtex.Concept\nwebanno.custom.Concept"
        self.app.run()
        self.assertHealthy()
        self.assertTrue(self.widget("button", "Run sanitization").disabled)
        self.assertTrue(any("inputs changed" in item.value for item in self.app.error))
        self.widget("button", "Undo concept rule decisions").click().run()
        self.assertHealthy()
        self.assertEqual(self.app.session_state["concept_rule_decisions"], [])

    def test_apply_uses_sidebar_layers_and_ignores_old_scope_filters(self):
        self.app.session_state["concept_rule_scope"] = {"layers": "absent.Layer", "documents": "one.txt", "annotators": "alice"}
        self.apply_rules()
        self.assertEqual(self.app.session_state["concept_rule_scope"], {
            "layers": "gemtex.Concept", "documents": "", "annotators": "",
        })

    def test_rule_only_decisions_restore_without_matching_suggestions(self):
        decisions = self.fixture.preview()
        self.app.session_state["test_restore"] = (decisions, {
            "concept_rules": [dataclasses.asdict(rule) for rule in DEFAULT_CONCEPT_RULES],
            "concept_rule_scope": {"layers": "gemtex.Concept", "documents": "", "annotators": ""},
            "reviewed_documents": ["one.txt", "two.txt"],
        })
        self.app.run()
        self.assertHealthy()
        self.assertEqual(self.app.session_state["sanitization_review_decisions"], decisions)
        self.assertFalse(self.widget("button", "Run sanitization").disabled)

    def test_undo_preserves_manually_edited_rule_choices(self):
        self.apply_rules()
        self.app.session_state["test_rule_edit"] = True
        self.widget("button", "Save rule decisions").click().run()
        self.assertHealthy()
        self.assertTrue(self.app.session_state["concept_rule_decisions"][0]["rule_reviewed_by_human"])
        self.app.session_state["test_rule_edit"] = False
        self.widget("button", "Undo concept rule decisions").click().run()
        self.assertHealthy()
        retained = self.app.session_state["concept_rule_decisions"]
        self.assertEqual(len(retained), 1)
        self.assertFalse(retained[0]["apply"])
        self.assertTrue(retained[0]["rule_reviewed_by_human"])
        self.widget("button", "Apply rules to review").click().run()
        self.assertHealthy()
        self.assertEqual(len(self.app.session_state["concept_rule_decisions"]), 6)
        self.assertEqual(sum(not item["apply"] for item in self.app.session_state["concept_rule_decisions"]), 1)

    def test_rule_overrides_generic_fallback_without_duplicate_decisions(self):
        decision = self.fixture.preview()[1]
        finding = CriticalFinding(
            document=decision["document"], annotator=decision["annotator"],
            layer=decision["layer"], offset=tuple(decision["offset"]),
            code=decision["source_code"], covered_text=decision["covered_text"],
            list_type="whitelist", reason="not_in_whitelist",
        )
        self.app.session_state["sanitization_suggestions"] = [SanitizationSuggestion(
            finding=finding, status=SanitizationStatus.HISTORICAL_ASSOCIATION_REPLACEMENT,
            replacement_code="999", replacement_fsn="Unwanted generic fallback",
        )]
        self.app.run()
        self.assertHealthy()
        self.apply_rules()
        decisions = self.app.session_state["sanitization_review_decisions"]
        self.assertEqual(len(decisions), 6)
        self.assertFalse(any(item.get("replacement_code") == "999" for item in decisions))

    def test_failed_application_preserves_previous_decisions_and_blocks_export(self):
        self.apply_rules()
        previous = self.app.session_state["concept_rule_decisions"]
        self.fixture.write_hdf5(target_active=False)
        self.widget("button", "Apply rules to review").click().run()
        self.assertHealthy()
        self.assertEqual(self.app.session_state["concept_rule_decisions"], previous)
        self.assertTrue(any("must exist and be active" in item.value for item in self.app.error))
        self.assertTrue(self.widget("button", "Run sanitization").disabled)

    def test_loaded_rules_revalidate_target_activity(self):
        decisions = self.fixture.preview()
        self.fixture.write_hdf5(target_active=False)
        self.app.session_state["test_restore"] = (decisions, {
            "concept_rules": [dataclasses.asdict(rule) for rule in DEFAULT_CONCEPT_RULES],
        })
        self.app.run()
        self.assertHealthy()
        self.assertTrue(any("must exist and be active" in item.value for item in self.app.error))
        self.assertTrue(self.widget("button", "Run sanitization").disabled)

    def test_loaded_id_settings_apply_before_sidebar_widgets_on_rerun(self):
        app = AppTest.from_string('''
from types import SimpleNamespace
from unittest.mock import patch
import streamlit as st
from snomed_post_processing.gui.sidebar import render_sidebar
from snomed_post_processing.gui.sanitization_run_tab import _restore_decision_state
with patch("streamlit.segmented_control", side_effect=lambda *args, **kwargs: kwargs["default"]), \\
     patch("snomed_post_processing.gui.sidebar.render_file_source_selector", return_value=SimpleNamespace(value=None)):
    inputs = render_sidebar()
if st.button("Restore ID settings"):
    _restore_decision_state([], {"id_prefix": "", "id_feature": "conceptId"})
    st.rerun()
st.session_state["observed_ids"] = (inputs.id_prefix, inputs.id_feature)
''').run()
        self.assertFalse(app.exception, str(app.exception))
        next(item for item in app.button if item.label == "Restore ID settings").click().run()
        self.assertFalse(app.exception, str(app.exception))
        self.assertEqual(app.session_state["observed_ids"], ("", "conceptId"))

    def test_explicit_keep_is_protected_from_rule_acceptance(self):
        decisions = self.fixture.preview()
        manual = {**decisions[0], "concept_rule": None, "action": "none", "apply": False, "reviewed_by_human": True}
        self.app.session_state["sanitization_restored_decisions_by_index"] = {0: manual}
        self.apply_rules()
        self.assertTrue(any("conflict with manual decisions" in item.value for item in self.app.error))
        self.assertTrue(self.widget("button", "Run sanitization").disabled)
        self.widget("button", "Keep manual decisions for conflicts").click().run()
        self.assertHealthy()
        self.assertEqual(len(self.app.session_state["concept_rule_decisions"]), 5)


if __name__ == "__main__":
    unittest.main()
