"""Small dependency-free BM25 index."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Sequence

from .semantic_models import Bm25Hit


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
