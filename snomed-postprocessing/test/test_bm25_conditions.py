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

    def test_exclusion_opt_in_requires_bm25_and_preserves_provenance_and_undo(self):
        item = bm25_suggestion(list_type="blacklist")
        original = [decision(item, 0)]
        self.assertFalse(self.assess(item)["eligible"])
        self.assertIn("opt-in", self.assess(item)["reason"])
        self.assertTrue(self.assess(item, include_exclusion_findings=True)["eligible"])
        disabled = apply_conditions([item], original, ["SAME_AS"], choices([item]),
                                    bm25_include_exclusion_findings=True)
        self.assertEqual(disabled.changed, 0)
        self.assertEqual(self.apply([item]).changed, 0)
        result = self.apply([item], original, bm25_include_exclusion_findings=True)
        self.assertEqual(result.changed, 1)
        self.assertEqual(result.reviewed_documents, {"bm25.txt"})
        evidence = result.decisions[0]["automatic_condition"]
        self.assertEqual(evidence["kind"], "bm25_gap")
        self.assertEqual(evidence["source_list_type"], "blacklist")
        restored, _ = read_sanitization_decisions_json(io.StringIO(sanitization_decisions_json_text(result.decisions)))
        self.assertEqual(restored, result.decisions)
        repeated = self.apply([item], result.decisions, bm25_include_exclusion_findings=True)
        self.assertEqual(repeated.changed, 0)
        self.assertIsNone(repeated.undo)
        # Disabling the opt-in does not silently clear earlier selections.
        self.assertEqual(self.apply([item], result.decisions).decisions, result.decisions)
        undone = undo_automatic_conditions(restored, result.reviewed_documents, result.undo)
        self.assertEqual(undone.decisions, original)
        self.assertEqual(undone.reviewed_documents, set())

    def test_exclusion_opt_in_keeps_ignored_duplicate_and_unknown_sources_manual(self):
        item = bm25_suggestion(list_type="blacklist")
        inclusion = dataclasses.replace(item, finding=dataclasses.replace(item.finding, list_type="whitelist"))
        ignored = dataclasses.replace(item, finding=dataclasses.replace(item.finding, ignored=True))
        unknown = dataclasses.replace(item, finding=dataclasses.replace(item.finding, list_type="other"))
        for items in ([item, item], [item, inclusion], [ignored], [unknown]):
            with self.subTest(items=items):
                assessments = bm25_assessments(items, include_exclusion_findings=True)
                self.assertFalse(any(entry["eligible"] for entry in assessments.values()))
                self.assertEqual(self.apply(items, bm25_include_exclusion_findings=True).changed, 0)

    def test_exclusion_opt_in_does_not_bypass_bm25_candidate_gates(self):
        item = bm25_suggestion(list_type="blacklist")
        blocked = [
            bm25_suggestion([12, 7], list_type="blacklist"),
            bm25_suggestion([12, 12, 6], list_type="blacklist"),
            bm25_suggestion([10, 9.9, 9.89], list_type="blacklist"),
            bm25_suggestion([12, 7, float("nan")], list_type="blacklist"),
            dataclasses.replace(item, retrieval_limits=("SNOGIT hit limit",)),
            dataclasses.replace(item, status=SanitizationStatus.NO_REPLACEMENT,
                                candidates=(), context_candidates=item.candidates),
            dataclasses.replace(item, candidates=(item.candidates[0],
                dataclasses.replace(item.candidates[1], source="snogit", source_member="other"), item.candidates[2])),
        ]
        for proposal in blocked:
            with self.subTest(proposal=proposal):
                self.assertFalse(self.assess(proposal, include_exclusion_findings=True)["eligible"])
                self.assertEqual(self.apply([proposal], bm25_include_exclusion_findings=True).changed, 0)

    def test_exclusion_opt_in_leaves_historical_sources_and_unresolved_documents_manual(self):
        items = [suggestion(document="bm25.txt", list_type="blacklist"),
                 bm25_suggestion(index=1, list_type="blacklist")]
        result = self.apply(items, bm25_include_exclusion_findings=True)
        self.assertEqual([entry["apply"] for entry in result.decisions], [False, True])
        self.assertEqual(result.reviewed_documents, set())

    def test_exclusion_opt_in_preserves_manual_rule_and_review_protections(self):
        item = bm25_suggestion(list_type="blacklist")
        original = decision(item, 0)
        variants = [dict(original, reviewed_by_human=True), dict(original, apply=True, action="replace"),
                    dict(original, manual_edit=True, action="manual_edit"),
                    dict(original, delete_annotation=True, action="delete"),
                    dict(original, concept_rule={"rule_id": "explicit"})]
        for prior in variants:
            with self.subTest(prior=prior):
                self.assertEqual(self.apply([item], [prior], bm25_include_exclusion_findings=True).decisions, [prior])
        for protection in ({"reviewed_documents": {"bm25.txt"}}, {"protected_indices": {0}}):
            self.assertEqual(self.apply([item], bm25_include_exclusion_findings=True, **protection).changed, 0)

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
