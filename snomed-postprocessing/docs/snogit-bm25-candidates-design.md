# Processed SNOGIT cache and BM25 sanitization candidates

## Purpose

Semantic BM25 is an optional fallback for sanitization suggestions when historical associations and ancestor fallback do not produce a clear replacement. It ranks lexical similarity between the annotation text and candidate terms.

SNOGIT can provide additional interface-term evidence, but it is never authoritative:

```text
SNOMED FSN BM25 + optional processed SNOGIT cache
        -> candidate evidence
        -> selected target-view gates
        -> review suggestion
```

Candidates must still satisfy the active policy/release validity rules from the selected HDF5.

## Terminology

Use the user-facing term **processed SNOGIT cache** for the reusable HDF5 built from a raw SNOGIT ZIP. The implementation module is still named `snogit_sidecar.py`.

`suggest-sanitization` consumes a processed cache only. It does not parse raw SNOGIT ZIPs and does not create a cache.

## Cache creation workflow

Build a cache once from the main SNOMED HDF5 and a raw SNOGIT ZIP:

```bash
uv run build-snogit-cache \
  --hdf5 concepts.hdf5 \
  --snogit-zip SNOGIT.zip \
  --output processed_snogit_cache.hdf5
```

Default member selection uses the newest general `SNOGIT_*.dat` member in the ZIP. Override with one or more explicit members:

```bash
uv run build-snogit-cache \
  --hdf5 concepts.hdf5 \
  --snogit-zip SNOGIT.zip \
  --output processed_snogit_cache.hdf5 \
  --snogit-member path/in/zip/SNOGIT_20240131.dat \
  --snogit-member path/in/zip/SNOGIT_ELGA_20240131.dat
```

Supported member classes are:

| Class | Default? |
|---|---:|
| general `SNOGIT_*.dat` | newest one selected by default |
| `SNOGIT_ELGA_*.dat` | explicit selection only |
| `SNOMED_latin_*.dat` | explicit selection only |

The GUI exposes the same behavior through a ZIP-member multiselect when creating a processed cache.

## Using a processed cache

Enable semantic BM25 fallback and pass the cache:

```bash
uv run suggest-sanitization \
  --lists-path concepts.hdf5 \
  --critical-findings critical_findings.json \
  --output sanitization_suggestions.md \
  --semantic-bm25-fallback \
  --use-snogit-cache processed_snogit_cache.hdf5
```

SNOGIT is optional. Without `--use-snogit-cache`, semantic BM25 still ranks SNOMED FSNs from the main HDF5.

## Candidate gates

BM25/SNOGIT candidates use the selected target view:

| Target view | Gate |
|---|---|
| policy | active AND whitelisted AND not blacklisted |
| release | active, plus optional embedded/custom blacklist exclusions |

All modes also reject:

- the unchanged source concept
- the SNOMED CT root

SNOGIT evidence must not bypass HDF5 validity gates.

## Cache compatibility

The processed cache stores a fingerprint of the main HDF5 so stale or mismatching caches can be rejected. Compatibility metadata includes:

```text
release date
policy/view date
RF2 view
concept count
policy candidate count
concept-code hash
policy-candidate hash
```

A cache should be rebuilt when the main HDF5 changes.

## HDF5 cache layout

The processed cache stores normalized term rows and an inverted BM25 index:

```text
/metadata/...
/terms/concept_index
/terms/term
/terms/source_member
/terms/length
/index/vocab
/index/postings_start
/index/postings_length
/index/postings_doc
/index/postings_tf
/index/idf
/index/avg_doc_len
```

This allows runtime retrieval without loading all SNOGIT terms into Python memory.

## Runtime safeguards

The SNOGIT searcher keeps the HDF5 cache open for resolver lifetime and uses NumPy-backed scoring. Guardrails bound worst-case queries:

```text
max_postings_per_token
max_candidate_rows
max_hits
```

Repeated normalized query texts are cached during one resolver run.

## Output evidence

Suggestion candidates can include optional SNOGIT evidence fields:

```text
source = snomed_fsn | snogit
matched_term
source_member
matched_query_tokens
```

These fields explain why a candidate was suggested; they do not change acceptance rules.

## Known follow-up

Short or generic one-token annotations may produce noisy lexical matches. If real-data testing confirms this, consider stricter thresholds or token-count-specific safeguards.
