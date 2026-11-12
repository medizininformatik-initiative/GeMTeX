"""The checked-in synthetic dataset exercises the real offline workflow."""
import collections
import json
import pathlib
import shutil
import tempfile
import unittest
import zipfile

import cassis
from streamlit.testing.v1 import AppTest

from test.create_synthetic_annotator_dataset import (
    ANNOTATORS, DOCUMENTS, LAYER, PREFIX, build_dataset, collect_findings, stage_decisions,
)
from snomed_post_processing.findings_io import read_critical_findings_json
from snomed_post_processing.pipelines.inception_upload_artifacts import build_inception_upload_artifacts
from snomed_post_processing.pipelines.sanitization_run import run_sanitization
from snomed_post_processing.sanitization import SanitizationResolver
from snomed_post_processing.sanitization.concept_rules import DEFAULT_CONCEPT_RULES, preview_concept_rules
from snomed_post_processing.sanitization.decisions_json import read_sanitization_decisions_json
from snomed_post_processing.sanitization.json_io import read_sanitization_suggestions_json
from snomed_post_processing.uima_processing import get_annotator_names

FIXTURE = pathlib.Path(__file__).parent / "projects" / "synthetic-annotator-scope"
APP = '''
from unittest.mock import patch
import streamlit as st
from snomed_post_processing.gui.sidebar import GuiInputs
from snomed_post_processing.gui.policy_tab import render_policy_tab
from snomed_post_processing.gui.sanitization_check_tab import render_sanitization_check_tab
from snomed_post_processing.gui.sanitization_run_tab import render_sanitization_run_tab
inputs = GuiInputs(load_annotators=True, hdf5_file=st.session_state["policy"],
    annotation_types_text="webanno.custom.Concept", ignore_overlap_types_text="",
    ignore_overlap_mode="overlap", id_prefix="http://snomed.info/id/", id_feature="id",
    data_dir=st.session_state["root"], annotators=tuple(st.session_state.get("processing_annotators", ())))
with patch("streamlit.segmented_control", side_effect=lambda *args, **kwargs: kwargs["default"]), \\
     patch("streamlit.pills", side_effect=lambda *args, **kwargs: kwargs["default"]):
    check, suggest, review = st.tabs(["Check", "Suggest", "Review"])
    with check:
        render_policy_tab(inputs)
    with suggest:
        render_sanitization_check_tab(inputs)
    with review:
        render_sanitization_run_tab(inputs)
'''


class SyntheticAnnotatorDatasetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.project = FIXTURE / "project.zip"
        self.policy = FIXTURE / "policy.hdf5"
        self.expected = json.loads((FIXTURE / "expected.json").read_text(encoding="utf-8"))

    def test_fresh_policy_check_reproduces_saved_findings(self):
        names, only_ser = get_annotator_names(self.project)
        self.assertEqual(names, set(ANNOTATORS))
        self.assertFalse(only_ser)
        findings = collect_findings(self.project, self.policy)
        self.assertEqual(findings, read_critical_findings_json(FIXTURE / "critical-findings.json"))
        self.assertEqual(len(findings), self.expected["critical_finding_count"])
        self.assertEqual(collections.Counter(f.list_type for f in findings), {"whitelist": 8, "blacklist": 2})
        self.assertEqual(collections.Counter(f.annotator for f in findings), {"alice": 5, "bob": 5})
        self.assertNotIn("410671006", {f.code for f in findings})  # included Date still matches a rule
        included = collect_findings(self.project, self.policy, ["alice"])
        self.assertEqual(len(included), self.expected["alice_only"]["critical_finding_count"])
        self.assertEqual({f.annotator for f in included}, {"alice"})

    def test_real_resolver_rules_and_conditions_match_saved_artifacts(self):
        findings = collect_findings(self.project, self.policy)
        suggestions = SanitizationResolver(self.policy).suggest_all(findings)
        self.assertEqual(suggestions, read_sanitization_suggestions_json(FIXTURE / "suggestions.json"))
        rules = preview_concept_rules(self.project, self.policy, DEFAULT_CONCEPT_RULES, annotation_types=[LAYER])
        self.assertEqual(len(rules), self.expected["rule_decision_count"])
        self.assertEqual(sum(d["policy_overridden"] for d in rules), self.expected["actual_policy_overrides"])
        result = stage_decisions(suggestions, rules)
        self.assertEqual(result.changed, self.expected["automatic_condition_selections"])
        self.assertEqual(result.reviewed_documents, {"automatic.txt"})
        saved, metadata = read_sanitization_decisions_json(FIXTURE / "staged-decisions.json")
        self.assertEqual(saved, result.decisions)
        self.assertEqual(metadata["annotators"], [])
        selected = [d for d in saved if d["apply"]]
        self.assertEqual(len(selected), self.expected["selected_decisions"])
        self.assertEqual({d["source_code"] for d in selected}, {"410680006", "410671006", "990000101"})
        automatic = [d for d in saved if d.get("automatic_condition")]
        self.assertEqual({d["replacement_code"] for d in automatic}, {"990000201"})
        self.assertTrue(all(not d["apply"] for d in saved if d["document"] == "manual-controls.txt"))

    def test_local_and_upload_writeback_preserve_features_and_scope(self):
        decisions, _ = read_sanitization_decisions_json(FIXTURE / "staged-decisions.json")
        original_bytes = self.project.read_bytes()
        for users, changed, artifact_count in ((None, 6, 6), ({"alice"}, 3, 3)):
            with self.subTest(users=users):
                folder = self.root / ("all" if users is None else "alice")
                folder.mkdir()
                output = folder / "sanitized.zip"
                local = run_sanitization(self.project, decisions, output, annotator_filter=users)
                self.assertEqual(local.changed_annotation_count, changed)
                self.assertFalse(local.unmatched_decisions)
                artifacts = build_inception_upload_artifacts(self.project, decisions, folder / "artifacts", annotator_filter=users)
                self.assertEqual(artifacts.artifact_count, artifact_count)
                self.assertEqual(sum(a.changed_annotation_count for a in artifacts.artifacts), changed)
                self.assertFalse(artifacts.unmatched_decisions)
                with zipfile.ZipFile(self.project) as before, zipfile.ZipFile(output) as after:
                    ts = cassis.load_typesystem(before.read("TypeSystem.xml").decode())
                    for user in ANNOTATORS:
                        for doc in DOCUMENTS:
                            member = f"annotation/{doc}/{user}.{'xmi' if user == 'bob' else 'json'}"
                            if users and user not in users:
                                self.assertEqual(before.read(member), after.read(member))
                                continue
                            load = cassis.load_cas_from_xmi if user == "bob" else cassis.load_cas_from_json
                            original = load(before.read(member).decode(), typesystem=ts)
                            rewritten = load(after.read(member).decode(), typesystem=ts)
                            self.assertEqual(original.sofa_string, rewritten.sofa_string)
                            self.assertEqual(collections.Counter(a.type.name for a in original.select_all()),
                                             collections.Counter(a.type.name for a in rewritten.select_all()))
                            old_annotations, new_annotations = list(original.select(LAYER)), list(rewritten.select(LAYER))
                            self.assertEqual(len(old_annotations), len(DOCUMENTS[doc][1]))
                            self.assertEqual(len(old_annotations), len(new_annotations))
                            replacements = {"410680006": None, "410671006": PREFIX + "410672004", "990000101": PREFIX + "990000201"}
                            for old, new in zip(old_annotations, new_annotations):
                                self.assertEqual((old.begin, old.end, old.literal, old.note), (new.begin, new.end, new.literal, new.note))
                                self.assertEqual(new.id, replacements.get(old.id.rsplit("/", 1)[-1], old.id))
                if users:
                    self.assertEqual({a.source_annotator for a in artifacts.artifacts}, users)
        self.assertEqual(self.project.read_bytes(), original_bytes)

    def test_generator_refuses_overwrite_and_creates_equivalent_data(self):
        destination = self.root / "new"
        self.assertEqual(build_dataset(destination), self.expected)
        self.assertEqual(read_critical_findings_json(destination / "critical-findings.json"),
                         read_critical_findings_json(FIXTURE / "critical-findings.json"))
        before = (destination / "project.zip").read_bytes()
        with self.assertRaises(FileExistsError):
            build_dataset(destination)
        self.assertEqual((destination / "project.zip").read_bytes(), before)

    def test_gui_check_rules_suggestions_and_automatic_conditions(self):
        for users, findings, rules, automatic, selected in (([], 10, 4, 2, 6), (["alice"], 5, 2, 1, 3)):
            with self.subTest(users=users):
                root = self.root / ("all" if not users else "alice")
                root.mkdir()
                for name in ("project.zip", "policy.hdf5"):
                    shutil.copyfile(FIXTURE / name, root / name)
                app = AppTest.from_string(APP)
                app.session_state["zip_file"] = root / "project.zip"
                app.session_state["policy"] = root / "policy.hdf5"
                app.session_state["root"] = root
                app.run()
                def widget(kind, label):
                    return next(w for w in getattr(app, kind) if w.label == label)
                if users:
                    widget("multiselect", "Select annotators to include").set_value(users).run()
                widget("button", "Run policy check").click().run()
                self.assertFalse(app.exception, str(app.exception))
                self.assertEqual(len(app.session_state["critical_findings"]), findings)
                widget("checkbox", "Semantic BM25 fallback").uncheck()
                widget("checkbox", "Historical ancestor fallback").uncheck()
                widget("button", "Apply suggestion settings").click().run()
                widget("button", "Apply rules to review").click().run()
                self.assertFalse(app.exception, str(app.exception))
                self.assertEqual(len(app.session_state["concept_rule_decisions"]), rules)
                widget("button", "Generate sanitization suggestions").click().run()
                self.assertFalse(app.exception, str(app.exception))
                widget("button", "Apply Conditions").click().run()
                self.assertFalse(app.exception, str(app.exception))
                decisions = app.session_state["sanitization_review_decisions"]
                self.assertEqual(sum(bool(d.get("automatic_condition")) for d in decisions), automatic)
                self.assertEqual(sum(bool(d.get("apply")) for d in decisions), selected)
                self.assertEqual(app.session_state["sanitization_automatic_reviewed_documents"], {"automatic.txt"})
                if users:
                    self.assertEqual({d["annotator"] for d in decisions}, set(users))


if __name__ == "__main__":
    unittest.main()
