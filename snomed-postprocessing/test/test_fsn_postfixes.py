"""Literal FSN-only postfix exclusion, without changing clinical or SNOGIT text."""
import pathlib
import tempfile
import unittest

from snomed_post_processing.sanitization.semantic_bm25 import SemanticBm25Resolver
from snomed_post_processing.sanitization.semantic_text import (
    _fsn_text, _query_text, _semantic_tag, _tokenize, normalize_fsn_postfixes,
)
from test.test_semantic_bm25_sanitization import _finding, _write_compact_hdf5


class FsnPostfixTest(unittest.TestCase):
    def test_only_complete_literal_postfix_after_last_spaced_hyphen_is_removed(self):
        cases = {
            "Evaluation - action (qualifier value)": "Evaluation",
            "Evaluation - ACTION (qualifier value)": "Evaluation",
            "Evaluation-action (qualifier value)": "Evaluation-action",
            "Evaluation- action (qualifier value)": "Evaluation- action",
            "Evaluation -action (qualifier value)": "Evaluation -action",
            "Follow-up - action (qualifier value)": "Follow-up",
            "A - B - action (qualifier value)": "A - B",
            "A - action - action (qualifier value)": "A - action",
            "A - reaction (qualifier value)": "A - reaction",
            "A - action unspecified (qualifier value)": "A - action unspecified",
            "A - other (qualifier value)": "A - other",
            "A – action (qualifier value)": "A – action",
            "A\t-\t action (qualifier value)": "A",
            "Pain (left side) - action (qualifier value)": "Pain (left side)",
            " - action (qualifier value)": " - action",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(_fsn_text(source, (" Action ",)), expected)
        self.assertEqual(_fsn_text("A - .* (finding)", (".*",)), "A")
        self.assertEqual(_fsn_text("A - other (finding)", (".*",)), "A - other")
        self.assertEqual(_fsn_text(None, ("action",)), "")

    def test_disabled_and_custom_postfixes_and_clinical_text(self):
        source = "Evaluation - action (qualifier value)"
        self.assertEqual(_fsn_text(source), "Evaluation - action")
        self.assertEqual(_fsn_text(source, ()), "Evaluation - action")
        self.assertEqual(_fsn_text("At - dosing instruction fragment (qualifier value)",
                                   ("dosing instruction fragment",)), "At")
        self.assertEqual(_fsn_text("A - custom postfix (finding)", ("custom postfix",)), "A")
        finding = _finding(covered_text="Clinical - action (left side)")
        self.assertEqual(_query_text(finding, source, ("action",)), "Clinical - action (left side) Evaluation")
        self.assertIn("action", _tokenize(finding.covered_text))
        self.assertEqual(_semantic_tag(source), "qualifier value")
        self.assertEqual(source, "Evaluation - action (qualifier value)")

    def test_normalization_and_invalid_settings(self):
        self.assertEqual(normalize_fsn_postfixes([" Action ", "ACTION", "custom"]), ("action", "custom"))
        self.assertEqual(normalize_fsn_postfixes([]), ())
        for values in ("action", None, [""], [None], [12]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                SemanticBm25Resolver("unused.hdf5", excluded_fsn_postfixes=values)

    def test_index_query_and_candidate_evidence_use_consistent_text(self):
        fsns = ["Evaluation - action (qualifier value)", "Evaluation - action (qualifier value)",
                "Follow-up - action (qualifier value)", "Procedure - other (qualifier value)"]
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "concepts.hdf5"
            _write_compact_hdf5(path, fsns=fsns)
            with SemanticBm25Resolver(path, excluded_fsn_postfixes=("action",), min_score=0,
                                      min_lexical_score=0, semantic_tag_boost_percent=0) as resolver:
                self.assertEqual(resolver.documents, [["evaluation"], ["follow", "up"], ["procedure", "other"]])
                self.assertNotIn("action", resolver.bm25_index.inverted)
                result = resolver.suggest(_finding(covered_text="evaluation"))
                self.assertEqual(result.replacement_code, "100")
                self.assertEqual(result.candidates[0].lexical_score, 1)
                self.assertEqual(result.candidates[0].matched_term, fsns[1])
                self.assertEqual(result.candidates[0].fsn, fsns[1])
                self.assertEqual(result.candidates[0].semantic_tag, "qualifier value")
                self.assertFalse(resolver.suggest(_finding(code=None, covered_text="action")).candidates)
            with SemanticBm25Resolver(path) as original:
                self.assertIn("action", original.bm25_index.inverted)


if __name__ == "__main__":
    unittest.main()
