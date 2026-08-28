import dataclasses
import io
import pathlib
import tempfile
import unittest

import h5py
import numpy as np

from snomed_post_processing.sanitization import (
    ASSOCIATION_TYPE_DESCRIPTIONS,
    DEFAULT_ALLOWED_ASSOCIATION_TYPES,
    SUPPORTED_ASSOCIATION_TYPES,
    format_association_type_descriptions,
    SanitizationResolver,
    SanitizationStatus,
    suggest_sanitization,
    write_sanitization_markdown_report,
)
from snomed_post_processing.uima_processing import CriticalFinding


_STRING_DTYPE = h5py.string_dtype(encoding="utf-8")


def _finding(code="100"):
    return CriticalFinding(
        annotator="annotator-a",
        document="doc.txt",
        code=code,
        covered_text="old concept",
        offset=(10, 20),
        list_type="whitelist",
        reason="not_in_whitelist",
        layer="gemtex.Concept",
    )


def _write_sanitization_ready_hdf5(
    path: pathlib.Path,
    *,
    whitelist_indices=(1,),
    blacklist_indices=(),
    target_active=(False, True, True),
    associations=((0, 1, 0, True, "20240131", "900000000000526001"),),
    association_types=("REPLACED_BY", "SAME_AS"),
):
    with h5py.File(path, "w") as h5_file:
        concepts = h5_file.create_group("concepts")
        concepts.create_dataset("codes", data=np.asarray(["100", "200", "300"], dtype=object), dtype=_STRING_DTYPE)
        concepts.create_dataset(
            "fsn",
            data=np.asarray([
                "Old concept (finding)",
                "Replacement concept (finding)",
                "Alternative concept (finding)",
            ], dtype=object),
            dtype=_STRING_DTYPE,
        )
        concepts.create_dataset("active", data=np.asarray(target_active, dtype=bool))

        policy_views = h5_file.create_group("policy_views")
        whitelist = policy_views.create_group("whitelist").create_group("0")
        whitelist.create_dataset("concept_index", data=np.asarray(whitelist_indices, dtype=np.int64))
        blacklist = policy_views.create_group("blacklist").create_group("0")
        blacklist.create_dataset("concept_index", data=np.asarray(blacklist_indices, dtype=np.int64))

        hist = h5_file.create_group("historical_associations")
        hist.create_dataset("source_index", data=np.asarray([a[0] for a in associations], dtype=np.int64))
        hist.create_dataset("target_index", data=np.asarray([a[1] for a in associations], dtype=np.int64))
        hist.create_dataset("association_type_id", data=np.asarray([a[2] for a in associations], dtype=np.int64))
        hist.create_dataset("association_types", data=np.asarray(association_types, dtype=object), dtype=_STRING_DTYPE)
        hist.create_dataset("active", data=np.asarray([a[3] for a in associations], dtype=bool))
        hist.create_dataset("effective_time", data=np.asarray([a[4] for a in associations], dtype=object), dtype=_STRING_DTYPE)
        hist.create_dataset("refset_id", data=np.asarray([a[5] for a in associations], dtype=object), dtype=_STRING_DTYPE)


