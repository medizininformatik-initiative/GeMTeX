"""One annotator selection governs checking, rules, review and both write-back routes."""
import dataclasses
import io
import json
import unittest
import zipfile
from unittest.mock import patch

import cassis
import h5py
import numpy as np
from streamlit.testing.v1 import AppTest

from test import test_concept_rules as fixtures
from test.test_automatic_conditions import suggestion, decision
from snomed_post_processing.findings_io import read_critical_findings_json_with_metadata
from snomed_post_processing.gui.streamlit.annotator_scope import sync_annotator_scope, reset_generic_review_for_new_suggestions
from snomed_post_processing.gui.streamlit import sanitization_run_tab as run_tab
from snomed_post_processing.gui.streamlit.sanitization_run_tab import _suggestions_to_review_rows, _restore_decision_state
from snomed_post_processing.pipelines.inception_apply_upload import apply_decisions_and_upload_to_inception
from snomed_post_processing.pipelines.inception_upload_artifacts import build_inception_upload_artifacts
from snomed_post_processing.pipelines.sanitization_run import run_sanitization
from snomed_post_processing.sanitization.decisions_json import sanitization_decisions_json_text
from snomed_post_processing.uima_processing.scope import annotator_in_scope, normalize_annotators, scope_covers


APP = '''
from unittest.mock import patch
import streamlit as st
from snomed_post_processing.gui.streamlit.sidebar import GuiInputs
from snomed_post_processing.gui.streamlit.policy_tab import render_policy_tab
from snomed_post_processing.gui.streamlit.sanitization_check_tab import render_sanitization_check_tab
from snomed_post_processing.gui.streamlit.sanitization_run_tab import render_sanitization_run_tab
from snomed_post_processing.sanitization.models import SanitizationSuggestion, SanitizationStatus
from snomed_post_processing.pipelines.sanitization_run import run_sanitization
inputs = GuiInputs(
    load_annotators=True, hdf5_file=st.session_state["test_hdf5"], annotation_types_text="gemtex.Concept",
    ignore_overlap_types_text="", ignore_overlap_mode="overlap", id_prefix="http://snomed.info/id/", id_feature="id",
    data_dir=st.session_state["test_root"], annotators=tuple(st.session_state.get("processing_annotators", ())),
)
def suggest_all(findings):
    st.session_state["test_suggestion_annotators"] = [item.annotator for item in findings]
    return [SanitizationSuggestion(item, SanitizationStatus.NO_HISTORICAL_ASSOCIATION) for item in findings]
def write_local(*args, **kwargs):
    st.session_state["test_local_filter"] = kwargs.get("annotator_filter")
    st.session_state["test_local_output"] = args[2]
    return run_sanitization(*args, **kwargs)
with patch("streamlit.segmented_control", side_effect=lambda *args, **kwargs: kwargs["default"]), \\
     patch("streamlit.pills", side_effect=lambda *args, **kwargs: kwargs["default"]), \\
     patch("snomed_post_processing.gui.streamlit.sanitization_check_tab.SanitizationResolver") as structured, \\
     patch("snomed_post_processing.gui.streamlit.sanitization_run_tab.run_sanitization", side_effect=write_local):
    structured.return_value.suggest_all.side_effect = suggest_all
    check, suggest, review = st.tabs(["Check", "Suggest", "Review"])
    with check:
        render_policy_tab(inputs)
    with suggest:
        render_sanitization_check_tab(inputs)
    with review:
        render_sanitization_run_tab(inputs)
'''


