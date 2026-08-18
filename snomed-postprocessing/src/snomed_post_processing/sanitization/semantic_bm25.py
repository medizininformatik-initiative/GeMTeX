"""Semantic BM25 replacement suggestions for SNOMED sanitization.

This module implements a conservative, dependency-free BM25 scorer over SNOMED
concept labels from the compact HDF5 layout. It is intended as a suggestion-only
fallback when structured historical associations do not yield a replacement.
"""

from __future__ import annotations

import dataclasses
import math
import pathlib
from typing import Optional, Sequence, Union

import h5py

from ..uima_processing import CriticalFinding
from ..hdf5_handling.policy import read_concepts, read_policy_indices, require_bm25_ready
from .bm25_index import BM25Index
from .models import SanitizationStatus
from .semantic_models import SemanticBm25Candidate, SemanticBm25Suggestion
from .semantic_text import _query_text, _semantic_tag, _tokenize

class SemanticBm25Resolver:
    """Suggest policy-acceptable replacements using BM25 over concept labels.

    The resolver indexes active, whitelisted, non-blacklisted concepts from the
    compact HDF5 policy views. It only returns suggestions for whitelist
    findings by default. Blacklist findings remain unresolved because replacing
    intentionally forbidden concepts requires explicit, separate review rules.
    """

    def __init__(
        self,
        hdf5_path: Union[str, pathlib.Path],
        *,
        min_score: float = 1.5,
        min_lexical_score: float = 0.15,
        max_candidates: int = 5,
        k1: float = 1.5,
        b: float = 0.75,
        use_semantic_tag_boost: bool = True,
        allow_blacklist_findings: bool = False,
    ):
        self.hdf5_path = pathlib.Path(hdf5_path)
        self.min_score = float(min_score)
        self.min_lexical_score = float(min_lexical_score)
        self.max_candidates = int(max_candidates)
        self.k1 = float(k1)
        self.b = float(b)
        self.use_semantic_tag_boost = bool(use_semantic_tag_boost)
        self.allow_blacklist_findings = bool(allow_blacklist_findings)
        self._load()
        self._build_index()

    def suggest(self, finding: CriticalFinding) -> SemanticBm25Suggestion:
        if finding.ignored:
            return SemanticBm25Suggestion(
                finding=finding,
                status=SanitizationStatus.NO_REPLACEMENT,
                reason="ignored findings are informational and are not sanitized",
            )
        if finding.list_type == "blacklist" and not self.allow_blacklist_findings:
            return SemanticBm25Suggestion(
                finding=finding,
                status=SanitizationStatus.BLACKLISTED_NO_AUTO_SANITIZATION,
                reason="BM25 fallback for blacklist findings is disabled by default",
            )
        if finding.list_type not in {"whitelist", "blacklist"}:
            return SemanticBm25Suggestion(
                finding=finding,
                status=SanitizationStatus.NO_REPLACEMENT,
                reason=f"unsupported finding list type: {finding.list_type}",
            )

        source_fsn = self.fsn_by_code(finding.code)
        if not finding.fsn and source_fsn:
            finding = dataclasses.replace(finding, fsn=source_fsn)

        query = _query_text(finding, source_fsn)
        query_tokens = _tokenize(query)
        if not query_tokens:
            return SemanticBm25Suggestion(
                finding=finding,
                status=SanitizationStatus.NO_REPLACEMENT,
                reason="finding has no searchable text",
            )

        scored = self._score(query_tokens, source_code=finding.code)
        candidates = tuple(scored[: self.max_candidates])
        if not candidates:
            return SemanticBm25Suggestion(
                finding=finding,
                status=SanitizationStatus.NO_REPLACEMENT,
                reason="no policy-acceptable BM25 candidate found",
            )

        best = candidates[0]
        if best.score < self.min_score or best.lexical_score < self.min_lexical_score:
            return SemanticBm25Suggestion(
                finding=finding,
                status=SanitizationStatus.NO_REPLACEMENT,
                reason=(
                    "best BM25 candidate did not satisfy score thresholds "
                    f"(score={best.score:.3f}, lexical={best.lexical_score:.3f})"
                ),
                score=best.score,
                candidate_count=len(candidates),
                candidates=candidates,
            )

        tied = [candidate for candidate in candidates if math.isclose(candidate.score, best.score, rel_tol=1e-9, abs_tol=1e-9)]
        if len({candidate.code for candidate in tied}) > 1:
            return SemanticBm25Suggestion(
                finding=finding,
                status=SanitizationStatus.AMBIGUOUS_REPLACEMENT,
                reason="multiple BM25 candidates share the best score",
                score=best.score,
                candidate_count=len(candidates),
                candidates=candidates,
            )

        return SemanticBm25Suggestion(
            finding=finding,
            status=SanitizationStatus.SEMANTIC_BM25_REPLACEMENT,
            replacement_code=best.code,
            replacement_fsn=best.fsn,
            association_type="BM25",
            reason="single policy-acceptable BM25 replacement candidate found",
            score=best.score,
            candidate_count=len(candidates),
            candidates=candidates,
        )

    def suggest_all(self, findings: Sequence[CriticalFinding]) -> list[SemanticBm25Suggestion]:
        return [self.suggest(finding) for finding in findings]

    def _load(self):
        with h5py.File(self.hdf5_path, "r") as h5_file:
            require_bm25_ready(h5_file)
            concepts = read_concepts(h5_file)
            self.codes = concepts.codes
            self.fsn = concepts.fsn
            self.code_to_index = concepts.code_to_index
            self.active = concepts.active
            self.whitelist_indices = read_policy_indices(h5_file, "whitelist")
            self.blacklist_indices = read_policy_indices(h5_file, "blacklist")

    def _build_index(self):
        self.document_indices = [
            idx
            for idx in sorted(self.whitelist_indices)
            if 0 <= idx < len(self.codes)
            and bool(self.active[idx])
            and idx not in self.blacklist_indices
            and self.fsn[idx]
        ]
        self.documents = [_tokenize(self.fsn[idx]) for idx in self.document_indices]
        self.bm25_index = BM25Index(self.documents, k1=self.k1, b=self.b)

    def _score(self, query_tokens: Sequence[str], source_code: Optional[str]) -> list[SemanticBm25Candidate]:
        query_terms = list(dict.fromkeys(query_tokens))
        query_set = set(query_tokens)
        source_tag = _semantic_tag(self.fsn_by_code(source_code)) if source_code else None
        scored: list[SemanticBm25Candidate] = []
        for hit in self.bm25_index.search(query_terms):
            local_idx = hit.document_id
            concept_idx = self.document_indices[local_idx]
            code = self.codes[concept_idx]
            if source_code and code == source_code:
                continue
            doc_set = set(self.documents[local_idx])
            lexical_score = len(query_set & doc_set) / max(len(query_set), 1)
            semantic_tag = _semantic_tag(self.fsn[concept_idx])
            score = hit.score
            if self.use_semantic_tag_boost and source_tag and semantic_tag == source_tag:
                score *= 1.1
            scored.append(
                SemanticBm25Candidate(
                    code=code,
                    fsn=self.fsn[concept_idx],
                    score=score,
                    lexical_score=lexical_score,
                    semantic_tag=semantic_tag,
                    active=bool(self.active[concept_idx]),
                    in_whitelist=concept_idx in self.whitelist_indices,
                    in_blacklist=concept_idx in self.blacklist_indices,
                )
            )
        scored.sort(key=lambda candidate: (-candidate.score, -candidate.lexical_score, candidate.code))
        return scored

    def fsn_by_code(self, code: Optional[str]) -> Optional[str]:
        if not code:
            return None
        idx = self.code_to_index.get(code)
        if idx is None:
            return None
        return self.fsn[idx]


