"""All-candidate BM25 gap heuristics and their conservative acceptance gates."""
import dataclasses
import io
import math
import unittest

from test.test_automatic_conditions import choices, decision, suggestion
from snomed_post_processing.sanitization.conditions import apply_conditions, bm25_assessments, undo_automatic_conditions
from snomed_post_processing.sanitization.decisions_json import read_sanitization_decisions_json, sanitization_decisions_json_text
from snomed_post_processing.sanitization.models import SanitizationStatus
from snomed_post_processing.sanitization.semantic_models import SemanticBm25Candidate, SemanticBm25Suggestion


def bm25_suggestion(scores=(12, 7, 6), *, index=0, document="bm25.txt", list_type="whitelist", codes=None):
    finding = suggestion(index, document=document, list_type=list_type).finding
    candidates = tuple(SemanticBm25Candidate(
        code=(codes[i] if codes else str(200 + i)), fsn=f"Target {i}", score=score, lexical_score=1,
        semantic_tag="finding", active=True, in_whitelist=True, in_blacklist=False,
    ) for i, score in enumerate(scores))
    numeric = [item for item in candidates if isinstance(item.score, (int, float)) and math.isfinite(item.score)]
    first = max(numeric, key=lambda item: item.score) if numeric else (candidates[0] if candidates else None)
    return SemanticBm25Suggestion(
        finding, SanitizationStatus.SEMANTIC_BM25_REPLACEMENT,
        replacement_code=first.code if first else None, replacement_fsn=first.fsn if first else None,
        association_type="BM25", candidates=candidates, candidate_count=len(candidates),
    )


