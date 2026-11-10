"""Conditional review selection; never writes CAS files or invents target candidates."""
from __future__ import annotations

import copy
import math
from collections import Counter
from dataclasses import dataclass
from numbers import Real
from typing import Any, Sequence

from .concept_rules import decision_key
from .models import SanitizationStatus
from .semantic_models import SemanticBm25Candidate, SemanticBm25Suggestion

DEFAULT_CONDITION_ASSOCIATIONS = ("SAME_AS", "REPLACED_BY", "WAS_A", "ALTERNATIVE", "SIMILAR_TO")


@dataclass
class ConditionResult:
    decisions: list[dict[str, Any]]
    reviewed_documents: set[str]
    undo: dict[str, Any] | None = None
    changed: int = 0
    skipped: int = 0


def finding_key(finding):
    return (finding.document, finding.annotator, finding.layer, tuple(finding.offset), finding.code or "")


def eligible_source_indices(suggestions):
    excluded = {finding_key(item.finding) for item in suggestions if item.finding.list_type == "blacklist"}
    occurrences = Counter(finding_key(item.finding) for item in suggestions)
    return {index for index, item in enumerate(suggestions)
            if item.finding.list_type == "whitelist" and not item.finding.ignored
            and finding_key(item.finding) not in excluded and occurrences[finding_key(item.finding)] == 1}


def historical_targets(suggestions: Sequence[Any], association_types: Sequence[str]):
    """Use only generated, selectable historical candidates for inclusion-list findings."""
    allowed = set(association_types)
    eligible = eligible_source_indices(suggestions)
    targets = {}
    for index, suggestion in enumerate(suggestions):
        if (index not in eligible or suggestion.status not in (
                SanitizationStatus.HISTORICAL_ASSOCIATION_REPLACEMENT, SanitizationStatus.AMBIGUOUS_REPLACEMENT)):
            continue
        candidates = [item for item in suggestion.candidates if getattr(item, "association_type", None) in allowed]
        codes = {item.code for item in candidates if item.code}
        if len(codes) == 1:
            targets[index] = {
                "kind": "historical_association", "source_list_type": "whitelist",
                "target_code": next(iter(codes)),
                "association_types": sorted({item.association_type for item in candidates}),
                "allowed_association_types": sorted(allowed),
            }
    return targets


def bm25_assessments(suggestions, min_dominance=2 / 3, min_relative_lead=0.20):
    """Assess every saved BM25 candidate, without mixing score channels or inventing targets."""
    for threshold in (min_dominance, min_relative_lead):
        if isinstance(threshold, bool) or not isinstance(threshold, Real) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError("BM25 gap thresholds must be finite numbers between 0 and 1.")
    eligible = eligible_source_indices(suggestions)
    assessments = {}
    for index, suggestion in enumerate(suggestions):
        if not isinstance(suggestion, SemanticBm25Suggestion):
            continue
        assessment = {"kind": "bm25_gap", "source_list_type": suggestion.finding.list_type,
                      "eligible": False, "candidate_count": len({item.code for item in suggestion.candidates
                          if isinstance(item, SemanticBm25Candidate) and isinstance(item.code, str) and item.code}),
                      "min_dominance": float(min_dominance), "min_relative_lead": float(min_relative_lead)}
        assessments[index] = assessment
        if index not in eligible:
            assessment["reason"] = "Source finding is excluded, ignored, duplicated, or not from the inclusion-list check."
            continue
        if suggestion.status not in (SanitizationStatus.SEMANTIC_BM25_REPLACEMENT, SanitizationStatus.AMBIGUOUS_REPLACEMENT):
            assessment["reason"] = "No selectable BM25 proposal passed generation thresholds."
            continue
        if suggestion.retrieval_limits:
            assessment["reason"] = "Retrieval limits reached; additional BM25 candidates may exist."
            continue
        candidates = suggestion.candidates
        if not candidates or any(not isinstance(item, SemanticBm25Candidate) for item in candidates):
            assessment["reason"] = "Missing BM25 candidates."
            continue
        channels = {(item.source, item.source_member) for item in candidates}
        if (len(channels) != 1 or candidates[0].source not in {"snomed_fsn", "snogit"}
                or (candidates[0].source == "snogit" and not candidates[0].source_member)):
            assessment["reason"] = "Mixed or unknown score channels/index members; raw scores are not comparable."
            continue
        if any(not isinstance(item.code, str) or not item.code or isinstance(item.score, bool) or not isinstance(item.score, Real)
               or not math.isfinite(item.score) or item.score < 0 for item in candidates):
            assessment["reason"] = "Missing, negative, or non-finite BM25 scores."
            continue
        best_by_code = {}
        for item in candidates:
            if item.code not in best_by_code or item.score > best_by_code[item.code].score:
                best_by_code[item.code] = item
        ranked = sorted(best_by_code.values(), key=lambda item: (-item.score, item.code))
        scores = [float(item.score) for item in ranked]
        assessment.update(candidate_count=len(ranked), candidate_codes=[item.code for item in ranked],
                          scores=scores, source=ranked[0].source, source_member=ranked[0].source_member)
        if len(ranked) < 3:
            assessment["reason"] = "At least three distinct target codes are required."
            continue
        if scores[0] <= 0 or math.isclose(scores[0], scores[1], rel_tol=1e-9, abs_tol=1e-9):
            assessment["reason"] = "No unique positive first-place score."
            continue
        first_gap = scores[0] - scores[1]
        largest_later_gap = max(left - right for left, right in zip(scores[1:], scores[2:]))
        dominance = first_gap / (first_gap + largest_later_gap)
        relative_lead = first_gap / scores[0]
        passes = (dominance >= min_dominance or math.isclose(dominance, min_dominance, abs_tol=1e-12, rel_tol=0)) and (
            relative_lead >= min_relative_lead or math.isclose(relative_lead, min_relative_lead, abs_tol=1e-12, rel_tol=0))
        assessment.update(target_code=ranked[0].code, metric="first_gap_vs_largest_later_gap",
                          first_gap=first_gap, largest_later_gap=largest_later_gap,
                          dominance=dominance, relative_lead=relative_lead, eligible=bool(passes),
                          reason="Gap conditions met (heuristic)." if passes else "Score gaps do not meet both thresholds.")
    return assessments


