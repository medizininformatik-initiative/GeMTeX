"""Historical-condition selection/undo without HDF5 or CAS mutation."""
import copy
import dataclasses
import io
import unittest

from snomed_post_processing.sanitization.conditions import (
    DEFAULT_CONDITION_ASSOCIATIONS, apply_conditions, historical_targets, undo_automatic_conditions,
)
from snomed_post_processing.sanitization.models import SanitizationCandidate, SanitizationStatus, SanitizationSuggestion
from snomed_post_processing.sanitization.semantic_models import SemanticBm25Candidate, SemanticBm25Suggestion
from snomed_post_processing.sanitization.decisions_json import sanitization_decisions_json_text, read_sanitization_decisions_json
from snomed_post_processing.uima_processing import CriticalFinding


def candidate(code="200", association="SAME_AS", excluded=False):
    return SanitizationCandidate(code, f"Target {code} (finding)", association, True, True, excluded)


def suggestion(index=0, *, document="doc", list_type="whitelist", candidates=None):
    candidates = tuple(candidates if candidates is not None else [candidate()])
    return SanitizationSuggestion(
        CriticalFinding("alice", document, str(1000 + index), "example", (index, index + 1),
                        list_type, "not_in_whitelist" if list_type == "whitelist" else "blacklisted", layer="L"),
        SanitizationStatus.HISTORICAL_ASSOCIATION_REPLACEMENT if len(candidates) == 1 else SanitizationStatus.AMBIGUOUS_REPLACEMENT,
        replacement_code=candidates[0].code if len(candidates) == 1 else None,
        replacement_fsn=candidates[0].fsn if len(candidates) == 1 else None,
        candidates=candidates, candidate_count=len(candidates),
    )


def decision(item, index):
    first = item.candidates[0] if item.candidates else None
    return dict(suggestion_index=index, document=item.finding.document, annotator=item.finding.annotator,
                layer=item.finding.layer, offset=list(item.finding.offset), source_code=item.finding.code,
                covered_text=item.finding.covered_text, action="none", apply=False, delete_annotation=False,
                manual_edit=False, reviewed_by_human=False, resolved=False,
                replacement_code=first.code if first else None, replacement_fsn=first.fsn if first else None,
                replacement_choice=f"{first.code} — {first.fsn}" if first else "— no replacement selected —",
                valid_choice=first is not None)


def choices(suggestions):
    return {i: tuple(f"{item.code} — {item.fsn}" for item in suggestion.candidates)
            for i, suggestion in enumerate(suggestions)}