class TestSanitizationResolver(unittest.TestCase):
    def test_supported_association_types_back_defaults_and_descriptions(self):
        self.assertTrue(set(DEFAULT_ALLOWED_ASSOCIATION_TYPES).issubset(SUPPORTED_ASSOCIATION_TYPES))
        self.assertIn("POSSIBLY_EQUIVALENT_TO", SUPPORTED_ASSOCIATION_TYPES)
        self.assertIn("PARTIALLY_EQUIVALENT_TO", SUPPORTED_ASSOCIATION_TYPES)
        self.assertIn("POSSIBLY_REPLACED_BY", SUPPORTED_ASSOCIATION_TYPES)
        self.assertIn("REFERS_TO", SUPPORTED_ASSOCIATION_TYPES)
        self.assertIn("SIMILAR_TO", SUPPORTED_ASSOCIATION_TYPES)
        self.assertEqual(set(SUPPORTED_ASSOCIATION_TYPES), set(ASSOCIATION_TYPE_DESCRIPTIONS))
        descriptions = format_association_type_descriptions()
        self.assertIn("SAME_AS", descriptions)
        self.assertIn("Source concept is considered equivalent", descriptions)

    def test_suggests_single_policy_acceptable_historical_replacement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_sanitization_ready_hdf5(hdf5_path)

            suggestion = suggest_sanitization(_finding(), hdf5_path)

        self.assertEqual(suggestion.status, SanitizationStatus.HISTORICAL_ASSOCIATION_REPLACEMENT)
        self.assertEqual(suggestion.replacement_code, "200")
        self.assertEqual(suggestion.replacement_fsn, "Replacement concept (finding)")
        self.assertEqual(suggestion.association_type, "REPLACED_BY")
        self.assertEqual(suggestion.candidate_count, 1)

    def test_rejects_candidate_not_accepted_by_policy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_sanitization_ready_hdf5(hdf5_path, whitelist_indices=())

            suggestion = suggest_sanitization(_finding(), hdf5_path)

        self.assertEqual(suggestion.status, SanitizationStatus.NO_POLICY_ACCEPTABLE_CANDIDATE)
        self.assertEqual(suggestion.replacement_code, None)
        self.assertEqual(suggestion.candidate_count, 1)
        self.assertFalse(suggestion.candidates[0].policy_acceptable)

    def test_release_view_accepts_active_candidate_without_whitelist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_sanitization_ready_hdf5(hdf5_path, whitelist_indices=())

            suggestion = suggest_sanitization(_finding(), hdf5_path, target_view="release")

        self.assertEqual(suggestion.status, SanitizationStatus.HISTORICAL_ASSOCIATION_REPLACEMENT)
        self.assertEqual(suggestion.replacement_code, "200")
        self.assertFalse(suggestion.candidates[0].in_whitelist)

    def test_release_view_optionally_excludes_blacklist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_sanitization_ready_hdf5(hdf5_path, whitelist_indices=(), blacklist_indices=(1,))

            excluded = suggest_sanitization(
                _finding(),
                hdf5_path,
                target_view="release",
                release_exclude_blacklist=True,
            )
            allowed = suggest_sanitization(
                _finding(),
                hdf5_path,
                target_view="release",
            )

        self.assertEqual(excluded.status, SanitizationStatus.NO_POLICY_ACCEPTABLE_CANDIDATE)
        self.assertEqual(allowed.status, SanitizationStatus.HISTORICAL_ASSOCIATION_REPLACEMENT)
        self.assertEqual(allowed.replacement_code, "200")
        self.assertTrue(allowed.candidates[0].in_blacklist)

    def test_blacklist_overrides_whitelist_for_candidate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_sanitization_ready_hdf5(hdf5_path, whitelist_indices=(1,), blacklist_indices=(1,))

            suggestion = suggest_sanitization(_finding(), hdf5_path)

        self.assertEqual(suggestion.status, SanitizationStatus.NO_POLICY_ACCEPTABLE_CANDIDATE)
        self.assertTrue(suggestion.candidates[0].in_whitelist)
        self.assertTrue(suggestion.candidates[0].in_blacklist)

    def test_marks_multiple_acceptable_targets_as_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_sanitization_ready_hdf5(
                hdf5_path,
                whitelist_indices=(1, 2),
                associations=(
                    (0, 1, 0, True, "20240131", "900000000000526001"),
                    (0, 2, 1, True, "20240131", "900000000000527005"),
                ),
            )

            suggestion = suggest_sanitization(_finding(), hdf5_path)

        self.assertEqual(suggestion.status, SanitizationStatus.AMBIGUOUS_REPLACEMENT)
        self.assertEqual(suggestion.candidate_count, 2)
        self.assertEqual({candidate.code for candidate in suggestion.candidates}, {"200", "300"})

    def test_blacklist_findings_do_not_auto_sanitize(self):
        finding = CriticalFinding(
            annotator="annotator-a",
            document="doc.txt",
            code="200",
            covered_text="bad concept",
            offset=(10, 20),
            list_type="blacklist",
            reason="blacklisted",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_sanitization_ready_hdf5(hdf5_path)
            resolver = SanitizationResolver(hdf5_path)

            suggestion = resolver.suggest(finding)

        self.assertEqual(suggestion.status, SanitizationStatus.BLACKLISTED_NO_AUTO_SANITIZATION)
        self.assertIsNone(suggestion.replacement_code)

    def test_missing_historical_association_is_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_sanitization_ready_hdf5(hdf5_path, associations=())

            suggestion = suggest_sanitization(_finding(), hdf5_path)

        self.assertEqual(suggestion.status, SanitizationStatus.NO_HISTORICAL_ASSOCIATION)

    def test_writes_standalone_markdown_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_sanitization_ready_hdf5(hdf5_path)
            suggestion = suggest_sanitization(_finding(), hdf5_path)

        suggestion = dataclasses.replace(
            suggestion,
            finding=dataclasses.replace(suggestion.finding, covered_text="line1\r\nline2\nline3\rline4"),
        )
        output = io.StringIO()
        write_sanitization_markdown_report([suggestion], output)
        report = output.getvalue()

        self.assertIn("# Sanitization Suggestions", report)
        self.assertIn("suggestion-only", report)
        self.assertIn("## Replacement suggestions", report)
        self.assertIn("### annotator-a", report)
        self.assertIn(
            "| Document | Source Code | Covered Text | Original FSN | Status | Replacement Code | Replacement FSN | Association | Candidates / context |",
            report,
        )
        self.assertIn("historical_association_replacement", report)
        self.assertIn("200", report)
        self.assertIn("Replacement concept (finding)", report)
        self.assertIn("line1 line2 line3 line4", report)
        self.assertNotIn("line1\r", report)
        self.assertNotIn("line2\n", report)
        self.assertNotIn("| Annotator |", report)
        self.assertNotIn("Offset", report)
        self.assertNotIn("Candidate Count", report)
        self.assertNotIn("Reason", report)


if __name__ == "__main__":
    unittest.main()
