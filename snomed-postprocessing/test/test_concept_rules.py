"""Explicit rules preserve literal/features and share local/upload write-back."""
import dataclasses
import io
import json
import pathlib
import tempfile
import unittest
import zipfile

import cassis
import h5py
import numpy as np

from snomed_post_processing.sanitization.concept_rules import (
    ConceptRule, DEFAULT_CONCEPT_RULES, preview_concept_rules, read_rules_json,
    rules_json_text, split_rule_conflicts, validate_rules,
)
from snomed_post_processing.sanitization.decisions_json import (
    read_sanitization_decisions_json, sanitization_decisions_json_text,
)
from snomed_post_processing.pipelines.sanitization_run import run_sanitization, sanitize_cas_bytes
from snomed_post_processing.pipelines.inception_upload_artifacts import build_inception_upload_artifacts


class ConceptRulesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.hdf5 = self.root / "policy.hdf5"
        self.project = self.root / "project.zip"
        self.ts = cassis.TypeSystem()
        self.concept = self.ts.create_type("gemtex.Concept", supertypeName="uima.tcas.Annotation")
        for feature in ("id", "literal", "note"):
            self.ts.create_feature(self.concept, feature, "uima.cas.String")
        self.cas = cassis.Cas(typesystem=self.ts, sofa_string="42 2024-01-01 other")
        self.cas.add(self.concept(begin=0, end=2, id="http://snomed.info/id/410680006", literal=" 0042 ± ", note="keep number"))
        self.cas.add(self.concept(begin=3, end=13, id="http://snomed.info/id/410671006", literal="2024/01/01", note="keep date"))
        self.cas.add(self.concept(begin=14, end=19, id="999", literal="", note="unchanged"))
        self.write_hdf5()
        self.write_project()

    def write_hdf5(self, target_active=True, target_included=False, target_excluded=True):
        dtype = h5py.string_dtype("utf-8")
        with h5py.File(self.hdf5, "w") as h5:
            concepts = h5.create_group("concepts")
            concepts.create_dataset("codes", data=np.array(["410680006", "410671006", "410672004", "999"], dtype=object), dtype=dtype)
            concepts.create_dataset("fsn", data=np.array(["Number (attribute)", "Date (attribute)", "Date property (qualifier value)", "Other"], dtype=object), dtype=dtype)
            concepts.create_dataset("active", data=np.array([True, True, target_active, True]))
            views = h5.create_group("policy_views")
            views.create_group("whitelist").create_group("0").create_dataset("concept_index", data=np.array([0, 1, 3] + ([2] if target_included else []), dtype="int64"))
            views.create_group("blacklist").create_group("0").create_dataset("concept_index", data=np.array([2] if target_excluded else [], dtype="int64"))

    def write_project(self, cas=None):
        cas = cas or self.cas
        with zipfile.ZipFile(self.project, "w") as archive:
            archive.writestr("exportedproject.json", json.dumps({"source_documents": [{"name": "one.txt"}, {"name": "two.txt"}]}))
            archive.writestr("TypeSystem.xml", cas.typesystem.to_xml())
            archive.writestr("annotation/one.txt/alice.json", cas.to_json())
            archive.writestr("annotation/one.txt/bob.xmi", cas.to_xmi())
            archive.writestr("annotation/two.txt/alice.xmi", cas.to_xmi())

    def preview(self, rules=DEFAULT_CONCEPT_RULES, **kwargs):
        return preview_concept_rules(self.project, self.hdf5, rules, annotation_types=["gemtex.Concept"], **kwargs)

    def assert_features_preserved(self, result_cas):
        before = list(self.cas.select("gemtex.Concept"))
        after = list(result_cas.select("gemtex.Concept"))
        self.assertEqual(len(before), len(after))
        for original, changed in zip(before, after):
            self.assertEqual((original.begin, original.end, original.type.name), (changed.begin, changed.end, changed.type.name))
            self.assertEqual(original.literal, changed.literal)
            self.assertEqual(original.note, changed.note)
        self.assertIsNone(after[0].id)
        self.assertEqual(after[1].id, "http://snomed.info/id/410672004")
        self.assertEqual(after[2].id, "999")

    def test_defaults_and_rule_json_roundtrip(self):
        restored = read_rules_json(io.StringIO(rules_json_text(DEFAULT_CONCEPT_RULES)))
        self.assertEqual(restored, DEFAULT_CONCEPT_RULES)
        self.assertTrue(all(rule.enabled and rule.override_policy for rule in restored))

    def test_validation_rejects_conflicts_bad_actions_targets_and_self_replacement(self):
        for rules in (
            [DEFAULT_CONCEPT_RULES[0], dataclasses.replace(DEFAULT_CONCEPT_RULES[0], rule_id="duplicate")],
            [dataclasses.replace(DEFAULT_CONCEPT_RULES[0], target_code="123")],
            [dataclasses.replace(DEFAULT_CONCEPT_RULES[0], action="delete")],
            [dataclasses.replace(DEFAULT_CONCEPT_RULES[1], target_code="410671006")],
            [dataclasses.replace(DEFAULT_CONCEPT_RULES[1], target_code="")],
            [dataclasses.replace(DEFAULT_CONCEPT_RULES[1], override_policy="false")],
        ):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                validate_rules(rules)

    def test_preview_scans_all_annotations_and_records_actual_override(self):
        source = self.project.read_bytes()
        decisions = self.preview()
        self.assertEqual(len(decisions), 6)
        self.assertEqual({item["action"] for item in decisions}, {"replace", "clear_id"})
        self.assertEqual(sum(item["policy_overridden"] for item in decisions), 3)
        self.assertTrue(all(item["apply"] and item["resolved"] for item in decisions))
        self.assertEqual(source, self.project.read_bytes())
        # Source concepts are already included, so a findings-only scan would miss them.
        self.assertTrue(all(item["source_code"] in {"410680006", "410671006"} for item in decisions))

    def test_scope_disabled_rules_and_missing_layer(self):
        decisions = self.preview(documents=["one.txt"], annotators=["ALICE"])
        self.assertEqual(len(decisions), 2)
        self.assertEqual(self.preview([dataclasses.replace(rule, enabled=False) for rule in DEFAULT_CONCEPT_RULES]), [])
        self.assertEqual(preview_concept_rules(self.project, self.hdf5, DEFAULT_CONCEPT_RULES, annotation_types=["absent.Layer"]), [])

    def test_override_off_enforces_policy_but_clear_id_needs_no_target(self):
        no_override = [dataclasses.replace(rule, override_policy=False) for rule in DEFAULT_CONCEPT_RULES]
        with self.assertRaisesRegex(ValueError, "override is off"):
            self.preview(no_override)
        self.assertEqual(len(self.preview(no_override[:1])), 3)
        self.write_hdf5(target_included=True, target_excluded=False)
        decisions = self.preview(no_override)
        self.assertFalse(any(item["policy_overridden"] for item in decisions))
        # Permission to override and an actual override are distinct.
        self.assertFalse(any(item["policy_overridden"] for item in self.preview()))

    def test_override_never_allows_missing_or_inactive_target(self):
        self.write_hdf5(target_active=False)
        with self.assertRaisesRegex(ValueError, "must exist and be active"):
            self.preview()
        self.write_hdf5()
        with self.assertRaisesRegex(ValueError, "must exist and be active"):
            self.preview([dataclasses.replace(DEFAULT_CONCEPT_RULES[1], target_code="123456")])

    def test_jsoncas_and_xmi_writeback_preserve_all_other_features(self):
        decisions = self.preview(documents=["one.txt"], annotators=["alice"])
        for fmt, content, loader in (
            ("jsoncas", self.cas.to_json(), cassis.load_cas_from_json),
            ("xmi", self.cas.to_xmi(), cassis.load_cas_from_xmi),
        ):
            with self.subTest(fmt=fmt):
                result = sanitize_cas_bytes(content.encode(), decisions, cas_format=fmt, typesystem=self.ts)
                self.assertEqual(result.changed_annotation_count, 2)
                self.assertEqual(result.unmatched_decisions, ())
                changed = loader(io.BytesIO(result.cas_bytes), typesystem=self.ts)
                self.assert_features_preserved(changed)
                again = sanitize_cas_bytes(result.cas_bytes, decisions, cas_format=fmt, typesystem=self.ts)
                self.assertEqual(again.changed_annotation_count, 0)

    def test_null_and_empty_literals_and_absent_literal_feature(self):
        for value in (None, ""):
            list(self.cas.select("gemtex.Concept"))[0].literal = value
            self.write_project()
            decisions = self.preview(documents=["one.txt"], annotators=["alice"])
            for fmt, content, loader in (("jsoncas", self.cas.to_json(), cassis.load_cas_from_json), ("xmi", self.cas.to_xmi(), cassis.load_cas_from_xmi)):
                result = sanitize_cas_bytes(content.encode(), decisions, cas_format=fmt, typesystem=self.ts)
                changed = loader(io.BytesIO(result.cas_bytes), typesystem=self.ts)
                self.assertEqual(list(changed.select("gemtex.Concept"))[0].literal, value)
        ts = cassis.TypeSystem()
        concept = ts.create_type("gemtex.Concept", supertypeName="uima.tcas.Annotation")
        ts.create_feature(concept, "id", "uima.cas.String")
        cas = cassis.Cas(typesystem=ts, sofa_string="42")
        cas.add(concept(begin=0, end=2, id="410680006"))
        self.write_project(cas)
        decisions = self.preview(documents=["one.txt"], annotators=["alice"])
        result = sanitize_cas_bytes(cas.to_json().encode(), decisions, cas_format="jsoncas", typesystem=ts)
        changed = cassis.load_cas_from_json(io.BytesIO(result.cas_bytes))
        self.assertNotIn("literal", [feature.name for feature in changed.typesystem.get_type("gemtex.Concept").features])
        self.assertIsNone(list(changed.select("gemtex.Concept"))[0].id)

    def test_rules_do_not_chain_and_plain_ids_stay_plain(self):
        for annotation in self.cas.select("gemtex.Concept"):
            annotation.id = annotation.id.rsplit("/", 1)[-1]
        self.write_project()
        rules = [DEFAULT_CONCEPT_RULES[0], dataclasses.replace(DEFAULT_CONCEPT_RULES[1], target_code="410680006")]
        decisions = self.preview(rules, documents=["one.txt"], annotators=["alice"])
        result = sanitize_cas_bytes(self.cas.to_json().encode(), decisions, cas_format="jsoncas", typesystem=self.ts)
        changed = cassis.load_cas_from_json(io.BytesIO(result.cas_bytes))
        annotations = list(changed.select("gemtex.Concept"))
        self.assertIsNone(annotations[0].id)
        self.assertEqual(annotations[1].id, "410680006")

    def test_decisions_roundtrip_includes_rules_override_and_clear_action(self):
        decisions = self.preview()
        metadata = {"concept_rules": [dataclasses.asdict(rule) for rule in DEFAULT_CONCEPT_RULES]}
        restored, restored_metadata = read_sanitization_decisions_json(io.StringIO(sanitization_decisions_json_text(decisions, metadata=metadata)))
        self.assertEqual(restored, decisions)
        self.assertEqual(restored_metadata, metadata)

    def test_zip_export_and_offline_upload_artifacts_share_rule_semantics(self):
        decisions = self.preview()
        source = self.project.read_bytes()
        result = run_sanitization(self.project, decisions, self.root / "sanitized.zip")
        self.assertEqual(result.changed_annotation_count, 6)
        self.assertEqual(result.unmatched_decisions, ())
        with zipfile.ZipFile(result.output_project) as archive:
            for path in ("annotation/one.txt/alice.json", "annotation/one.txt/bob.xmi"):
                loader = cassis.load_cas_from_json if path.endswith("json") else cassis.load_cas_from_xmi
                self.assert_features_preserved(loader(io.BytesIO(archive.read(path)), typesystem=self.ts))
        for repair in (False, True):
            artifacts = build_inception_upload_artifacts(self.project, decisions, self.root / f"uploads-{repair}", repair_for_remote_upload=repair)
            self.assertEqual(artifacts.artifact_count, 3)
            for artifact in artifacts.artifacts:
                loader = cassis.load_cas_from_json if artifact.cas_format == "jsoncas" else cassis.load_cas_from_xmi
                # Repaired files can add sentence/token types; use their own TypeSystem where embedded.
                self.assert_features_preserved(loader(io.BytesIO(artifact.output_path.read_bytes()), typesystem=self.ts, lenient=True))
        self.assertEqual(source, self.project.read_bytes())

    def test_manual_conflicts_protect_actions_and_explicit_keep(self):
        rules = self.preview(documents=["one.txt"], annotators=["alice"])
        manual = [{**rules[0], "concept_rule": None, "action": "none", "apply": False, "reviewed_by_human": True}]
        safe, conflicts = split_rule_conflicts(rules, manual)
        self.assertEqual(conflicts, rules[:1])
        self.assertEqual(safe, rules[1:])
        self.assertEqual(split_rule_conflicts(rules, [{**manual[0], "reviewed_by_human": False}])[1], [])
        self.assertEqual(split_rule_conflicts(rules, [{**manual[0], "reviewed_by_human": False}], ["one.txt"])[1], rules[:1])

    def test_overlapping_layer_selection_deduplicates_subtypes_and_matches_exact_type(self):
        child = self.ts.create_type("gemtex.SubConcept", supertypeName="gemtex.Concept")
        self.cas.add(child(begin=0, end=2, id="http://snomed.info/id/410680006", literal="child literal", note="child"))
        self.write_project()
        decisions = preview_concept_rules(
            self.project, self.hdf5, DEFAULT_CONCEPT_RULES,
            annotation_types=["gemtex.Concept", "gemtex.SubConcept"],
            documents=["one.txt"], annotators=["alice"],
        )
        self.assertEqual(len(decisions), 3)
        result = sanitize_cas_bytes(self.cas.to_json().encode(), decisions, cas_format="jsoncas", typesystem=self.ts)
        self.assertEqual(result.changed_annotation_count, 3)
        self.assertEqual(result.unmatched_decisions, ())
        changed = cassis.load_cas_from_json(io.BytesIO(result.cas_bytes))
        self.assertIsNone(list(changed.select("gemtex.SubConcept"))[0].id)
        self.assertEqual(list(changed.select("gemtex.SubConcept"))[0].literal, "child literal")

    def test_invalid_or_unselected_clear_id_decisions_are_skipped(self):
        decision = self.preview(documents=["one.txt"], annotators=["alice"])[0]
        decisions = [
            {**decision, "apply": False}, {**decision, "valid_choice": False},
            {**decision, "replacement_code": "123"},
        ]
        result = sanitize_cas_bytes(self.cas.to_json().encode(), decisions, cas_format="jsoncas", typesystem=self.ts)
        self.assertEqual(result.changed_annotation_count, 0)
        self.assertEqual(len(result.skipped_decisions), 3)
        changed = cassis.load_cas_from_json(io.BytesIO(result.cas_bytes))
        self.assertEqual(list(changed.select("gemtex.Concept"))[0].id, "http://snomed.info/id/410680006")

    def test_ambiguous_annotations_fail_closed(self):
        self.cas.add(self.concept(begin=0, end=2, id="http://snomed.info/id/410680006"))
        self.write_project()
        with self.assertRaisesRegex(ValueError, "Ambiguous annotation identity"):
            self.preview()


if __name__ == "__main__":
    unittest.main()