class Bm25ConditionsTest(unittest.TestCase):
    def assess(self, item, **kwargs):
        return bm25_assessments([item], **kwargs)[0]

    def apply(self, items, decisions=None, **kwargs):
        decisions = decisions if decisions is not None else [decision(item, index) for index, item in enumerate(items)]
        return apply_conditions(items, decisions, ["SAME_AS"], choices(items), bm25_enabled=True, **kwargs)

    def test_three_candidate_formula_and_relative_lead(self):
        metrics = self.assess(bm25_suggestion())
        self.assertTrue(metrics["eligible"])
        self.assertAlmostEqual(metrics["dominance"], 5 / 6)
        self.assertAlmostEqual(metrics["relative_lead"], 5 / 12)
        self.assertFalse(self.assess(bm25_suggestion([10, 9.9, 9.89]))["eligible"])
        self.assertFalse(self.assess(bm25_suggestion([10, 8, 5]))["eligible"])

    def test_every_later_gap_is_used_not_just_the_top_three(self):
        self.assertTrue(self.assess(bm25_suggestion([12, 7, 6]))["eligible"])
        four = self.assess(bm25_suggestion([12, 7, 6, 0]))
        self.assertFalse(four["eligible"])
        self.assertEqual(four["largest_later_gap"], 6)
        self.assertAlmostEqual(four["dominance"], 5 / 11)
        five = self.assess(bm25_suggestion([12, 7, 6, 5, 4]))
        self.assertTrue(five["eligible"])
        self.assertEqual(five["candidate_count"], 5)
        self.assertEqual(len(five["scores"]), 5)

    def test_scores_are_sorted_and_target_codes_deduplicated_by_best_score(self):
        item = bm25_suggestion([6, 11, 7, 12], codes=["300", "200", "400", "200"])
        metrics = self.assess(item)
        self.assertTrue(metrics["eligible"])
        self.assertEqual(metrics["scores"], [12, 7, 6])
        self.assertEqual(metrics["candidate_codes"], ["200", "400", "300"])
        self.assertEqual(metrics["target_code"], "200")
        self.assertFalse(self.assess(bm25_suggestion([12, 11, 7], codes=["200", "200", "300"]))["eligible"])

    def test_fewer_than_three_top_ties_and_zero_scores_stay_manual(self):
        for scores in ([], [12], [12, 7], [12, 12, 6], [0, 0, 0], [12, 12 - 1e-10, 6]):
            with self.subTest(scores=scores):
                self.assertFalse(self.assess(bm25_suggestion(scores))["eligible"])
        # Equal runner-up scores are not an ambiguous first place.
        self.assertTrue(self.assess(bm25_suggestion([12, 7, 7, 7]))["eligible"])

    def test_invalid_score_anywhere_is_not_silently_dropped(self):
        for invalid in (float("nan"), float("inf"), -1, None, "6", True):
            with self.subTest(invalid=invalid):
                self.assertFalse(self.assess(bm25_suggestion([12, 7, 6, invalid]))["eligible"])

    def test_only_comparable_known_score_channels_are_allowed(self):
        original = bm25_suggestion()
        snogit = dataclasses.replace(original, candidates=tuple(
            dataclasses.replace(item, source="snogit", source_member="SNOGIT_2026.dat") for item in original.candidates
        ))
        self.assertTrue(self.assess(snogit)["eligible"])
        for changed in (
            dataclasses.replace(original.candidates[1], source="snogit", source_member="SNOGIT_2026.dat"),
            dataclasses.replace(original.candidates[1], source="unknown"),
            dataclasses.replace(original.candidates[1], source_member="another-index"),
        ):
            mixed = dataclasses.replace(original, candidates=(original.candidates[0], changed, original.candidates[2]))
            self.assertFalse(self.assess(mixed)["eligible"])
            self.assertEqual(self.assess(mixed)["candidate_count"], 3)
        unknown_member = dataclasses.replace(original, candidates=tuple(
            dataclasses.replace(item, source="snogit", source_member=None) for item in original.candidates
        ))
        self.assertFalse(self.assess(unknown_member)["eligible"])
        different_member = dataclasses.replace(snogit, candidates=(snogit.candidates[0],
            dataclasses.replace(snogit.candidates[1], source_member="other.dat"), snogit.candidates[2]))
        self.assertFalse(self.assess(different_member)["eligible"])

    def test_source_scope_ignored_duplicates_and_generation_thresholds_still_apply(self):
        item = bm25_suggestion()
        exclusion = dataclasses.replace(item, finding=dataclasses.replace(item.finding, list_type="blacklist"))
        ignored = dataclasses.replace(item, finding=dataclasses.replace(item.finding, ignored=True))
        rejected = dataclasses.replace(item, status=SanitizationStatus.NO_REPLACEMENT, context_candidates=item.candidates, candidates=())
        for blocked in (exclusion, ignored, rejected):
            self.assertFalse(self.assess(blocked)["eligible"])
        self.assertFalse(bm25_assessments([item, exclusion])[0]["eligible"])
        self.assertFalse(bm25_assessments([item, item])[0]["eligible"])

    def test_configurable_thresholds_and_boundary_values(self):
        item = bm25_suggestion([10, 8, 7])  # D=2/3 and M=.2 exactly
        self.assertTrue(self.assess(item)["eligible"])
        self.assertFalse(self.assess(item, min_dominance=0.7)["eligible"])
        self.assertFalse(self.assess(item, min_relative_lead=0.3)["eligible"])
        for invalid in (-0.1, 1.1, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                self.assess(item, min_dominance=invalid)

    def test_bm25_is_opt_in_and_combines_with_historical_as_or(self):
        items = [suggestion(), bm25_suggestion(index=1)]
        initial = [decision(item, index) for index, item in enumerate(items)]
        disabled = apply_conditions(items, initial, ["SAME_AS"], choices(items))
        self.assertEqual([item["apply"] for item in disabled.decisions], [True, False])
        enabled = self.apply(items, initial)
        self.assertEqual([item["apply"] for item in enabled.decisions], [True, True])
        self.assertEqual([item["automatic_condition"]["kind"] for item in enabled.decisions], ["historical_association", "bm25_gap"])

    def test_manual_actions_and_optional_release_exclusions_are_unchanged(self):
        item = bm25_suggestion()
        manual = dict(decision(item, 0), reviewed_by_human=True)
        self.assertEqual(self.apply([item], [manual]).changed, 0)
        # Candidate validity was checked during generation, including optional Active-release exclusions.
        release = dataclasses.replace(item, candidates=tuple(
            dataclasses.replace(candidate, in_whitelist=False, in_blacklist=True) for candidate in item.candidates
        ))
        self.assertEqual(self.apply([release]).changed, 1)

    def test_bm25_provenance_undo_idempotence_and_json_roundtrip(self):
        items = [bm25_suggestion([12, 7, 6, 5, 4])]
        original = [decision(items[0], 0)]
        result = self.apply(items, original)
        evidence = result.decisions[0]["automatic_condition"]
        self.assertEqual(evidence["candidate_count"], 5)
        self.assertEqual(evidence["source"], "snomed_fsn")
        self.assertEqual(evidence["metric"], "first_gap_vs_largest_later_gap")
        restored, _ = read_sanitization_decisions_json(io.StringIO(sanitization_decisions_json_text(result.decisions)))
        self.assertEqual(restored, result.decisions)
        repeated = self.apply(items, result.decisions)
        self.assertEqual(repeated.changed, 0)
        self.assertIsNone(repeated.undo)
        undone = undo_automatic_conditions(restored, result.reviewed_documents, result.undo)
        self.assertEqual(undone.decisions, original)
        self.assertEqual(undone.reviewed_documents, set())


if __name__ == "__main__":
    unittest.main()
