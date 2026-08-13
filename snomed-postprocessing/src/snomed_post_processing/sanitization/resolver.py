"""Historical-association based sanitization resolver."""

from __future__ import annotations

import pathlib
from typing import Sequence, Union

import h5py
import numpy as np

from ..hdf5_handling.policy import (
    has_active_ancestor_arrays,
    has_is_a_relationships,
    read_active_ancestors,
    read_concepts,
    read_historical_associations,
    read_is_a_relationships,
    read_policy_indices,
    require_sanitization_ready,
)
from ..uima_processing import CriticalFinding
from .models import (
    DEFAULT_ALLOWED_ASSOCIATION_TYPES,
    SanitizationCandidate,
    SanitizationStatus,
    SanitizationSuggestion,
)


class SanitizationResolver:
    """Resolve ``CriticalFinding`` objects against a compact SNOMED HDF5 file."""

    def __init__(
        self,
        hdf5_path: Union[str, pathlib.Path],
        allowed_association_types: Sequence[str] = DEFAULT_ALLOWED_ASSOCIATION_TYPES,
        *,
        activate_historical_ancestor_fallback: bool = False,
        ancestor_max_distance: int = 3,
    ):
        self.hdf5_path = pathlib.Path(hdf5_path)
        self.allowed_association_types = frozenset(allowed_association_types)
        self.activate_historical_ancestor_fallback = bool(activate_historical_ancestor_fallback)
        self.ancestor_max_distance = int(ancestor_max_distance)
        self._load()

    def _load(self):
        with h5py.File(self.hdf5_path, "r") as h5_file:
            require_sanitization_ready(h5_file)
            concepts = read_concepts(h5_file)
            self.codes = concepts.codes
            self.fsn = concepts.fsn
            self.active = concepts.active
            self.code_to_index = concepts.code_to_index

            self.whitelist_indices = read_policy_indices(h5_file, "whitelist")
            self.blacklist_indices = read_policy_indices(h5_file, "blacklist")

            associations = read_historical_associations(h5_file)
            self.association_source_index = associations.source_index
            self.association_target_index = associations.target_index
            self.association_type_id = associations.association_type_id
            self.association_types = associations.association_types
            self.association_active = associations.active
            self.association_effective_time = associations.effective_time
            self.association_refset_id = associations.refset_id

            self.active_ancestor_index = None
            self.active_ancestor_concept_index = None
            self.active_ancestor_distance = None
            if has_active_ancestor_arrays(h5_file):
                ancestors = read_active_ancestors(h5_file)
                self.active_ancestor_index = ancestors.ancestor_index
                self.active_ancestor_concept_index = ancestors.ancestor_concept_index
                self.active_ancestor_distance = ancestors.ancestor_distance

            self.is_a_parent_by_source: dict[int, list[tuple[int, bool, str]]] = {}
            if has_is_a_relationships(h5_file):
                is_a_relationships = read_is_a_relationships(h5_file)
                for source_idx, parent_idx, active, effective_time in zip(
                    is_a_relationships.source_index,
                    is_a_relationships.parent_index,
                    is_a_relationships.active,
                    is_a_relationships.effective_time,
                ):
                    self.is_a_parent_by_source.setdefault(int(source_idx), []).append(
                        (int(parent_idx), bool(active), effective_time)
                    )

    def suggest(self, finding: CriticalFinding) -> SanitizationSuggestion:
        if finding.ignored:
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.NO_REPLACEMENT,
                reason="ignored findings are informational and are not sanitized",
            )
        if finding.list_type == "blacklist":
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.BLACKLISTED_NO_AUTO_SANITIZATION,
                reason="automatic sanitization for blacklist findings is disabled",
            )
        if finding.list_type != "whitelist":
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.NO_REPLACEMENT,
                reason=f"unsupported finding list type: {finding.list_type}",
            )
        if not finding.code:
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.NO_REPLACEMENT,
                reason="finding has no SNOMED CT code",
            )

        source_index = self.code_to_index.get(finding.code)
        if source_index is None:
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.NO_HISTORICAL_ASSOCIATION,
                reason="source concept is not present in /concepts",
            )

        candidates = self._historical_candidates(source_index)
        acceptable = [candidate for candidate in candidates if candidate.policy_acceptable]
        if acceptable:
            unique_targets = {(candidate.code, candidate.association_type) for candidate in acceptable}
            if len({candidate.code for candidate in acceptable}) > 1:
                return SanitizationSuggestion(
                    finding=finding,
                    status=SanitizationStatus.AMBIGUOUS_REPLACEMENT,
                    reason="multiple policy-acceptable replacement targets found",
                    candidate_count=len(acceptable),
                    candidates=tuple(acceptable),
                )

            chosen = acceptable[0]
            if len(unique_targets) > 1:
                # Same replacement code through multiple association types is still
                # deterministic, but expose the ambiguity in the candidate list.
                association_type = ",".join(sorted({candidate.association_type for candidate in acceptable}))
            else:
                association_type = chosen.association_type
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.HISTORICAL_ASSOCIATION_REPLACEMENT,
                replacement_code=chosen.code,
                replacement_fsn=chosen.fsn,
                association_type=association_type,
                reason="single policy-acceptable historical association replacement found",
                candidate_count=len(acceptable),
                candidates=tuple(acceptable),
            )

        ancestor_suggestion = self._ancestor_suggestion(finding, source_index)
        if ancestor_suggestion is not None:
            return ancestor_suggestion

        if candidates:
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.NO_POLICY_ACCEPTABLE_CANDIDATE,
                reason="historical associations exist, but no candidate satisfies active/whitelist/blacklist policy",
                candidate_count=len(candidates),
                candidates=tuple(candidates),
            )

        return SanitizationSuggestion(
            finding=finding,
            status=SanitizationStatus.NO_HISTORICAL_ASSOCIATION,
            reason="no active allowed historical association found for source concept",
        )

    def suggest_all(self, findings: Sequence[CriticalFinding]) -> list[SanitizationSuggestion]:
        return [self.suggest(finding) for finding in findings]

    def _historical_candidates(self, source_index: int) -> list[SanitizationCandidate]:
        row_indices = np.where(
            (self.association_source_index == source_index) & self.association_active
        )[0]
        candidates: list[SanitizationCandidate] = []
        for row_index in row_indices:
            association_type = self.association_types[int(self.association_type_id[row_index])]
            if association_type not in self.allowed_association_types:
                continue
            target_index = int(self.association_target_index[row_index])
            if target_index < 0 or target_index >= len(self.codes):
                continue
            candidates.append(
                SanitizationCandidate(
                    code=self.codes[target_index],
                    fsn=self.fsn[target_index] or None,
                    association_type=association_type,
                    active=bool(self.active[target_index]),
                    in_whitelist=target_index in self.whitelist_indices,
                    in_blacklist=target_index in self.blacklist_indices,
                    effective_time=self.association_effective_time[row_index] or None,
                    refset_id=self.association_refset_id[row_index] or None,
                )
            )
        return candidates

    def _ancestor_suggestion(
        self,
        finding: CriticalFinding,
        source_index: int,
    ) -> SanitizationSuggestion | None:
        if not self.activate_historical_ancestor_fallback:
            return None

        active_candidates = self._active_ancestor_candidates(source_index)
        if active_candidates:
            return self._select_ancestor_suggestion(
                finding,
                active_candidates,
                SanitizationStatus.NEAREST_TARGET_ANCESTOR,
                "nearest active policy-acceptable ancestor found",
            )

        historical_candidates = self._historical_ancestor_candidates(source_index)
        if historical_candidates:
            return self._select_ancestor_suggestion(
                finding,
                historical_candidates,
                SanitizationStatus.NEAREST_HISTORICAL_ANCESTOR,
                "nearest policy-acceptable ancestor found via historical/inactive is-a traversal",
            )
        return None

    def _select_ancestor_suggestion(
        self,
        finding: CriticalFinding,
        candidates: list[tuple[int, int, str, str | None]],
        success_status: SanitizationStatus,
        reason: str,
    ) -> SanitizationSuggestion:
        min_distance = min(distance for _idx, distance, _assoc, _effective_time in candidates)
        nearest = [candidate for candidate in candidates if candidate[1] == min_distance]
        suggestion_candidates = tuple(
            self._ancestor_candidate(idx, association_type, effective_time)
            for idx, _distance, association_type, effective_time in nearest
        )
        if len({candidate.code for candidate in suggestion_candidates}) > 1:
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.AMBIGUOUS_ANCESTOR,
                reason="multiple equally near policy-acceptable ancestors found",
                candidate_count=len(suggestion_candidates),
                candidates=suggestion_candidates,
            )
        chosen = suggestion_candidates[0]
        return SanitizationSuggestion(
            finding=finding,
            status=success_status,
            replacement_code=chosen.code,
            replacement_fsn=chosen.fsn,
            association_type=chosen.association_type,
            reason=reason,
            candidate_count=len(suggestion_candidates),
            candidates=suggestion_candidates,
        )

    def _active_ancestor_candidates(self, source_index: int) -> list[tuple[int, int, str, str | None]]:
        if (
            self.active_ancestor_index is None
            or self.active_ancestor_concept_index is None
            or self.active_ancestor_distance is None
            or source_index < 0
            or source_index >= len(self.active_ancestor_index)
        ):
            return []
        start, count = self.active_ancestor_index[source_index]
        candidates = []
        for ancestor_idx, distance in zip(
            self.active_ancestor_concept_index[start : start + count],
            self.active_ancestor_distance[start : start + count],
        ):
            ancestor_idx = int(ancestor_idx)
            distance = int(distance)
            if distance > self.ancestor_max_distance:
                continue
            if self._is_policy_acceptable_ancestor(source_index, ancestor_idx):
                candidates.append((ancestor_idx, distance, "IS_A_ACTIVE", None))
        candidates.sort(key=lambda candidate: (candidate[1], self.codes[candidate[0]]))
        return candidates

    def _historical_ancestor_candidates(self, source_index: int) -> list[tuple[int, int, str, str | None]]:
        if not self.is_a_parent_by_source:
            return []
        candidates = []
        queue = [(source_index, 0)]
        best_distance_by_node = {source_index: 0}
        effective_time_by_node: dict[int, str | None] = {}
        while queue:
            current_index, current_distance = queue.pop(0)
            if current_distance >= self.ancestor_max_distance:
                continue
            for parent_index, relationship_active, effective_time in self.is_a_parent_by_source.get(current_index, []):
                next_distance = current_distance + 1
                if best_distance_by_node.get(parent_index, self.ancestor_max_distance + 1) <= next_distance:
                    continue
                best_distance_by_node[parent_index] = next_distance
                effective_time_by_node[parent_index] = effective_time
                if self._is_policy_acceptable_ancestor(source_index, parent_index):
                    association_type = "IS_A_ACTIVE" if relationship_active else "IS_A_HISTORICAL"
                    candidates.append((parent_index, next_distance, association_type, effective_time))
                queue.append((parent_index, next_distance))
        candidates.sort(key=lambda candidate: (candidate[1], self.codes[candidate[0]]))
        return candidates

    def _is_policy_acceptable_ancestor(self, source_index: int, ancestor_index: int) -> bool:
        return (
            ancestor_index != source_index
            and 0 <= ancestor_index < len(self.codes)
            and self.codes[ancestor_index] != "138875005"
            and bool(self.active[ancestor_index])
            and ancestor_index in self.whitelist_indices
            and ancestor_index not in self.blacklist_indices
        )

    def _ancestor_candidate(
        self,
        ancestor_index: int,
        association_type: str,
        effective_time: str | None,
    ) -> SanitizationCandidate:
        return SanitizationCandidate(
            code=self.codes[ancestor_index],
            fsn=self.fsn[ancestor_index] or None,
            association_type=association_type,
            active=bool(self.active[ancestor_index]),
            in_whitelist=ancestor_index in self.whitelist_indices,
            in_blacklist=ancestor_index in self.blacklist_indices,
            effective_time=effective_time,
        )


def suggest_sanitization(
    finding: CriticalFinding,
    hdf5_path: Union[str, pathlib.Path],
    allowed_association_types: Sequence[str] = DEFAULT_ALLOWED_ASSOCIATION_TYPES,
    **kwargs,
) -> SanitizationSuggestion:
    return SanitizationResolver(hdf5_path, allowed_association_types, **kwargs).suggest(finding)