def apply_conditions(suggestions, decisions, association_types, choices_by_index,
                     reviewed_documents=(), protected_indices=(), *, bm25_enabled=False,
                     bm25_min_dominance=2 / 3, bm25_min_relative_lead=0.20):
    updated = copy.deepcopy(decisions)
    reviewed = set(reviewed_documents)
    targets = historical_targets(suggestions, association_types)
    if bm25_enabled:
        for index, assessment in bm25_assessments(suggestions, bm25_min_dominance, bm25_min_relative_lead).items():
            if assessment["eligible"]:
                targets.setdefault(index, {key: value for key, value in assessment.items() if key != "eligible"})
    protected = set(protected_indices)
    excluded_keys = {finding_key(item.finding) for item in suggestions if item.finding.list_type == "blacklist"}
    before, after = {}, {}
    for item in updated:
        index = item.get("suggestion_index")
        automatic = item.get("automatic_condition")
        if (index not in targets or index in protected or item.get("concept_rule")
                or decision_key(item) != finding_key(suggestions[index].finding)
                or item.get("reviewed_by_human") or item.get("manual_edit") or item.get("delete_annotation")
                or item.get("action") in ("manual_edit", "delete", "clear_id")
                or (item.get("apply") and not automatic)
                or (item.get("document") in reviewed and not automatic)):
            continue
        condition = targets[index]
        # UI supplies the current row's selectable options, not diagnostic context.
        choices = choices_by_index.get(index, ())
        choice = next((label for label in choices if label.split(" —", 1)[0] == condition["target_code"]), None)
        if choice is None:
            continue
        original = copy.deepcopy(item)
        item.update(action="replace", apply=True, resolved=True, valid_choice=True,
                    replacement_code=condition["target_code"], replacement_choice=choice,
                    replacement_fsn=choice.split(" — ", 1)[1] if " — " in choice else None,
                    automatic_condition=condition)
        if item != original:
            before[index], after[index] = original, copy.deepcopy(item)
    grouped = {}
    for item in updated:
        grouped.setdefault(item["document"], []).append(item)
    newly_reviewed = set()
    for document, items in grouped.items():
        if document in reviewed or not any(item.get("suggestion_index") in after for item in items):
            continue
        if any(decision_key(item) in excluded_keys for item in items):
            continue
        if all(not item.get("manual_edit") and (
            (item.get("apply") and item.get("valid_choice") and
             (item.get("automatic_condition") or item.get("concept_rule")))
            or item.get("reviewed_by_human")
        ) for item in items):
            newly_reviewed.add(document)
    snapshot = {"before": before, "after": after, "documents": sorted(newly_reviewed)} if before or newly_reviewed else None
    return ConditionResult(updated, reviewed | newly_reviewed, snapshot, len(after),
                           sum(not item.get("concept_rule") for item in decisions) - len(after))


def decision_selection(item):
    """Compare editable choices without depending on regenerated display/ranking hints."""
    return (decision_key(item), *(item.get(key) for key in (
        "action", "apply", "delete_annotation", "manual_edit", "replacement_code",
        "replacement_choice", "valid_choice",
    )))


def undo_automatic_conditions(decisions, reviewed_documents, snapshot, protected_documents=()):
    updated = copy.deepcopy(decisions)
    reviewed = set(reviewed_documents)
    protected = set(protected_documents)
    restored = set()
    for position, item in enumerate(updated):
        index = item.get("suggestion_index")
        expected = snapshot["after"].get(index)
        if (expected is None or item.get("document") in protected or item.get("reviewed_by_human")
                or decision_selection(item) != decision_selection(expected)
                or item.get("automatic_condition") != expected.get("automatic_condition")):
            continue
        updated[position] = copy.deepcopy(snapshot["before"][index])
        restored.add(index)
    for document in snapshot["documents"]:
        indices = {index for index, item in snapshot["after"].items() if item["document"] == document}
        if document not in protected and indices.issubset(restored):
            reviewed.discard(document)
    return ConditionResult(updated, reviewed, changed=len(restored), skipped=len(snapshot["after"]) - len(restored))