class AutomaticConditionsTest(unittest.TestCase):
    def apply(self, suggestions, decisions=None, allowed=DEFAULT_CONDITION_ASSOCIATIONS, reviewed=(), protected=()):
        if decisions is None:
            decisions = [decision(item, index) for index, item in enumerate(suggestions)]
        return apply_conditions(suggestions, decisions, allowed, choices(suggestions), reviewed, protected)

    def test_only_inclusion_sources_and_unique_targets(self):
        items = [suggestion(), suggestion(1, list_type="blacklist"),
                 suggestion(2, candidates=[candidate(), candidate("300")])]
        result = self.apply(items)
        self.assertEqual([item["apply"] for item in result.decisions], [True, False, False])
        self.assertTrue(result.decisions[0]["resolved"])
        self.assertEqual(result.changed, 1)
        self.assertEqual(result.reviewed_documents, set())

    def test_same_annotation_with_exclusion_finding_cannot_be_approved(self):
        inclusion = suggestion()
        exclusion = dataclasses.replace(inclusion, finding=dataclasses.replace(inclusion.finding, list_type="blacklist"))
        self.assertEqual(historical_targets([inclusion, exclusion], DEFAULT_CONDITION_ASSOCIATIONS), {})

    def test_duplicate_source_rows_are_not_double_targeted(self):
        item = suggestion()
        self.assertEqual(self.apply([item, item]).changed, 0)

    def test_association_types_are_evaluated_on_candidates_not_joined_summary(self):
        item = suggestion(candidates=[candidate("200", "SAME_AS"), candidate("200", "REPLACED_BY"), candidate("300", "SIMILAR_TO")])
        item = dataclasses.replace(item, association_type="SAME_AS,REPLACED_BY,SIMILAR_TO")
        result = self.apply([item], allowed=["SAME_AS", "REPLACED_BY"])
        self.assertEqual(result.changed, 1)
        self.assertEqual(result.decisions[0]["replacement_code"], "200")
        self.assertEqual(result.decisions[0]["automatic_condition"]["association_types"], ["REPLACED_BY", "SAME_AS"])
        self.assertEqual(self.apply([item]).changed, 0)
        self.assertEqual(self.apply([item], allowed=[]).changed, 0)

    def test_selected_condition_can_choose_nonfirst_target(self):
        item = suggestion(candidates=[candidate("200", "SIMILAR_TO"), candidate("300", "SAME_AS")])
        result = self.apply([item], allowed=["SAME_AS"])
        self.assertEqual(result.decisions[0]["replacement_code"], "300")
        self.assertTrue(result.decisions[0]["replacement_choice"].startswith("300 —"))

    def test_diagnostics_ancestors_ignored_and_bm25_are_not_automated(self):
        base = suggestion()
        diagnostic = dataclasses.replace(base, status=SanitizationStatus.NO_POLICY_ACCEPTABLE_CANDIDATE,
                                         candidates=(), candidate_count=0, context_candidates=base.candidates)
        ancestor = dataclasses.replace(base, status=SanitizationStatus.NEAREST_TARGET_ANCESTOR)
        ignored = dataclasses.replace(base, finding=dataclasses.replace(base.finding, ignored=True))
        bm25 = SemanticBm25Suggestion(base.finding, SanitizationStatus.AMBIGUOUS_REPLACEMENT,
            candidates=(SemanticBm25Candidate("200", "Target", 10000, 1, "finding", True, True, False),))
        for item in (diagnostic, ancestor, ignored, bm25):
            with self.subTest(item=type(item).__name__, status=item.status):
                self.assertEqual(self.apply([item]).changed, 0)

    def test_release_candidate_flags_are_not_reinterpreted_as_strict_policy(self):
        # Generation already applied the chosen view. Embedded exclusion may be disabled in Active release.
        result = self.apply([suggestion(candidates=[dataclasses.replace(candidate(excluded=True), in_whitelist=False)])])
        self.assertEqual(result.changed, 1)

    def test_existing_manual_actions_keeps_rules_and_reviewed_documents_are_protected(self):
        item = suggestion()
        original = decision(item, 0)
        variants = [dict(original, reviewed_by_human=True), dict(original, apply=True, action="replace"),
                    dict(original, manual_edit=True, action="manual_edit"),
                    dict(original, delete_annotation=True, action="delete"), dict(original, concept_rule={"rule_id": "explicit"})]
        for prior in variants:
            with self.subTest(prior=prior):
                self.assertEqual(self.apply([item], [prior]).decisions, [prior])
        self.assertEqual(self.apply([item], reviewed={"doc"}).changed, 0)
        self.assertEqual(self.apply([item], protected={0}).changed, 0)

    def test_complete_documents_resolve_and_undo_restores_previous_state(self):
        items = [suggestion(), suggestion(1)]
        original = [decision(item, i) for i, item in enumerate(items)]
        result = self.apply(items, original)
        self.assertEqual(result.reviewed_documents, {"doc"})
        self.assertEqual(result.changed, 2)
        undone = undo_automatic_conditions(result.decisions, result.reviewed_documents, result.undo)
        self.assertEqual(undone.decisions, original)
        self.assertEqual(undone.reviewed_documents, set())
        self.assertEqual(original[0]["apply"], False)  # input was not mutated

    def test_undo_preserves_later_manual_edits_and_document_review(self):
        items = [suggestion(), suggestion(1)]
        result = self.apply(items)
        changed = copy.deepcopy(result.decisions)
        changed[0].update(apply=False, action="none", reviewed_by_human=True)
        undone = undo_automatic_conditions(changed, {"doc"}, result.undo)
        self.assertEqual(undone.changed, 1)
        self.assertEqual(undone.skipped, 1)
        self.assertEqual(undone.decisions[0], changed[0])
        self.assertEqual(undone.reviewed_documents, {"doc"})
        protected = undo_automatic_conditions(result.decisions, {"doc"}, result.undo, {"doc"})
        self.assertEqual(protected.changed, 0)

    def test_selected_condition_uses_existing_cas_writeback_without_other_feature_changes(self):
        import cassis
        from test import test_concept_rules as fixtures
        from snomed_post_processing.pipelines.sanitization_run import sanitize_cas_bytes

        fixture = fixtures.ConceptRulesTest("test_defaults_and_rule_json_roundtrip")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        original = fixture.preview(documents=["one.txt"], annotators=["alice"])[1]
        finding = CriticalFinding(
            original["annotator"], original["document"], original["source_code"], original["covered_text"],
            tuple(original["offset"]), "whitelist", "not_in_whitelist", layer=original["layer"],
        )
        item = dataclasses.replace(suggestion(candidates=[candidate("999")]), finding=finding)
        result = self.apply([item])
        written = sanitize_cas_bytes(fixture.cas.to_json().encode(), result.decisions, cas_format="jsoncas")
        self.assertEqual(written.changed_annotation_count, 1)
        changed = cassis.load_cas_from_json(io.BytesIO(written.cas_bytes))
        for before, after in zip(fixture.cas.select("gemtex.Concept"), changed.select("gemtex.Concept")):
            self.assertEqual((before.begin, before.end, before.literal, before.note),
                             (after.begin, after.end, after.literal, after.note))
        self.assertEqual(list(changed.select("gemtex.Concept"))[1].id, "http://snomed.info/id/999")

    def test_repeated_apply_is_idempotent_and_provenance_roundtrips(self):
        items = [suggestion()]
        result = self.apply(items)
        repeated = self.apply(items, result.decisions, reviewed=result.reviewed_documents)
        self.assertEqual(repeated.changed, 0)
        self.assertIsNone(repeated.undo)
        self.assertEqual(repeated.decisions, result.decisions)
        restored, _ = read_sanitization_decisions_json(io.StringIO(sanitization_decisions_json_text(result.decisions)))
        self.assertEqual(restored, result.decisions)


if __name__ == "__main__":
    unittest.main()
