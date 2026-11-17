"""Tie-aware retention, bounded SNOGIT retrieval and honest coverage metadata."""
import dataclasses
import io
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import h5py
import numpy as np

from snomed_post_processing.sanitization.conditions import bm25_assessments
from snomed_post_processing.sanitization.json_io import sanitization_suggestion_from_dict, sanitization_suggestion_to_dict
from snomed_post_processing.sanitization.models import SanitizationStatus
from snomed_post_processing.sanitization.report import write_sanitization_markdown_report
from snomed_post_processing.sanitization.semantic_bm25 import SemanticBm25Resolver, _retain_cutoff_ties
from snomed_post_processing.sanitization.snogit_sidecar import SnogitSidecarBm25Searcher, build_snogit_sidecar
from snomed_post_processing.uima_processing import CriticalFinding


def finding():
    return CriticalFinding(annotator="reviewer", document="doc.txt", code="371881003", covered_text="during",
                           offset=(0, 6), list_type="blacklist", reason="blacklisted", layer="gemtex.Concept")


def write_tied_hdf5(path, count=12, excluded=()):
    codes = ["371881003"] + [str(1000 + i) for i in range(count)]
    with h5py.File(path, "w") as h:
        c = h.create_group("concepts")
        c.attrs.update(release_date="20260401", policy_date="20260401", rf2_view="snapshot")
        dtype = h5py.string_dtype("utf-8")
        c.create_dataset("codes", data=np.array(codes, dtype=object), dtype=dtype)
        c.create_dataset("fsn", data=np.array(["During (attribute)"] + [f"During word{i} (attribute)" for i in range(count)], dtype=object), dtype=dtype)
        c.create_dataset("active", data=np.ones(count + 1, dtype=bool))
        p = h.create_group("policy_views")
        p.create_group("whitelist").create_group("0").create_dataset("concept_index", data=np.arange(1, count + 1))
        p.create_group("blacklist").create_group("0").create_dataset("concept_index", data=np.array([0, *excluded]))
    return codes[1:]


class Bm25TiesTest(unittest.TestCase):
    def test_cutoff_ties_are_not_split_and_rounded_scores_are_not_ties(self):
        scored = [SimpleNamespace(score=score) for score in (10, 9, 8, 8, 8, 8, 8, 7)]
        retained, limits = _retain_cutoff_ties(scored, 5)
        self.assertEqual([item.score for item in retained], [10, 9, 8, 8, 8, 8, 8])
        self.assertFalse(limits)
        retained, _ = _retain_cutoff_ties([SimpleNamespace(score=s) for s in (1.234401, 1.234399)], 1)
        self.assertEqual(len(retained), 1)
        retained, _ = _retain_cutoff_ties([SimpleNamespace(score=s) for s in (1, 1 - 1e-10)], 1)
        self.assertEqual(len(retained), 2)

    def test_real_during_query_retains_all_valid_tied_targets_even_with_limit_one(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "concepts.hdf5"
            codes = write_tied_hdf5(path, excluded=(2,))
            source = path.read_bytes()
            for limit in (1, 5):
                with SemanticBm25Resolver(path, max_candidates=limit, min_score=0, min_lexical_score=0, allow_blacklist_findings=True) as resolver:
                    result = resolver.suggest(finding())
                self.assertEqual(result.status, SanitizationStatus.AMBIGUOUS_REPLACEMENT)
                self.assertIsNone(result.replacement_code)
                self.assertEqual(result.candidate_count, 11)
                self.assertEqual({item.code for item in result.candidates}, set(codes) - {codes[1]})
                self.assertFalse(result.retrieval_limits)
                self.assertFalse(bm25_assessments([result])[0]["eligible"])
                self.assertEqual(sanitization_suggestion_from_dict(sanitization_suggestion_to_dict(result)), result)
            self.assertEqual(path.read_bytes(), source)

    def test_safety_cap_is_reported_and_blocks_automatic_conditions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "concepts.hdf5"
            write_tied_hdf5(path)
            with patch("snomed_post_processing.sanitization.semantic_bm25.MAX_TIED_CANDIDATES", 6):
                with SemanticBm25Resolver(path, max_candidates=5, min_score=0, min_lexical_score=0, allow_blacklist_findings=True) as resolver:
                    result = resolver.suggest(finding())
            self.assertEqual(result.candidate_count, 6)
            self.assertEqual(result.retrieval_limits, ("candidate tie limit (6)",))
            restored = sanitization_suggestion_from_dict(sanitization_suggestion_to_dict(result))
            self.assertEqual(restored, result)
            output = io.StringIO()
            write_sanitization_markdown_report([result], output)
            self.assertIn("Retrieval limits reached", output.getvalue())
            # Even a numerically clear inclusion-source leader cannot auto-qualify with partial retrieval.
            comparable = dataclasses.replace(result, finding=dataclasses.replace(result.finding, list_type="whitelist"),
                status=SanitizationStatus.SEMANTIC_BM25_REPLACEMENT,
                candidates=tuple(dataclasses.replace(item, score=score) for item, score in zip(result.candidates, (12, 7, 6))))
            assessment = bm25_assessments([comparable])[0]
            self.assertFalse(assessment["eligible"])
            self.assertIn("Retrieval limits", assessment["reason"])

    def test_snogit_cutoff_ties_and_search_limit_signals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            main, raw, cache = root / "concepts.hdf5", root / "SNOGIT_20260401.dat", root / "cache.hdf5"
            codes = write_tied_hdf5(main, count=25)
            raw.write_text("".join(f"{code}\tt{i}\tDuring (attribute)\tduring word{i}\n" for i, code in enumerate(codes)), encoding="utf-16")
            build_snogit_sidecar(hdf5_path=main, snogit_zip_path=raw, output_path=cache)
            with SnogitSidecarBm25Searcher(cache) as searcher:
                hits = searcher.search(["during"], max_hits=5)
                self.assertEqual(len(hits), 25)
                self.assertFalse(searcher.last_search_limits)
                with patch("snomed_post_processing.sanitization.snogit_sidecar.MAX_TIED_SNOGIT_HITS", 7):
                    self.assertEqual(len(searcher.search(["during"], max_hits=5)), 7)
                    self.assertIn("SNOGIT tied-hit limit (7)", searcher.last_search_limits)
                    self.assertIn("SNOGIT hit limit", searcher.last_search_limits)
                self.assertFalse(searcher.search(["during"], max_postings_per_token=1))
                self.assertIn("SNOGIT postings limit", searcher.last_search_limits)
                self.assertFalse(searcher.search(["during"], max_candidate_rows=1))
                self.assertIn("SNOGIT candidate-row limit", searcher.last_search_limits)
                self.assertEqual(len(searcher.search(["during"], max_hits=5)), 25)
                self.assertFalse(searcher.last_search_limits)

    def test_cached_snogit_queries_restore_their_own_limit_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "concepts.hdf5"
            write_tied_hdf5(path)
            with SemanticBm25Resolver(path) as resolver:
                searcher = Mock()
                searcher.search.return_value = []
                searcher.last_search_limits = ("SNOGIT hit limit",)
                resolver._snogit_searcher = searcher
                resolver._search_snogit_cached(["during"])
                self.assertTrue(resolver._snogit_retrieval_limits)
                searcher.last_search_limits = ()
                resolver._search_snogit_cached(["other"])
                self.assertFalse(resolver._snogit_retrieval_limits)
                resolver._search_snogit_cached(["during"])
                self.assertEqual(resolver._snogit_retrieval_limits, ("SNOGIT hit limit",))
                self.assertEqual(searcher.search.call_count, 2)


if __name__ == "__main__":
    unittest.main()
