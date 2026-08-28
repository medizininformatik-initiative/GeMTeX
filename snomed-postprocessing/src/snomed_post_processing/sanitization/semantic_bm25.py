"""Semantic BM25 replacement suggestions for SNOMED sanitization.

This module implements a conservative, dependency-free BM25 scorer over SNOMED
concept labels from the compact HDF5 layout. It is intended as a suggestion-only
fallback when structured historical associations do not yield a replacement.
"""

from __future__ import annotations

import dataclasses
import math
import pathlib
from typing import Callable, Iterable, Optional, Sequence, Union

import h5py

from ..uima_processing import CriticalFinding
from ..hdf5_handling.policy import read_candidate_validity_sets, read_concepts, read_policy_indices, require_bm25_ready
from .bm25_index import BM25Index
from .models import SanitizationStatus
from .semantic_models import SemanticBm25Candidate, SemanticBm25Suggestion
from .semantic_text import _query_text, _semantic_tag, _tokenize
from .snogit_sidecar import SnogitSidecarBm25Searcher, validate_snogit_sidecar_compatibility

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
        snogit_sidecar_path: Optional[Union[str, pathlib.Path]] = None,
        use_snogit: bool = False,
        target_view: str = "policy",
        release_exclude_blacklist: bool = False,
        runtime_blacklist_indices: Iterable[int] = (),
    ):
        self.hdf5_path = pathlib.Path(hdf5_path)
        self.min_score = float(min_score)
        self.min_lexical_score = float(min_lexical_score)
        self.max_candidates = int(max_candidates)
        self.k1 = float(k1)
        self.b = float(b)
        self.use_semantic_tag_boost = bool(use_semantic_tag_boost)
        self.allow_blacklist_findings = bool(allow_blacklist_findings)
        self.snogit_sidecar_path = pathlib.Path(snogit_sidecar_path) if snogit_sidecar_path else None
        self.use_snogit = bool(use_snogit or snogit_sidecar_path)
        if target_view not in {"policy", "release"}:
            raise ValueError(f"Unsupported BM25 target view: {target_view!r}")
        self.target_view = target_view
        self.release_exclude_blacklist = bool(release_exclude_blacklist)
        self.runtime_blacklist_indices = frozenset(int(idx) for idx in runtime_blacklist_indices)
        self._snogit_searcher: Optional[SnogitSidecarBm25Searcher] = None
        self._snogit_query_cache = {}
        self._load()
        self._build_index()

    def close(self) -> None:
        if self._snogit_searcher is not None:
            self._snogit_searcher.close()
            self._snogit_searcher = None

    def __enter__(self) -> "SemanticBm25Resolver":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self):
        self.close()

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
        snogit_query_tokens = _tokenize(finding.covered_text)
        if not query_tokens and not snogit_query_tokens:
            return SemanticBm25Suggestion(
                finding=finding,
                status=SanitizationStatus.NO_REPLACEMENT,
                reason="finding has no searchable text",
            )

        scored = self._score(query_tokens, source_code=finding.code, snogit_query_tokens=snogit_query_tokens)
        candidates = tuple(scored[: self.max_candidates])
        if not candidates:
            return SemanticBm25Suggestion(
                finding=finding,
                status=SanitizationStatus.NO_REPLACEMENT,
                reason=f"no {self.target_view}-acceptable BM25 candidate found",
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
            reason=f"single {self.target_view}-acceptable BM25 replacement candidate found",
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
            self.candidate_validity_sets = read_candidate_validity_sets(
                h5_file,
                mode=self.target_view,
                exclude_blacklist=self.release_exclude_blacklist,
                runtime_blacklist_indices=self.runtime_blacklist_indices,
            )
        self.snogit_source_member = None
        if self.use_snogit:
            if self.snogit_sidecar_path is None:
                raise ValueError("use_snogit=True requires a processed SNOGIT cache path at BM25 resolver runtime")
            validate_snogit_sidecar_compatibility(
                self.snogit_sidecar_path,
                self.hdf5_path,
                strict=True,
            )
            with h5py.File(self.snogit_sidecar_path, "r") as sidecar:
                if "metadata/source_members" in sidecar:
                    source_members = tuple(
                        value.decode("utf-8") if isinstance(value, bytes) else str(value)
                        for value in sidecar["metadata/source_members"][:]
                    )
                    self.snogit_source_member = ", ".join(source_members) if source_members else None
            self._snogit_searcher = SnogitSidecarBm25Searcher(self.snogit_sidecar_path)

    def _build_index(self):
        self.document_indices = []
        self.documents = []
        self.document_sources = []
        self.document_terms = []
        self.document_source_members = []
        for idx in range(len(self.codes)):
            if self.candidate_validity_sets.check_index(idx).acceptable and self.fsn[idx]:
                self.document_indices.append(idx)
                self.documents.append(_tokenize(self.fsn[idx]))
                self.document_sources.append("snomed_fsn")
                self.document_terms.append(self.fsn[idx])
                self.document_source_members.append(None)
        self.bm25_index = BM25Index(self.documents, k1=self.k1, b=self.b)

    def _score(
        self,
        query_tokens: Sequence[str],
        source_code: Optional[str],
        *,
        snogit_query_tokens: Sequence[str] = (),
    ) -> list[SemanticBm25Candidate]:
        query_terms = list(dict.fromkeys(query_tokens))
        query_set = set(query_tokens)
        snogit_query_terms = list(dict.fromkeys(snogit_query_tokens))
        snogit_query_set = set(snogit_query_tokens)
        source_tag = _semantic_tag(self.fsn_by_code(source_code)) if source_code else None
        best_by_code: dict[str, SemanticBm25Candidate] = {}
        for hit in self.bm25_index.search(query_terms):
            local_idx = hit.document_id
            concept_idx = self.document_indices[local_idx]
            candidate = self._candidate_from_hit(
                concept_idx=concept_idx,
                source_code=source_code,
                query_set=query_set,
                source_tag=source_tag,
                score=hit.score,
                doc_tokens=self.documents[local_idx],
                source=self.document_sources[local_idx],
                matched_term=self.document_terms[local_idx],
                source_member=self.document_source_members[local_idx],
            )
            if candidate is None:
                continue
            previous = best_by_code.get(candidate.code)
            if previous is None or _candidate_rank_key(candidate) < _candidate_rank_key(previous):
                best_by_code[candidate.code] = candidate
        if self._snogit_searcher is not None and snogit_query_terms:
            for hit in self._search_snogit_cached(snogit_query_terms):
                concept_idx = int(hit.concept_index)
                candidate = self._candidate_from_hit(
                    concept_idx=concept_idx,
                    source_code=source_code,
                    query_set=snogit_query_set,
                    source_tag=None,
                    score=hit.score,
                    doc_tokens=_tokenize(hit.term),
                    source="snogit",
                    matched_term=hit.term,
                    source_member=self.snogit_source_member,
                )
                if candidate is None:
                    continue
                previous = best_by_code.get(candidate.code)
                if previous is None or _candidate_rank_key(candidate) < _candidate_rank_key(previous):
                    best_by_code[candidate.code] = candidate
        scored = list(best_by_code.values())
        scored.sort(key=_candidate_rank_key)
        return scored

    def _search_snogit_cached(self, snogit_query_terms: Sequence[str]):
        if self._snogit_searcher is None:
            return ()
        cache_key = tuple(dict.fromkeys(token for token in snogit_query_terms if token))
        if not cache_key:
            return ()
        cached = self._snogit_query_cache.get(cache_key)
        if cached is None:
            cached = tuple(
                self._snogit_searcher.search(
                    cache_key,
                    k1=self.k1,
                    b=self.b,
                    max_hits=max(self.max_candidates * 20, 50),
                )
            )
            self._snogit_query_cache[cache_key] = cached
        return cached

    def _candidate_from_hit(
        self,
        *,
        concept_idx: int,
        source_code: Optional[str],
        query_set: set[str],
        source_tag: Optional[str],
        score: float,
        doc_tokens: Sequence[str],
        source: str,
        matched_term: str,
        source_member: Optional[str],
    ) -> Optional[SemanticBm25Candidate]:
        if not (0 <= concept_idx < len(self.codes)):
            return None
        code = self.codes[concept_idx]
        if source_code and code == source_code:
            return None
        if not self.candidate_validity_sets.check_index(concept_idx).acceptable:
            return None
        doc_set = set(doc_tokens)
        lexical_score = len(query_set & doc_set) / max(len(query_set), 1)
        semantic_tag = _semantic_tag(self.fsn[concept_idx])
        final_score = float(score)
        if self.use_semantic_tag_boost and source_tag and semantic_tag == source_tag:
            final_score *= 1.1
        return SemanticBm25Candidate(
            code=code,
            fsn=self.fsn[concept_idx],
            score=final_score,
            lexical_score=lexical_score,
            semantic_tag=semantic_tag,
            active=bool(self.active[concept_idx]),
            in_whitelist=concept_idx in self.whitelist_indices,
            in_blacklist=concept_idx in self.blacklist_indices or concept_idx in self.runtime_blacklist_indices,
            source=source,
            matched_term=matched_term,
            source_member=source_member,
        )

    def fsn_by_code(self, code: Optional[str]) -> Optional[str]:
        if not code:
            return None
        idx = self.code_to_index.get(code)
        if idx is None:
            return None
        return self.fsn[idx]


def _candidate_rank_key(candidate: SemanticBm25Candidate) -> tuple[float, float, int, str]:
    source_priority = 0 if candidate.source == "snogit" else 1
    return (-candidate.score, -candidate.lexical_score, source_priority, candidate.code)


def suggest_semantic_bm25(
    finding: CriticalFinding,
    hdf5_path: Union[str, pathlib.Path],
    **kwargs,
) -> SemanticBm25Suggestion:
    """Suggest an acceptable replacement using the BM25 fallback."""
    return SemanticBm25Resolver(hdf5_path, **kwargs).suggest(finding)


def apply_semantic_bm25_fallback(
    suggestions: Sequence,
    hdf5_path: Union[str, pathlib.Path],
    *,
    allow_blacklist_findings: bool = False,
    progress_callback: Optional[Callable[[dict[str, object]], None]] = None,
    **kwargs,
) -> list:
    """Replace unresolved whitelist suggestions with BM25 replacements when possible.

    Historical-association suggestions remain authoritative. BM25 is consulted
    only for actionable whitelist findings that do not already have a
    replacement. If ``allow_blacklist_findings`` is true, BM25 is also consulted
    for actionable blacklist findings; candidates must still be active,
    acceptable in the selected target view. If BM25 does not pass thresholds, the
    original suggestion is kept so its original failure reason remains visible.
    """
    resolver = SemanticBm25Resolver(
        hdf5_path,
        allow_blacklist_findings=allow_blacklist_findings,
        **kwargs,
    )

    def report_progress(**payload: object) -> None:
        if progress_callback is not None:
            progress_callback(payload)

    enhanced = []
    total = len(suggestions)
    attempted = 0
    replaced = 0
    ambiguous = 0
    report_progress(
        phase="start",
        processed=0,
        total=total,
        attempted=attempted,
        replaced=replaced,
        ambiguous=ambiguous,
        progress=0.0,
    )
    for index, suggestion in enumerate(suggestions, start=1):
        finding = suggestion.finding
        actionable_for_bm25 = (
            getattr(suggestion, "replacement_code", None) is None
            and not finding.ignored
            and (
                finding.list_type == "whitelist"
                or (allow_blacklist_findings and finding.list_type == "blacklist")
            )
        )
        if actionable_for_bm25:
            attempted += 1
            report_progress(
                phase="scoring",
                processed=index - 1,
                total=total,
                attempted=attempted,
                replaced=replaced,
                ambiguous=ambiguous,
                current_document=getattr(finding, "document", None),
                current_code=getattr(finding, "code", None),
                progress=((index - 1) / total if total else 1.0),
            )
            bm25_suggestion = resolver.suggest(finding)
            if bm25_suggestion.replacement_code is not None:
                replaced += 1
            elif bm25_suggestion.status == SanitizationStatus.AMBIGUOUS_REPLACEMENT:
                ambiguous += 1
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
                report_progress(
                    phase="processed",
                    processed=index,
                    total=total,
                    attempted=attempted,
                    replaced=replaced,
                    ambiguous=ambiguous,
                    progress=(index / total if total else 1.0),
                )
                continue
        enhanced.append(suggestion)
        report_progress(
            phase="processed",
            processed=index,
            total=total,
            attempted=attempted,
            replaced=replaced,
            ambiguous=ambiguous,
            progress=(index / total if total else 1.0),
        )
    report_progress(
        phase="complete",
        processed=total,
        total=total,
        attempted=attempted,
        replaced=replaced,
        ambiguous=ambiguous,
        progress=1.0,
    )
    return enhanced