def suggest_semantic_bm25(
    finding: CriticalFinding,
    hdf5_path: Union[str, pathlib.Path],
    **kwargs,
) -> SemanticBm25Suggestion:
    """Suggest a policy-acceptable replacement using the BM25 fallback."""
    return SemanticBm25Resolver(hdf5_path, **kwargs).suggest(finding)


def apply_semantic_bm25_fallback(
    suggestions: Sequence,
    hdf5_path: Union[str, pathlib.Path],
    *,
    allow_blacklist_findings: bool = False,
    **kwargs,
) -> list:
    """Replace unresolved whitelist suggestions with BM25 replacements when possible.

    Historical-association suggestions remain authoritative. BM25 is consulted
    only for actionable whitelist findings that do not already have a
    replacement. If ``allow_blacklist_findings`` is true, BM25 is also consulted
    for actionable blacklist findings; candidates must still be active,
    whitelisted, and not blacklisted. If BM25 does not pass thresholds, the
    original suggestion is kept so its original failure reason remains visible.
    """
    resolver = SemanticBm25Resolver(
        hdf5_path,
        allow_blacklist_findings=allow_blacklist_findings,
        **kwargs,
    )
    enhanced = []
    for suggestion in suggestions:
        finding = suggestion.finding
        if (
            getattr(suggestion, "replacement_code", None) is None
            and not finding.ignored
            and (
                finding.list_type == "whitelist"
                or (allow_blacklist_findings and finding.list_type == "blacklist")
            )
        ):
            bm25_suggestion = resolver.suggest(finding)
            if (
                bm25_suggestion.replacement_code is not None
                or bm25_suggestion.status == SanitizationStatus.AMBIGUOUS_REPLACEMENT
            ):
                enhanced.append(
                    dataclasses.replace(
                        bm25_suggestion,
                        context_candidates=tuple(getattr(suggestion, "candidates", ())),
                    )
                )
                continue
        enhanced.append(suggestion)
    return enhanced
