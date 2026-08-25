"""Historical-association based sanitization resolver."""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Sequence, Union

import h5py
import numpy as np

from ..hdf5_handling.policy import (
    has_active_ancestor_arrays,
    has_depth_to_root_arrays,
    has_historical_is_a_relationships,
    read_active_ancestors,
    read_concepts,
    read_depth_to_root,
    read_historical_associations,
    read_candidate_validity_sets,
    read_historical_is_a_relationships,
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
        ancestor_max_distance: int | None = 3,
        ancestor_max_relative_distance: float | None = 0.35,
        target_view: str = "policy",
        release_exclude_blacklist: bool = True,
    ):
        self.hdf5_path = pathlib.Path(hdf5_path)
        self.allowed_association_types = frozenset(allowed_association_types)
        self.activate_historical_ancestor_fallback = bool(activate_historical_ancestor_fallback)
        self.ancestor_max_distance = (
            None if ancestor_max_distance is None else int(ancestor_max_distance)
        )
        self.ancestor_max_relative_distance = (
            None
            if ancestor_max_relative_distance is None
            else float(ancestor_max_relative_distance)
        )
        if target_view not in {"policy", "release"}:
            raise ValueError(f"Unsupported sanitization target view: {target_view!r}")
        self.target_view = target_view
        self.release_exclude_blacklist = bool(release_exclude_blacklist)
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
            self.candidate_validity_sets = read_candidate_validity_sets(
                h5_file,
                mode=self.target_view,
                exclude_blacklist=self.release_exclude_blacklist,
            )

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

            self.min_depth_to_root = None
            self.max_depth_to_root = None
            if has_depth_to_root_arrays(h5_file):
                depth_to_root = read_depth_to_root(h5_file)
                self.min_depth_to_root = depth_to_root.min_depth_to_root
                self.max_depth_to_root = depth_to_root.max_depth_to_root

            self.historical_is_a_parent_by_source: dict[int, list[tuple[int, str]]] = {}
            if has_historical_is_a_relationships(h5_file):
                historical_is_a = read_historical_is_a_relationships(h5_file)
                for source_idx, parent_idx, effective_time in zip(
                    historical_is_a.source_index,
                    historical_is_a.parent_index,
                    historical_is_a.effective_time,
                ):
                    self.historical_is_a_parent_by_source.setdefault(int(source_idx), []).append(
                        (int(parent_idx), effective_time)
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

        if not finding.fsn and self.fsn[source_index]:
            finding = dataclasses.replace(finding, fsn=self.fsn[source_index])

        candidates = self._historical_candidates(source_index)
        acceptable = [candidate for candidate in candidates if self._is_acceptable_candidate_code(candidate.code)]
        if acceptable:
            unique_targets = {(candidate.code, candidate.association_type) for candidate in acceptable}
            if len({candidate.code for candidate in acceptable}) > 1:
                return SanitizationSuggestion(
                    finding=finding,
                    status=SanitizationStatus.AMBIGUOUS_REPLACEMENT,
                    reason=f"multiple {self.target_view}-acceptable replacement targets found",
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
                reason=f"single {self.target_view}-acceptable historical association replacement found",
                candidate_count=len(acceptable),
                candidates=tuple(acceptable),
            )

        ancestor_suggestion = self._ancestor_suggestion(finding, source_index)
        if ancestor_suggestion is not None:
            return ancestor_suggestion

        ancestor_context = self._ancestor_context_candidates(source_index)
        combined_candidates = tuple(candidates) + tuple(ancestor_context)
        if candidates:
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.NO_POLICY_ACCEPTABLE_CANDIDATE,
                reason=f"historical associations exist, but no candidate satisfies {self.target_view}-view validity or enabled ancestor-distance limits",
                candidate_count=len(combined_candidates),
                candidates=combined_candidates,
            )

        return SanitizationSuggestion(
            finding=finding,
            status=SanitizationStatus.NO_HISTORICAL_ASSOCIATION,
            reason="no active allowed historical association found for source concept",
            candidate_count=len(ancestor_context),
            candidates=tuple(ancestor_context),
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
                f"nearest active {self.target_view}-acceptable ancestor found",
            )

        historical_candidates = self._historical_ancestor_candidates(source_index)
        if historical_candidates:
            return self._select_ancestor_suggestion(
                finding,
                historical_candidates,
                SanitizationStatus.NEAREST_HISTORICAL_ANCESTOR,
                f"nearest {self.target_view}-acceptable ancestor found via historical/inactive is-a traversal",
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
                reason=f"multiple equally near {self.target_view}-acceptable ancestors found",
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

    def _active_ancestor_candidates(
        self,
        source_index: int,
        *,
        distance_offset: int = 0,
        association_type: str = "IS_A_ACTIVE",
        effective_time: str | None = None,
        estimated_source_depth: int | None = None,
        enforce_distance_limits: bool = True,
    ) -> list[tuple[int, int, str, str | None]]:
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
            distance = int(distance) + distance_offset
            if enforce_distance_limits and self.ancestor_max_distance is not None and distance > self.ancestor_max_distance:
                continue
            if self._is_acceptable_ancestor(source_index, ancestor_idx) and (
                not enforce_distance_limits
                or self._is_within_relative_ancestor_distance(
                    source_index,
                    ancestor_idx,
                    distance,
                    estimated_source_depth=estimated_source_depth,
                )
            ):
                candidates.append((ancestor_idx, distance, association_type, effective_time))
        candidates.sort(key=lambda candidate: (candidate[1], self.codes[candidate[0]]))
        return candidates

    def _historical_ancestor_candidates(self, source_index: int) -> list[tuple[int, int, str, str | None]]:
        if not self.historical_is_a_parent_by_source:
            return []
        candidates = []
        queue = [(source_index, 0)]
        best_distance_by_node = {source_index: 0}
        while queue:
            current_index, current_distance = queue.pop(0)
            if self.ancestor_max_distance is not None and current_distance >= self.ancestor_max_distance:
                continue
            for parent_index, effective_time in self.historical_is_a_parent_by_source.get(current_index, []):
                next_distance = current_distance + 1
                previous_best_distance = best_distance_by_node.get(parent_index)
                if previous_best_distance is not None and previous_best_distance <= next_distance:
                    continue
                best_distance_by_node[parent_index] = next_distance
                estimated_source_depth = self._estimated_historical_source_depth(
                    parent_index,
                    next_distance,
                )
                if self._is_acceptable_ancestor(source_index, parent_index) and self._is_within_relative_ancestor_distance(
                    source_index,
                    parent_index,
                    next_distance,
                    estimated_source_depth=estimated_source_depth,
                ):
                    candidates.append((parent_index, next_distance, "IS_A_HISTORICAL", effective_time))
                candidates.extend(
                    self._active_ancestor_candidates(
                        parent_index,
                        distance_offset=next_distance,
                        association_type="IS_A_HISTORICAL_THEN_ACTIVE",
                        effective_time=effective_time,
                        estimated_source_depth=estimated_source_depth,
                    )
                )
                queue.append((parent_index, next_distance))
        candidates.sort(key=lambda candidate: (candidate[1], self.codes[candidate[0]]))
        return candidates

    def _ancestor_context_candidates(self, source_index: int) -> list[SanitizationCandidate]:
        """Return nearest acceptable ancestors rejected by distance limits.

        These are not replacement suggestions. They are preserved as context so
        that a later BM25 fallback report can show the closest structured
        hierarchy candidate alongside the lexical BM25 top-k list.
        """
        if not self.activate_historical_ancestor_fallback:
            return []

        accepted = {
            idx
            for idx, _distance, _association_type, _effective_time in (
                self._active_ancestor_candidates(source_index)
                + self._historical_ancestor_candidates(source_index)
            )
        }
        relaxed = (
            self._active_ancestor_candidates(
                source_index,
                association_type="IS_A_ACTIVE_OUTSIDE_DISTANCE_LIMIT",
                enforce_distance_limits=False,
            )
            + self._historical_ancestor_candidates_relaxed(source_index)
        )
        rejected = [candidate for candidate in relaxed if candidate[0] not in accepted]
        if not rejected:
            return []
        min_distance = min(distance for _idx, distance, _association_type, _effective_time in rejected)
        nearest = [candidate for candidate in rejected if candidate[1] == min_distance]
        return [
            self._ancestor_candidate(idx, association_type, effective_time)
            for idx, _distance, association_type, effective_time in nearest
        ]

    def _historical_ancestor_candidates_relaxed(self, source_index: int) -> list[tuple[int, int, str, str | None]]:
        if not self.historical_is_a_parent_by_source:
            return []
        candidates = []
        queue = [(source_index, 0)]
        best_distance_by_node = {source_index: 0}
        while queue:
            current_index, current_distance = queue.pop(0)
            for parent_index, effective_time in self.historical_is_a_parent_by_source.get(current_index, []):
                next_distance = current_distance + 1
                previous_best_distance = best_distance_by_node.get(parent_index)
                if previous_best_distance is not None and previous_best_distance <= next_distance:
                    continue
                best_distance_by_node[parent_index] = next_distance
                estimated_source_depth = self._estimated_historical_source_depth(
                    parent_index,
                    next_distance,
                )
                if self._is_acceptable_ancestor(source_index, parent_index):
                    candidates.append((parent_index, next_distance, "IS_A_HISTORICAL_OUTSIDE_DISTANCE_LIMIT", effective_time))
                candidates.extend(
                    self._active_ancestor_candidates(
                        parent_index,
                        distance_offset=next_distance,
                        association_type="IS_A_HISTORICAL_THEN_ACTIVE_OUTSIDE_DISTANCE_LIMIT",
                        effective_time=effective_time,
                        estimated_source_depth=estimated_source_depth,
                        enforce_distance_limits=False,
                    )
                )
                queue.append((parent_index, next_distance))
        candidates.sort(key=lambda candidate: (candidate[1], self.codes[candidate[0]]))
        return candidates

    def _is_acceptable_candidate_code(self, code: str) -> bool:
        concept_index = self.code_to_index.get(code)
        return concept_index is not None and self._is_acceptable_candidate_index(concept_index)

    def _is_acceptable_candidate_index(self, concept_index: int) -> bool:
        return self.candidate_validity_sets.check_index(concept_index).acceptable

    def _is_acceptable_ancestor(self, source_index: int, ancestor_index: int) -> bool:
        return (
            ancestor_index != source_index
            and 0 <= ancestor_index < len(self.codes)
            and self.codes[ancestor_index] != "138875005"
            and self._is_acceptable_candidate_index(ancestor_index)
        )

    def _is_within_relative_ancestor_distance(
        self,
        source_index: int,
        ancestor_index: int,
        distance: int,
        *,
        estimated_source_depth: int | None = None,
    ) -> bool:
        if self.ancestor_max_relative_distance is None or self.max_depth_to_root is None:
            return True

        source_depth = estimated_source_depth
        if source_depth is None and 0 <= source_index < len(self.max_depth_to_root):
            source_depth = int(self.max_depth_to_root[source_index])
        if (source_depth is None or source_depth <= 0) and 0 <= ancestor_index < len(self.max_depth_to_root):
            ancestor_depth = int(self.max_depth_to_root[ancestor_index])
            if ancestor_depth >= 0:
                source_depth = ancestor_depth + int(distance)

        if source_depth is None or source_depth <= 0:
            return True
        return (int(distance) / source_depth) <= self.ancestor_max_relative_distance

    def _estimated_historical_source_depth(
        self,
        parent_index: int,
        distance_to_parent: int,
    ) -> int | None:
        if self.max_depth_to_root is None or not (0 <= parent_index < len(self.max_depth_to_root)):
            return None
        parent_depth = int(self.max_depth_to_root[parent_index])
        if parent_depth < 0:
            return None
        return parent_depth + int(distance_to_parent)

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
