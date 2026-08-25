import io
import pathlib
import tempfile
import unittest
import zipfile

import h5py
import numpy as np

from snomed_post_processing.sanitization import (
    SanitizationStatus,
    SanitizationSuggestion,
    apply_semantic_bm25_fallback,
    build_snogit_sidecar,
    list_snogit_zip_members,
    search_snogit_sidecar_bm25,
    validate_snogit_sidecar_compatibility,
    write_sanitization_markdown_report,
)
from snomed_post_processing.sanitization.semantic_bm25 import (
    BM25Index,
    SemanticBm25Resolver,
    _query_text,
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
        concepts.attrs["release_date"] = "20260401"
        concepts.attrs["policy_date"] = "20240401"
        concepts.attrs["rf2_view"] = "snapshot"
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
    def test_bm25_index_scores_only_documents_reached_by_query_postings(self):
        index = BM25Index(
            [
                ["alpha", "therapy", "procedure"],
                ["beta", "therapy", "procedure"],
                ["heart", "failure", "disorder"],
            ]
        )

        hits = index.search(["alpha"])

        self.assertEqual([hit.document_id for hit in hits], [0])
        self.assertEqual(hits[0].matched_query_tokens, ("alpha",))
        self.assertIn("alpha", index.inverted)
        self.assertNotIn(2, [doc_id for doc_id, _ in index.inverted["alpha"]])

    def test_query_text_excludes_snomed_code(self):
        query = _query_text(
            _finding(code="123456789", covered_text="alpha therapy"),
            "Old alpha concept (procedure)",
        )

        self.assertEqual(query, "alpha therapy Old alpha concept (procedure)")
        self.assertNotIn("123456789", query)

    def test_fsn_lookup_uses_code_index_map(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_compact_hdf5(hdf5_path)
            resolver = SemanticBm25Resolver(hdf5_path)

        self.assertEqual(resolver.code_to_index["100"], 1)
        self.assertEqual(resolver.fsn_by_code("100"), "Alpha therapy procedure (procedure)")
        self.assertIsNone(resolver.fsn_by_code("missing"))

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

    def test_release_view_bm25_accepts_active_candidate_without_whitelist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_compact_hdf5(hdf5_path, whitelist_indices=(), active=(False, True, True, False))

            policy_suggestion = suggest_semantic_bm25(
                _finding(),
                hdf5_path,
                min_score=0.1,
                min_lexical_score=0.2,
            )
            release_suggestion = suggest_semantic_bm25(
                _finding(),
                hdf5_path,
                min_score=0.1,
                min_lexical_score=0.2,
                target_view="release",
            )

        self.assertEqual(policy_suggestion.status, SanitizationStatus.NO_REPLACEMENT)
        self.assertEqual(release_suggestion.status, SanitizationStatus.SEMANTIC_BM25_REPLACEMENT)
        self.assertEqual(release_suggestion.replacement_code, "100")
        self.assertFalse(release_suggestion.candidates[0].in_whitelist)

    def test_release_view_bm25_optionally_excludes_blacklist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            _write_compact_hdf5(
                hdf5_path,
                whitelist_indices=(),
                blacklist_indices=(1,),
                active=(False, True, True, False),
            )

            excluded = suggest_semantic_bm25(
                _finding(),
                hdf5_path,
                min_score=0.1,
                min_lexical_score=0.5,
                target_view="release",
            )
            allowed = suggest_semantic_bm25(
                _finding(),
                hdf5_path,
                min_score=0.1,
                min_lexical_score=0.5,
                target_view="release",
                release_exclude_blacklist=False,
            )

        self.assertEqual(excluded.status, SanitizationStatus.NO_REPLACEMENT)
        self.assertEqual(allowed.status, SanitizationStatus.SEMANTIC_BM25_REPLACEMENT)
        self.assertEqual(allowed.replacement_code, "100")
        self.assertTrue(allowed.candidates[0].in_blacklist)

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

    def test_snogit_sidecar_defaults_to_newest_general_member(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = pathlib.Path(tmpdir) / "SNOGIT-release.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("release/SNOGIT_ELGA_20260611.dat", "100\telga\tAlpha\tELGA term\n")
                archive.writestr("release/SNOGIT_20260712.dat", "100\tgeneral-new\tAlpha\tGeneral new\n")
                archive.writestr("release/SNOGIT_20250101.dat", "100\tgeneral-old\tAlpha\tGeneral old\n")
                archive.writestr("release/SNOMED_LATIN_FULL_20260713.dat", "100\tAlpha\tLatin\n")

            members = list_snogit_zip_members(zip_path)

        defaults = [member.name for member in members if member.recommended_default]
        self.assertEqual(defaults, ["release/SNOGIT_20260712.dat"])

    def test_builds_minimal_snogit_sidecar_and_validates_hdf5_compatibility(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            hdf5_path = tmpdir / "concepts.hdf5"
            sidecar_path = tmpdir / "snogit-sidecar.hdf5"
            zip_path = tmpdir / "SNOGIT-release.zip"
            _write_compact_hdf5(hdf5_path, blacklist_indices=(3,))
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(
                    "release/SNOGIT_20260712.dat",
                    "100\tt1\tAlpha therapy procedure (procedure)\tHerzinfarkt\n"
                    "100\tt2\tAlpha therapy procedure (procedure)\tHerzinfarkt\n"
                    "300\tt3\tForbidden concept (procedure)\tVerboten\n"
                    "missing\tt4\tUnknown\tUnbekannt\n",
                )

            result = build_snogit_sidecar(
                hdf5_path=hdf5_path,
                snogit_zip_path=zip_path,
                output_path=sidecar_path,
            )

            self.assertEqual(result.selected_members, ("release/SNOGIT_20260712.dat",))
            self.assertEqual(result.rows_written, 1)
            self.assertEqual(result.vocab_size, 1)
            self.assertEqual(result.postings_count, 1)
            self.assertTrue(validate_snogit_sidecar_compatibility(sidecar_path, hdf5_path))
            with h5py.File(sidecar_path, "r") as sidecar:
                self.assertIn("length", sidecar["terms"])
                self.assertIn("index", sidecar)
                self.assertEqual(sidecar["schema"].attrs["version"], "2")
                self.assertEqual(sidecar["terms/length"][:].tolist(), [1])
                self.assertEqual([value.decode("utf-8") for value in sidecar["index/vocab/token"][:]], ["herzinfarkt"])

    def test_snogit_sidecar_inverted_index_query_returns_hits(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            hdf5_path = tmpdir / "concepts.hdf5"
            sidecar_path = tmpdir / "snogit-sidecar.hdf5"
            zip_path = tmpdir / "SNOGIT-release.zip"
            _write_compact_hdf5(hdf5_path, blacklist_indices=(3,))
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(
                    "release/SNOGIT_20260712.dat",
                    "100\tt1\tAlpha therapy procedure (procedure)\tAkuter Herzinfarkt\n"
                    "200\tt2\tBeta diagnosis disorder (disorder)\tHerzinsuffizienz\n",
                )
            build_snogit_sidecar(
                hdf5_path=hdf5_path,
                snogit_zip_path=zip_path,
                output_path=sidecar_path,
            )

            hits = search_snogit_sidecar_bm25(
                sidecar_path,
                ["akuter", "herzinfarkt"],
                hdf5_path=hdf5_path,
            )

        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0].concept_index, 1)
        self.assertEqual(hits[0].term, "Akuter Herzinfarkt")
        self.assertEqual(hits[0].matched_query_tokens, ("akuter", "herzinfarkt"))

    def test_snogit_sidecar_bm25_skips_tokens_exceeding_candidate_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            hdf5_path = tmpdir / "concepts.hdf5"
            sidecar_path = tmpdir / "snogit-sidecar.hdf5"
            zip_path = tmpdir / "SNOGIT-release.zip"
            _write_compact_hdf5(hdf5_path, blacklist_indices=(3,))
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(
                    "release/SNOGIT_20260712.dat",
                    "100\tt1\tAlpha therapy procedure (procedure)\tAkuter gemeinsamer Begriff\n"
                    "200\tt2\tBeta diagnostic procedure (procedure)\tAnderer gemeinsamer Begriff\n",
                )
            build_snogit_sidecar(
                hdf5_path=hdf5_path,
                snogit_zip_path=zip_path,
                output_path=sidecar_path,
            )

            hits = search_snogit_sidecar_bm25(
                sidecar_path,
                ["akuter", "gemeinsamer"],
                hdf5_path=hdf5_path,
                max_candidate_rows=1,
            )

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].concept_index, 1)
        self.assertEqual(hits[0].matched_query_tokens, ("akuter",))

    def test_snogit_sidecar_bm25_reads_ranked_rows_not_sorted_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            hdf5_path = tmpdir / "concepts.hdf5"
            sidecar_path = tmpdir / "snogit-sidecar.hdf5"
            zip_path = tmpdir / "SNOGIT-release.zip"
            _write_compact_hdf5(hdf5_path, blacklist_indices=(3,))
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(
                    "release/SNOGIT_20260712.dat",
                    "200\tt1\tBeta diagnostic procedure (procedure)\tHerzinfarkt\n"
                    "100\tt2\tAlpha therapy procedure (procedure)\tAkuter Herzinfarkt Herzinfarkt\n",
                )
            build_snogit_sidecar(
                hdf5_path=hdf5_path,
                snogit_zip_path=zip_path,
                output_path=sidecar_path,
            )

            hits = search_snogit_sidecar_bm25(
                sidecar_path,
                ["akuter", "herzinfarkt"],
                hdf5_path=hdf5_path,
            )

        self.assertGreaterEqual(len(hits), 2)
        self.assertEqual(hits[0].term_row, 1)
        self.assertEqual(hits[0].concept_index, 1)
        self.assertEqual(hits[0].term, "Akuter Herzinfarkt Herzinfarkt")

    def test_snogit_sidecar_terms_are_used_as_bm25_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            hdf5_path = tmpdir / "concepts.hdf5"
            sidecar_path = tmpdir / "snogit-sidecar.hdf5"
            zip_path = tmpdir / "SNOGIT-release.zip"
            _write_compact_hdf5(hdf5_path, blacklist_indices=(3,))
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(
                    "release/SNOGIT_20260712.dat",
                    "100\tt1\tAlpha therapy procedure (procedure)\tHerzinfarkt\n",
                )
            build_snogit_sidecar(
                hdf5_path=hdf5_path,
                snogit_zip_path=zip_path,
                output_path=sidecar_path,
            )

            suggestion = suggest_semantic_bm25(
                _finding(code="missing-source", covered_text="Herzinfarkt"),
                hdf5_path,
                min_score=0.1,
                min_lexical_score=0.5,
                snogit_sidecar_path=sidecar_path,
            )

        self.assertEqual(suggestion.status, SanitizationStatus.SEMANTIC_BM25_REPLACEMENT)
        self.assertEqual(suggestion.replacement_code, "100")
        self.assertEqual(suggestion.candidates[0].source, "snogit")
        self.assertEqual(suggestion.candidates[0].matched_term, "Herzinfarkt")

    def test_snogit_candidates_do_not_use_source_fsn_query_terms(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            hdf5_path = tmpdir / "concepts.hdf5"
            sidecar_path = tmpdir / "snogit-sidecar.hdf5"
            zip_path = tmpdir / "SNOGIT-release.zip"
            _write_compact_hdf5(hdf5_path, blacklist_indices=(3,))
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(
                    "release/SNOGIT_20260712.dat",
                    "100\tt1\tAlpha therapy procedure (procedure)\tHerzinfarkt\n",
                )
            build_snogit_sidecar(
                hdf5_path=hdf5_path,
                snogit_zip_path=zip_path,
                output_path=sidecar_path,
            )

            suggestion = suggest_semantic_bm25(
                _finding(code="999", covered_text="unrelated annotation text"),
                hdf5_path,
                min_score=0.1,
                min_lexical_score=0.1,
                snogit_sidecar_path=sidecar_path,
            )

        self.assertTrue(all(candidate.source != "snogit" for candidate in suggestion.candidates))

    def test_requires_compact_policy_views(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            with h5py.File(hdf5_path, "w") as h5_file:
                h5_file.create_group("concepts")

            with self.assertRaisesRegex(ValueError, "BM25-sanitization-ready"):
                SemanticBm25Resolver(hdf5_path)


if __name__ == "__main__":
    unittest.main()
