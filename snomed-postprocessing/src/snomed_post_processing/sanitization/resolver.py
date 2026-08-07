"""Historical-association based sanitization resolver."""

from __future__ import annotations

import pathlib
from typing import Sequence, Union

import h5py
import numpy as np

from ..hdf5_policy import (
    read_concepts,
    read_historical_associations,
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
    ):
        self.hdf5_path = pathlib.Path(hdf5_path)
        self.allowed_association_types = frozenset(allowed_association_types)
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
        if not candidates:
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.NO_HISTORICAL_ASSOCIATION,
                reason="no active allowed historical association found for source concept",
            )

        acceptable = [candidate for candidate in candidates if candidate.policy_acceptable]
        if not acceptable:
            return SanitizationSuggestion(
                finding=finding,
                status=SanitizationStatus.NO_POLICY_ACCEPTABLE_CANDIDATE,
                reason="historical associations exist, but no candidate satisfies active/whitelist/blacklist policy",
                candidate_count=len(candidates),
                candidates=tuple(candidates),
            )

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


def suggest_sanitization(
    finding: CriticalFinding,
    hdf5_path: Union[str, pathlib.Path],
    allowed_association_types: Sequence[str] = DEFAULT_ALLOWED_ASSOCIATION_TYPES,
) -> SanitizationSuggestion:
    return SanitizationResolver(hdf5_path, allowed_association_types).suggest(finding)
