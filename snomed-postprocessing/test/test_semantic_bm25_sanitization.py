import io
import pathlib
import tempfile
import unittest

import h5py
import numpy as np

from snomed_post_processing.sanitization import (
    SanitizationStatus,
    SanitizationSuggestion,
    apply_semantic_bm25_fallback,
    write_sanitization_markdown_report,
)
from snomed_post_processing.sanitization.semantic_bm25 import (
    SemanticBm25Resolver,
    suggest_semantic_bm25,
)
from snomed_post_processing.uima_processing import CriticalFinding


_STRING_DTYPE = h5py.string_dtype(encoding="utf-8")


def _finding(*, code="999", covered_text="alpha therapy", list_type="whitelist", ignored=False):
    return CriticalFinding(
        annotator="annotator-a",
        document="doc.txt",
        code=code,
        covered_text=covered_text,
        offset=(10, 20),
        list_type=list_type,
        reason="not_in_whitelist" if list_type == "whitelist" else "blacklisted",
        layer="gemtex.Concept",
        ignored=ignored,
    )


def _write_compact_hdf5(
    path: pathlib.Path,
    *,
    whitelist_indices=(1, 2, 3),
    blacklist_indices=(),
    active=(False, True, True, True),
):
    with h5py.File(path, "w") as h5_file:
        concepts = h5_file.create_group("concepts")
        concepts.create_dataset(
            "codes",
            data=np.asarray(["999", "100", "200", "300"], dtype=object),
            dtype=_STRING_DTYPE,
        )
        concepts.create_dataset(
            "fsn",
            data=np.asarray(
                [
                    "Inactive alpha therapy legacy concept (procedure)",
                    "Alpha therapy procedure (procedure)",
                    "Beta diagnostic procedure (procedure)",
                    "Alpha therapy forbidden concept (procedure)",
                ],
                dtype=object,
            ),
            dtype=_STRING_DTYPE,
        )
        concepts.create_dataset("active", data=np.asarray(active, dtype=bool))
        policy_views = h5_file.create_group("policy_views")
        whitelist = policy_views.create_group("whitelist").create_group("0")
        whitelist.create_dataset("concept_index", data=np.asarray(whitelist_indices, dtype=np.int64))
        blacklist = policy_views.create_group("blacklist").create_group("0")
        blacklist.create_dataset("concept_index", data=np.asarray(blacklist_indices, dtype=np.int64))


class TestSemanticBm25Sanitization(unittest.TestCase):
    def test_suggests_policy_acceptable_bm25_replacement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_compact_hdf5(hdf5_path, blacklist_indices=(3,))

            suggestion = suggest_semantic_bm25(
                _finding(),
                hdf5_path,
                min_score=0.1,
                min_lexical_score=0.2,
            )

        self.assertEqual(suggestion.status, SanitizationStatus.SEMANTIC_BM25_REPLACEMENT)
        self.assertEqual(suggestion.replacement_code, "100")
        self.assertEqual(suggestion.replacement_fsn, "Alpha therapy procedure (procedure)")
        self.assertGreater(suggestion.score, 0.0)
        self.assertTrue(suggestion.candidates[0].policy_acceptable)

    def test_thresholds_can_reject_weak_candidate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_compact_hdf5(hdf5_path)

            suggestion = suggest_semantic_bm25(
                _finding(covered_text="alpha therapy"),
                hdf5_path,
                min_score=999.0,
                min_lexical_score=0.2,
            )

        self.assertEqual(suggestion.status, SanitizationStatus.NO_REPLACEMENT)
        self.assertIsNone(suggestion.replacement_code)
        self.assertGreater(suggestion.candidate_count, 0)
        self.assertIn("threshold", suggestion.reason)

    def test_blacklist_findings_remain_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_compact_hdf5(hdf5_path)
            resolver = SemanticBm25Resolver(hdf5_path, min_score=0.1)

            suggestion = resolver.suggest(_finding(list_type="blacklist"))

        self.assertEqual(suggestion.status, SanitizationStatus.BLACKLISTED_NO_AUTO_SANITIZATION)
        self.assertIsNone(suggestion.replacement_code)

    def test_blacklist_findings_can_get_opt_in_bm25_suggestions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_compact_hdf5(hdf5_path, blacklist_indices=(3,))
            resolver = SemanticBm25Resolver(
                hdf5_path,
                min_score=0.1,
                min_lexical_score=0.2,
                allow_blacklist_findings=True,
            )

            suggestion = resolver.suggest(_finding(list_type="blacklist"))

        self.assertEqual(suggestion.status, SanitizationStatus.SEMANTIC_BM25_REPLACEMENT)
        self.assertEqual(suggestion.replacement_code, "100")
        self.assertEqual(suggestion.association_type, "BM25")

    def test_ignored_findings_are_not_sanitized(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_compact_hdf5(hdf5_path)

            suggestion = suggest_semantic_bm25(_finding(ignored=True), hdf5_path)

        self.assertEqual(suggestion.status, SanitizationStatus.NO_REPLACEMENT)
        self.assertIsNone(suggestion.replacement_code)

    def test_apply_fallback_can_include_blacklist_findings_in_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_compact_hdf5(hdf5_path, blacklist_indices=(3,))
            blacklist_unresolved = SanitizationSuggestion(
                finding=_finding(list_type="blacklist"),
                status=SanitizationStatus.BLACKLISTED_NO_AUTO_SANITIZATION,
                reason="blacklist suggestions disabled",
            )

            suggestions = apply_semantic_bm25_fallback(
                [blacklist_unresolved],
                hdf5_path,
                allow_blacklist_findings=True,
                min_score=0.1,
                min_lexical_score=0.2,
            )
            output = io.StringIO()
            write_sanitization_markdown_report(suggestions, output)
            report = output.getvalue()

        self.assertEqual(suggestions[0].status, SanitizationStatus.SEMANTIC_BM25_REPLACEMENT)
        self.assertEqual(suggestions[0].replacement_code, "100")
        self.assertIn("semantic_bm25_replacement", report)
        self.assertIn("BM25", report)

    def test_apply_fallback_feeds_existing_sanitization_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_compact_hdf5(hdf5_path, blacklist_indices=(3,))
            historical_unresolved = SanitizationSuggestion(
                finding=_finding(),
                status=SanitizationStatus.NO_HISTORICAL_ASSOCIATION,
                reason="no historical association",
            )

            suggestions = apply_semantic_bm25_fallback(
                [historical_unresolved],
                hdf5_path,
                min_score=0.1,
                min_lexical_score=0.2,
            )
            output = io.StringIO()
            write_sanitization_markdown_report(suggestions, output)
            report = output.getvalue()

        self.assertEqual(suggestions[0].status, SanitizationStatus.SEMANTIC_BM25_REPLACEMENT)
        self.assertEqual(suggestions[0].replacement_code, "100")
        self.assertIn("semantic_bm25_replacement", report)
        self.assertIn("BM25", report)
        self.assertIn("Alpha therapy procedure", report)

    def test_requires_compact_policy_views(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            with h5py.File(hdf5_path, "w") as h5_file:
                h5_file.create_group("concepts")

            with self.assertRaisesRegex(ValueError, "BM25-sanitization-ready"):
                SemanticBm25Resolver(hdf5_path)


if __name__ == "__main__":
    unittest.main()