class AnnotatorScopeTest(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.ConceptRulesTest("test_defaults_and_rule_json_roundtrip")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        # Number/Date should be policy findings, while explicit rules can still override the target policy.
        with h5py.File(fixture.hdf5, "a") as h:
            del h["policy_views/whitelist/0/concept_index"]
            h["policy_views/whitelist/0"].create_dataset("concept_index", data=np.array([3]))

    def app(self):
        app = AppTest.from_string(APP)
        app.session_state["zip_file"] = self.fixture.project
        app.session_state["test_hdf5"] = self.fixture.hdf5
        app.session_state["test_root"] = self.fixture.root
        app.run()
        self.healthy(app)
        return app

    def healthy(self, app):
        self.assertFalse(app.exception, str(app.exception))

    def widget(self, app, kind, label):
        return next(item for item in getattr(app, kind) if item.label == label)

    def choose_alice(self, app):
        self.widget(app, "multiselect", "Select annotators to include").set_value(["alice"]).run()
        self.healthy(app)

    def test_case_insensitive_scope_and_coverage(self):
        scope = normalize_annotators([" ALICE ", "alice"])
        self.assertEqual(scope, ("alice",))
        self.assertTrue(annotator_in_scope("Alice", scope))
        self.assertFalse(annotator_in_scope("bob", scope))
        self.assertTrue(annotator_in_scope("bob", ()))
        self.assertTrue(scope_covers((), scope))
        self.assertFalse(scope_covers(scope, ()))
        self.assertFalse(scope_covers(scope, ("bob",)))

    def test_policy_check_and_suggestions_share_the_selected_annotators(self):
        app = self.app()
        self.choose_alice(app)
        self.widget(app, "button", "Run policy check").click().run()
        self.healthy(app)
        self.assertEqual(app.session_state["policy_check_result"]["annotators"], ["alice"])
        findings = app.session_state["critical_findings"]
        self.assertEqual(len(findings), 4)
        self.assertEqual({item.annotator for item in findings}, {"alice"})
        _, metadata = read_critical_findings_json_with_metadata(io.StringIO(app.session_state["critical_findings_json_text"]))
        self.assertEqual(metadata["annotators"], ["alice"])
        # Also exercise the generation boundary with an out-of-scope imported/session finding.
        app.session_state["critical_findings"] = findings + [dataclasses.replace(findings[0], annotator="bob")]
        self.widget(app, "checkbox", "Semantic BM25 fallback").uncheck()
        self.widget(app, "button", "Apply suggestion settings").click().run()
        self.widget(app, "button", "Generate sanitization suggestions").click().run()
        self.healthy(app)
        self.assertEqual(set(app.session_state["test_suggestion_annotators"]), {"alice"})
        self.assertEqual(app.session_state["sanitization_suggestions_metadata"]["annotators"], ["alice"])
        self.widget(app, "multiselect", "Select annotators to include").set_value([]).run()
        self.healthy(app)
        self.assertTrue(any("narrower annotator scope" in item.value for item in app.warning))
        self.assertTrue(any("Run the policy check again" in item.value for item in app.warning))

    def test_rules_review_and_local_writeback_do_not_touch_excluded_bob(self):
        app = self.app()
        source = self.fixture.project.read_bytes()
        self.choose_alice(app)
        self.widget(app, "button", "Apply rules to review").click().run()
        self.healthy(app)
        rules = app.session_state["concept_rule_decisions"]
        self.assertEqual(len(rules), 4)
        self.assertEqual({item["annotator"] for item in rules}, {"alice"})
        review = next(item for item in app.dataframe if "Policy actually overridden" in item.value.columns)
        self.assertEqual(set(review.value["Annotator"]), {"alice"})
        self.widget(app, "button", "Run sanitization").click().run()
        self.healthy(app)
        self.assertEqual(app.session_state["test_local_filter"], {"alice"})
        with zipfile.ZipFile(self.fixture.project) as before, zipfile.ZipFile(app.session_state["test_local_output"]) as after:
            self.assertEqual(before.read("annotation/one.txt/bob.xmi"), after.read("annotation/one.txt/bob.xmi"))
            changed = cassis.load_cas_from_json(after.read("annotation/one.txt/alice.json").decode(), typesystem=self.fixture.ts)
            self.fixture.assert_features_preserved(changed)
        self.assertEqual(self.fixture.project.read_bytes(), source)
        # Broadening scope cannot silently reuse the narrower rule scan.
        self.widget(app, "multiselect", "Select annotators to include").set_value([]).run()
        self.healthy(app)
        self.assertTrue(any("Concept-rule inputs changed" in item.value for item in app.error))

    def test_uploaded_artifacts_and_dry_run_honor_saved_scope(self):
        decisions = self.fixture.preview()
        path = self.fixture.root / "decisions.json"
        path.write_text(sanitization_decisions_json_text(decisions, metadata={"annotators": ["ALICE"]}), encoding="utf-8")
        result = apply_decisions_and_upload_to_inception(
            source_project=self.fixture.project, decisions_path=path, output_dir=self.fixture.root / "pipeline",
        )
        self.assertTrue(result.dry_run)
        self.assertEqual(result.decision_count, 4)
        self.assertEqual(result.artifacts_result.artifact_count, 2)
        self.assertEqual({item.source_annotator for item in result.artifacts_result.artifacts}, {"alice"})
        report = json.loads(result.pipeline_report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["decisions_metadata"]["annotators"], ["alice"])
        native = build_inception_upload_artifacts(self.fixture.project, decisions, self.fixture.root / "native", annotator_filter=["Alice"])
        self.assertEqual(native.artifact_count, 2)
        self.assertFalse(native.unmatched_decisions)

    def test_context_extraction_and_cache_are_scoped(self):
        state = {}
        loader = run_tab._load_cas_from_zip_member
        with patch("streamlit.session_state", state), patch.object(run_tab, "_load_cas_from_zip_member", wraps=loader) as load:
            alice = run_tab._project_document_text_lookup(self.fixture.project, annotators=("alice",))
            self.assertIn("two.txt", alice)
            self.assertTrue(all("alice." in call.args[1] for call in load.call_args_list))
            load.reset_mock()
            bob = run_tab._project_document_text_lookup(self.fixture.project, annotators=("bob",))
            self.assertIn("one.txt", bob)
            self.assertNotIn("two.txt", bob)
            self.assertTrue(load.called)
            self.assertTrue(all("bob." in call.args[1] for call in load.call_args_list))
            load.reset_mock()
            run_tab._project_document_text_lookup(self.fixture.project, annotators=("bob",))
            load.assert_not_called()

    def test_local_pipeline_filter_also_filters_decision_counts(self):
        decisions = self.fixture.preview()
        output = self.fixture.root / "local.zip"
        result = run_sanitization(self.fixture.project, decisions, output, annotator_filter={"ALICE"})
        self.assertEqual(result.decision_count, 4)
        self.assertFalse(result.unmatched_decisions)
        with zipfile.ZipFile(self.fixture.project) as before, zipfile.ZipFile(output) as after:
            self.assertEqual(before.read("annotation/one.txt/bob.xmi"), after.read("annotation/one.txt/bob.xmi"))

    def test_scope_changes_preserve_indices_and_never_restore_excluded_selections(self):
        suggestions = [dataclasses.replace(suggestion(i), finding=dataclasses.replace(suggestion(i).finding, annotator=name))
                       for i, name in enumerate(("alice", "bob", "alice"))]
        decisions = [dict(decision(item, i), apply=True, reviewed_by_human=True) for i, item in enumerate(suggestions)]
        state = {"processing_annotators": (), "sanitization_suggestions": suggestions,
                 "sanitization_review_decisions": decisions,
                 "sanitization_restored_decisions_by_index": {i: item for i, item in enumerate(decisions)},
                 "sanitization_manual_apply_2": True, "sanitization_replacement_choice_2": "999",
                 "sanitization_conditions_undo": {"old": True}, "sanitization_document_reviewed_doc_txt": True}
        with patch("streamlit.session_state", state), patch("streamlit.sidebar.info"):
            sync_annotator_scope(["Alice"])
            rows = _suggestions_to_review_rows(suggestions, annotators=("alice",))
            self.assertEqual([row["#"] for row in rows], [1, 3])
            self.assertEqual([item["suggestion_index"] for item in state["sanitization_review_decisions"]], [0, 2])
            self.assertNotIn("sanitization_manual_apply_2", state)
            self.assertNotIn("sanitization_conditions_undo", state)
            sync_annotator_scope(())
            self.assertNotIn("sanitization_manual_apply_2", state)
            self.assertTrue(all(item["annotator"] == "alice" for item in state["sanitization_review_decisions"]))
            _restore_decision_state(decisions, {"reviewed_documents": ["missing.txt"]}, annotators=("alice",))
            self.assertEqual(set(state["sanitization_restored_decisions_by_index"]), {0, 2})
            self.assertNotIn("sanitization_document_reviewed_missing_txt", state)
            state["sanitization_suggestions"] = [suggestions[0], suggestions[2]]
            with self.assertRaisesRegex(ValueError, "matching suggestions JSON"):
                _restore_decision_state(decisions, {}, annotators=("alice",))

    def test_different_suggestions_reset_generic_state_without_dropping_rule_choices(self):
        old, new = [suggestion(0)], [suggestion(1)]
        rule = {"concept_rule": {"rule_id": "test"}, "annotator": "alice"}
        state = {"sanitization_suggestions": old, "sanitization_manual_apply_1": True,
                 "sanitization_review_decisions": [dict(decision(old[0], 0), apply=True), rule]}
        with patch("streamlit.session_state", state), patch("streamlit.warning") as warning:
            reset_generic_review_for_new_suggestions(new)
        self.assertNotIn("sanitization_manual_apply_1", state)
        self.assertEqual(state["sanitization_review_decisions"], [rule])
        warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
