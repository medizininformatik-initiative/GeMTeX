"""Semantic BM25 replacement suggestions for SNOMED sanitization.

This module implements a conservative, dependency-free BM25 scorer over SNOMED
concept labels from the compact HDF5 layout. It is intended as a suggestion-only
fallback when structured historical associations do not yield a replacement.
"""

from __future__ import annotations

import dataclasses
import math
import pathlib
import re
from collections import Counter, defaultdict
from typing import Optional, Sequence, Union

import h5py
import numpy as np

from ..uima_processing import CriticalFinding
from . import SanitizationStatus

_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
_SEMANTIC_TAG_RE = re.compile(r"\(([^()]*)\)\s*$")


@dataclasses.dataclass(frozen=True)
class SemanticBm25Candidate:
    """A single policy-acceptable BM25 replacement candidate."""

    code: str
    fsn: str
    score: float
    lexical_score: float
    semantic_tag: Optional[str]
    active: bool
    in_whitelist: bool
    in_blacklist: bool

    @property
    def policy_acceptable(self) -> bool:
        return self.active and self.in_whitelist and not self.in_blacklist


@dataclasses.dataclass(frozen=True)
class SemanticBm25Suggestion:
    """Suggestion produced by :class:`SemanticBm25Resolver`."""

    finding: CriticalFinding
    status: SanitizationStatus
    replacement_code: Optional[str] = None
    replacement_fsn: Optional[str] = None
    association_type: Optional[str] = None
    reason: str = ""
    score: float = 0.0
    candidate_count: int = 0
    candidates: tuple[SemanticBm25Candidate, ...] = ()


@dataclasses.dataclass(frozen=True)
class Bm25Hit:
    """A scored document hit from :class:`BM25Index`."""

    document_id: int
    score: float
    matched_query_tokens: tuple[str, ...]


class BM25Index:
    """Small dependency-free BM25 index with token-to-document postings.

    Documents are token sequences. The inverted index lets searches score only
    documents that contain at least one query token instead of scanning every
    indexed document for every query.
    """

    def __init__(
        self,
        documents: Sequence[Sequence[str]],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ):
        self.documents = [tuple(document) for document in documents]
        self.k1 = float(k1)
        self.b = float(b)
        self.document_lengths = [len(document) for document in self.documents]
        self.document_count = len(self.documents)
        self.average_document_length = (
            sum(self.document_lengths) / self.document_count
            if self.document_count
            else 0.0
        )
        self.term_frequencies = [Counter(document) for document in self.documents]
        self.inverted: dict[str, list[tuple[int, int]]] = defaultdict(list)
        document_frequency: Counter[str] = Counter()
        for document_id, term_frequency in enumerate(self.term_frequencies):
            for token, frequency in term_frequency.items():
                self.inverted[token].append((document_id, frequency))
                document_frequency[token] += 1
        self.idf = {
            term: math.log(1.0 + (self.document_count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def search(self, query_tokens: Sequence[str]) -> list[Bm25Hit]:
        if not query_tokens or self.document_count == 0:
            return []

        scores: dict[int, float] = defaultdict(float)
        matched_tokens_by_document: dict[int, set[str]] = defaultdict(set)
        average_document_length = max(self.average_document_length, 1e-9)
        for token in dict.fromkeys(query_tokens):
            postings = self.inverted.get(token)
            if not postings:
                continue
            idf = self.idf.get(token, 0.0)
            for document_id, frequency in postings:
                document_length = self.document_lengths[document_id]
                if document_length == 0:
                    continue
                denominator = frequency + self.k1 * (
                    1.0 - self.b + self.b * document_length / average_document_length
                )
                scores[document_id] += idf * frequency * (self.k1 + 1.0) / denominator
                matched_tokens_by_document[document_id].add(token)

        hits = [
            Bm25Hit(
                document_id=document_id,
                score=score,
                matched_query_tokens=tuple(sorted(matched_tokens_by_document[document_id])),
            )
            for document_id, score in scores.items()
            if score > 0.0
        ]
        hits.sort(key=lambda hit: (-hit.score, hit.document_id))
        return hits


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

        query = _query_text(finding, self.fsn_by_code(finding.code))
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
            required = [
                "concepts/codes",
                "concepts/fsn",
                "concepts/active",
                "policy_views/whitelist/0/concept_index",
                "policy_views/blacklist/0/concept_index",
            ]
            missing = [path for path in required if path not in h5_file]
            if missing:
                raise ValueError(
                    "HDF5 file is not BM25-sanitization-ready; missing compact dataset(s): "
                    + ", ".join(missing)
                )
            self.codes = tuple(_decode_array(h5_file["concepts/codes"][:]))
            self.fsn = tuple(_decode_array(h5_file["concepts/fsn"][:]))
            self.code_to_index = {code: idx for idx, code in enumerate(self.codes)}
            self.active = np.asarray(h5_file["concepts/active"][:], dtype=bool)
            self.whitelist_indices = frozenset(
                int(idx) for idx in h5_file["policy_views/whitelist/0/concept_index"][:]
            )
            self.blacklist_indices = frozenset(
                int(idx) for idx in h5_file["policy_views/blacklist/0/concept_index"][:]
            )

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
            if bm25_suggestion.replacement_code is not None:
                enhanced.append(bm25_suggestion)
                continue
        enhanced.append(suggestion)
    return enhanced


def _query_text(finding: CriticalFinding, source_fsn: Optional[str] = None) -> str:
    return " ".join(
        part for part in (finding.covered_text, source_fsn or "") if part
    )


def _tokenize(text: Optional[str]) -> list[str]:
    if not text:
        return []
    return [token.lower() for token in _TOKEN_RE.findall(text) if len(token) > 1]


def _semantic_tag(fsn: Optional[str]) -> Optional[str]:
    if not fsn:
        return None
    match = _SEMANTIC_TAG_RE.search(fsn)
    return match.group(1).lower() if match else None


def _decode_array(values) -> list[str]:
    decoded = []
    for value in values:
        if isinstance(value, (bytes, bytearray)):
            decoded.append(value.decode("utf-8"))
        else:
            decoded.append(str(value))
    return decoded
