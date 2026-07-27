# Legacy grounding baselines

This directory contains older, self-contained baseline scripts for grounding German clinical entity spans to SNOMED CT concepts. They are not part of the current INCEpTION/Streamlit post-processing workflow, but they document and implement earlier candidate-generation approaches.

## Shared input/output idea

Both scripts expect HuggingFace-style JSONL sentence files with token-level BIO annotations, e.g. records containing:

- `fname`
- `sentence_id`
- `tokens`
- `tags`
- `token_offsets`
- `sentence_offset`
- `text`

They extract gold entity spans from the BIO tags, reconstruct span text from offsets where possible, and try to map each span to candidate SNOMED CT concepts.

Both scripts load terminology resources from configurable paths:

- German SNOMED RF2 Description file
- optional SNOMED RF2 Concept file for concept active/inactive status
- SNOGIT German interface terms, resolved back to SNOMED concept IDs

Both produce:

- JSONL output with one record per entity span
- JSON statistics with aggregate and per-label match counts/rates

## `lexical_matching_baseline.py`

A lexical dictionary-style grounding baseline.

Workflow:

1. Read BIO-tagged JSONL sentence files.
2. Extract entity spans.
3. Load SNOMED German descriptions, optional SNOMED concepts, and SNOGIT terms.
4. Normalize span and terminology text deterministically:
   - Unicode NFKC
   - casefolding
   - punctuation/symbols to spaces
   - whitespace collapse/strip
5. Search for exact normalized string matches in SNOMED and SNOGIT.
6. If no exact match is found, optionally search approximate matches using bounded Levenshtein distance via `rapidfuzz`.
7. Group matched descriptions/terms by SNOMED concept ID.
8. Emit concept-level candidate metadata, including matched terms, FSNs, description types, and active status where available.

In short: exact/fuzzy lexical lookup baseline for entity-to-SNOMED grounding.

Run pattern:

```bash
python legacy/lexical_matching_baseline.py --config path/to/config.yaml
```

## `bm25_matching.py`

A BM25 information-retrieval-style grounding baseline.

Workflow:

1. Read BIO-tagged JSONL sentence files.
2. Extract entity spans.
3. Load SNOMED German descriptions, optional SNOMED concepts, and SNOGIT terms.
4. Normalize and tokenize terminology entries.
5. Build two BM25 indices:
   - one over SNOMED German descriptions
   - one over SNOGIT German terms
6. For each entity span, normalize/tokenize the query span.
7. Retrieve top-k lexical candidates from both BM25 indices.
8. Group hits by SNOMED concept ID.
9. Emit ranked concept candidates with BM25 scores/ranks and terminology metadata.

The script contains a small deterministic BM25 implementation and does not require `rank_bm25`.

In short: BM25 candidate-retrieval baseline for entity-to-SNOMED grounding.

Run pattern:

```bash
python legacy/bm25_matching.py --config path/to/config.yaml
```

## Conceptual difference

Both scripts perform the same broad task:

```text
BIO-tagged entity spans
        ↓
normalize span text
        ↓
search SNOMED German + SNOGIT
        ↓
produce candidate SNOMED concepts
        ↓
write JSONL + stats
```

The difference is the matching strategy:

- `lexical_matching_baseline.py` uses exact normalized matching plus optional Levenshtein fallback.
- `bm25_matching.py` uses token-based ranked retrieval and can return partial lexical matches.

Use the lexical baseline when strict dictionary-style matching is desired. Use the BM25 baseline when broader candidate generation is desired, especially for spans that may only partially overlap terminology descriptions.
