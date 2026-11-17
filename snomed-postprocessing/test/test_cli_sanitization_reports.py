"""Offline CLI report exports using tiny synthetic terminology/findings fixtures."""
import dataclasses
import io
import pathlib
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from click.testing import CliRunner

from snomed_post_processing.cli.app import suggest_sanitization_cli
from snomed_post_processing.findings_io import write_critical_findings_json
from snomed_post_processing.sanitization import (
    SanitizationResolver, read_sanitization_suggestions_json_with_metadata,
)
from snomed_post_processing.sanitization.models import SanitizationCandidate
from snomed_post_processing.sanitization.semantic_models import SemanticBm25Suggestion
from snomed_post_processing.sanitization_context import (
    SUGGESTION_OVERVIEW_COLUMNS, suggestion_overview_row,
)
from test.test_bm25_conditions import bm25_suggestion
from test.test_sanitization_resolver import _finding, _write_sanitization_ready_hdf5
from test.test_semantic_bm25_sanitization import _finding as bm25_finding


class CliSanitizationReportsTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = pathlib.Path(directory.name)
        self.hdf5 = self.root / "concepts.hdf5"
        self.source = self.root / "findings.json"
        self.output = self.root / "reports" / "suggestions.md"
        _write_sanitization_ready_hdf5(self.hdf5)
        self.findings = [dataclasses.replace(_finding(), document=document, annotator=annotator,
            covered_text='private-A.txt,\n"clinical ± text"')
            for document, annotator in (("private-A.txt", "Alice"), ("private-A.txt", "Bob"), ("private-B.txt", "Alice"))]
        self.metadata = {"annotators": ["alice", "bob"], "id_feature": "customId", "id_prefix": "",
                         "store_scope": "*:annotation", "finding_contexts": [{"context": "saved context"}]}
        write_critical_findings_json(self.findings, self.source, metadata=self.metadata)

    def invoke(self, *extra, output=None):
        result = CliRunner().invoke(suggest_sanitization_cli, [
            "--lists-path", str(self.hdf5), "--critical-findings", str(self.source),
            "--output", str(output or self.output), *extra,
        ])
        return result

    def test_structured_reports_roundtrip_and_mask_only_identity_columns(self):
        source_before, hdf5_before = self.source.read_bytes(), self.hdf5.read_bytes()
        expected = SanitizationResolver(self.hdf5).suggest_all(self.findings)
        result = self.invoke()
        self.assertEqual(result.exit_code, 0, (result.output, result.exception))
        self.assertIn("Replacement concept", self.output.read_text(encoding="utf-8"))
        loaded, metadata = read_sanitization_suggestions_json_with_metadata(self.output.with_suffix(".json"))
        self.assertEqual(loaded, expected)
        for key, value in self.metadata.items():
            self.assertEqual(metadata[key], value)
        self.assertEqual(metadata["command"], "suggest-sanitization")
        self.assertEqual(metadata["finding_count"], 3)
        self.assertEqual(metadata["suggestion_count"], 3)
        self.assertEqual(metadata["settings"]["target_view"], "policy")
        self.assertFalse(metadata["settings"]["semantic_bm25_fallback"])
        content = self.output.with_suffix(".masked.csv").read_bytes()
        self.assertTrue(content.startswith(b"\xef\xbb\xbf"))
        csv = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
        original = pd.DataFrame([suggestion_overview_row(i, item) for i, item in enumerate(expected, 1)])
        self.assertEqual(tuple(csv.columns), SUGGESTION_OVERVIEW_COLUMNS)
        self.assertEqual(csv["Document"].tolist(), ["document-1", "document-1", "document-2"])
        self.assertEqual(csv["Annotator"].tolist(), ["annotator-1", "annotator-2", "annotator-1"])
        pd.testing.assert_frame_equal(csv.drop(columns=["Document", "Annotator"]),
                                      original.drop(columns=["Document", "Annotator"]).astype(str))
        self.assertEqual(self.source.read_bytes(), source_before)
        self.assertEqual(self.hdf5.read_bytes(), hdf5_before)

    def test_actual_bm25_generation_and_settings_are_saved(self):
        write_critical_findings_json([bm25_finding(covered_text="replacement concept")], self.source)
        result = self.invoke("--semantic-bm25-fallback", "--bm25-min-score", "0",
                             "--bm25-min-lexical-score", "0", "--bm25-max-candidates", "7",
                             "--bm25-semantic-tag-boost-percent", "37", "--target-view", "release")
        self.assertEqual(result.exit_code, 0, (result.output, result.exception))
        loaded, metadata = read_sanitization_suggestions_json_with_metadata(self.output.with_suffix(".json"))
        self.assertIsInstance(loaded[0], SemanticBm25Suggestion)
        self.assertTrue(loaded[0].candidates)
        self.assertTrue(metadata["settings"]["semantic_bm25_fallback"])
        self.assertEqual(metadata["settings"]["bm25_max_candidates"], 7)
        self.assertEqual(metadata["settings"]["bm25_semantic_tag_boost_percent"], 37)
        self.assertEqual(metadata["settings"]["target_view"], "release")
        self.assertEqual(metadata["hdf5_file_name"], "concepts.hdf5")
        self.assertIsNone(metadata["hdf5_policy_date"])

    def test_json_preserves_all_candidates_precision_diagnostics_and_limits(self):
        item = bm25_suggestion([22.6022130612345, 15.30182904, 11.76684182, 1.23456789, 0.123456789])
        item = dataclasses.replace(item, context_candidates=(
            SanitizationCandidate("0042", "Diagnostic target", "WAS_A", True, False, False),
        ), retrieval_limits=("SNOGIT hit limit",))
        with patch("snomed_post_processing.pipelines.sanitization_check.SanitizationResolver") as resolver:
            resolver.return_value.suggest_all.return_value = [item]
            result = self.invoke()
        self.assertEqual(result.exit_code, 0, (result.output, result.exception))
        loaded, _ = read_sanitization_suggestions_json_with_metadata(self.output.with_suffix(".json"))
        self.assertEqual(loaded, [item])
        self.assertEqual(len(loaded[0].candidates), 5)
        csv = pd.read_csv(self.output.with_suffix(".masked.csv"), dtype=str, keep_default_na=False)
        self.assertIn("0042", csv.iloc[0]["Diagnostic candidates (not selectable)"])
        self.assertNotIn("0042", csv.iloc[0]["Top candidates"])
        self.assertEqual(csv.iloc[0]["Retrieval limits"], "SNOGIT hit limit")

    def test_empty_findings_produce_valid_json_and_header_only_csv(self):
        write_critical_findings_json([], self.source, metadata=self.metadata)
        result = self.invoke()
        self.assertEqual(result.exit_code, 0, (result.output, result.exception))
        loaded, metadata = read_sanitization_suggestions_json_with_metadata(self.output.with_suffix(".json"))
        self.assertEqual(loaded, [])
        self.assertEqual(metadata["suggestion_count"], 0)
        csv = pd.read_csv(self.output.with_suffix(".masked.csv"))
        self.assertTrue(csv.empty)
        self.assertEqual(tuple(csv.columns), SUGGESTION_OVERVIEW_COLUMNS)

    def test_extensionless_output_still_gets_sibling_artifacts(self):
        output = self.root / "reports" / "latest"
        result = self.invoke(output=output)
        self.assertEqual(result.exit_code, 0, (result.output, result.exception))
        for path in (output, output.with_suffix(".json"), output.with_suffix(".masked.csv")):
            self.assertTrue(path.is_file(), path)

    def test_colliding_output_or_input_paths_are_rejected_without_writes(self):
        before = self.source.read_bytes()
        for output in (self.root / "report.json", self.root / "findings.md", self.hdf5):
            with self.subTest(output=output):
                result = self.invoke(output=output)
                self.assertNotEqual(result.exit_code, 0)
                self.assertIn("must not overwrite input files", result.output)
                self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse((self.root / "report.json").exists())
        self.assertFalse((self.root / "findings.md").exists())


if __name__ == "__main__":
    unittest.main()
