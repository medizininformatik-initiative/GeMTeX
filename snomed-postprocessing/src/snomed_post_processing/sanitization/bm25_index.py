"""Small dependency-free BM25 index."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Sequence

import numpy as np

from .semantic_models import Bm25Hit


class BM25Index:
    """Small BM25 index with NumPy-backed token postings.

    Documents are token sequences. The inverted index lets searches score only
    documents that contain at least one query token instead of scanning every
    indexed document for every query. Query-time scoring is vectorized over each
    token's postings with NumPy arrays.
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
        self.document_lengths = np.asarray([len(document) for document in self.documents], dtype=np.float64)
        self.document_count = len(self.documents)
        self.average_document_length = (
            float(np.mean(self.document_lengths))
            if self.document_count
            else 0.0
        )

        postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        document_frequency: Counter[str] = Counter()
        self.term_frequencies = []
        for document_id, document in enumerate(self.documents):
            term_frequency = Counter(document)
            self.term_frequencies.append(term_frequency)
            for token, frequency in term_frequency.items():
                postings[token].append((document_id, int(frequency)))
                document_frequency[token] += 1

        self.inverted = dict(postings)
        self.idf = {
            term: math.log(1.0 + (self.document_count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }
        vocab = sorted(postings)
        self.vocab_pos = {token: idx for idx, token in enumerate(vocab)}
        self.postings_start = np.zeros(len(vocab), dtype=np.int64)
        self.postings_length = np.zeros(len(vocab), dtype=np.int64)
        self.idf_array = np.zeros(len(vocab), dtype=np.float64)

        document_ids: list[int] = []
        frequencies: list[int] = []
        cursor = 0
        for vocab_idx, token in enumerate(vocab):
            token_postings = postings[token]
            self.postings_start[vocab_idx] = cursor
            self.postings_length[vocab_idx] = len(token_postings)
            self.idf_array[vocab_idx] = self.idf[token]
            for document_id, frequency in token_postings:
                document_ids.append(document_id)
                frequencies.append(frequency)
            cursor += len(token_postings)

        self.posting_document_id = np.asarray(document_ids, dtype=np.int64)
        self.posting_frequency = np.asarray(frequencies, dtype=np.float64)

    def search(self, query_tokens: Sequence[str]) -> list[Bm25Hit]:
        if not query_tokens or self.document_count == 0:
            return []

        row_chunks: list[np.ndarray] = []
        contribution_chunks: list[np.ndarray] = []
        matched_tokens_by_document: dict[int, set[str]] = defaultdict(set)
        average_document_length = max(float(self.average_document_length), 1e-9)
        for token in dict.fromkeys(query_tokens):
            vocab_idx = self.vocab_pos.get(token)
            if vocab_idx is None:
                continue
            start = int(self.postings_start[vocab_idx])
            length = int(self.postings_length[vocab_idx])
            if length <= 0:
                continue
            end = start + length
            document_ids = self.posting_document_id[start:end]
            frequencies = self.posting_frequency[start:end]
            document_lengths = self.document_lengths[document_ids]
            non_empty = document_lengths > 0.0
            if not np.any(non_empty):
                continue
            document_ids = document_ids[non_empty]
            frequencies = frequencies[non_empty]
            document_lengths = document_lengths[non_empty]
            denominator = frequencies + self.k1 * (
                1.0 - self.b + self.b * document_lengths / average_document_length
            )
            contribution = self.idf_array[vocab_idx] * frequencies * (self.k1 + 1.0) / denominator
            row_chunks.append(document_ids)
            contribution_chunks.append(contribution)
            for document_id in document_ids:
                matched_tokens_by_document[int(document_id)].add(token)

        if not row_chunks:
            return []
        all_document_ids = np.concatenate(row_chunks)
        all_contributions = np.concatenate(contribution_chunks)
        unique_document_ids, inverse = np.unique(all_document_ids, return_inverse=True)
        scores = np.bincount(inverse, weights=all_contributions)
        positive = scores > 0.0
        if not np.any(positive):
            return []
        unique_document_ids = unique_document_ids[positive]
        scores = scores[positive]
        ordered_positions = sorted(
            range(len(scores)),
            key=lambda pos: (-float(scores[pos]), int(unique_document_ids[pos])),
        )
        return [
            Bm25Hit(
                document_id=int(unique_document_ids[pos]),
                score=float(scores[pos]),
                matched_query_tokens=tuple(sorted(matched_tokens_by_document[int(unique_document_ids[pos])])),
            )
            for pos in ordered_positions
        ]
