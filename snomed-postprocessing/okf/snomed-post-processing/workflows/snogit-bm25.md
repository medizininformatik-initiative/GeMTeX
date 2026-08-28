---
type: Workflow
title: Processed SNOGIT cache and BM25 fallback
description: Optional lexical fallback evidence for sanitization suggestions using SNOMED FSNs and processed SNOGIT terms.
resource: /src/snomed_post_processing/sanitization/snogit_sidecar.py
tags: [workflow, snogit, bm25, sanitization, hdf5]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: snogit-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/snogit-bm25-candidates-design.md
    title: Processed SNOGIT cache and BM25 sanitization candidates
  - id: bm25-code
    resource: /src/snomed_post_processing/sanitization/semantic_bm25.py
    title: Semantic BM25 resolver
  - id: snogit-code
    resource: /src/snomed_post_processing/sanitization/snogit_sidecar.py
    title: SNOGIT sidecar/cache implementation
---

# Purpose

Semantic BM25 is an optional fallback for sanitization suggestions when historical associations and ancestor fallback do not produce a clear replacement. It ranks lexical similarity between annotation text/source FSN and candidate terms.

SNOGIT provides optional interface-term evidence but is never authoritative:

```text
SNOMED FSN BM25 + optional processed SNOGIT cache
        -> candidate evidence
        -> selected target-view gates
        -> review suggestion
```

# Terminology

Use the user-facing term **processed SNOGIT cache** for the reusable HDF5 built from a raw SNOGIT ZIP. The implementation module is named `snogit_sidecar.py`.

`suggest-sanitization` consumes a processed cache only. It does not parse raw SNOGIT ZIPs and does not create a cache.

# Cache creation

```bash
uv run build-snogit-cache \
  --hdf5 concepts.hdf5 \
  --snogit-zip SNOGIT.zip \
  --output processed_snogit_cache.hdf5
```

Default member selection uses the newest general `SNOGIT_*.dat` member in the ZIP.

Override with explicit members:

```bash
uv run build-snogit-cache \
  --hdf5 concepts.hdf5 \
  --snogit-zip SNOGIT.zip \
  --output processed_snogit_cache.hdf5 \
  --snogit-member path/in/zip/SNOGIT_20240131.dat \
  --snogit-member path/in/zip/SNOGIT_ELGA_20240131.dat
```

Supported member classes:

| Class | Default? |
|---|---:|
| general `SNOGIT_*.dat` | newest selected by default |
| `SNOGIT_ELGA_*.dat` | explicit selection only |
| `SNOMED_latin_*.dat` | explicit selection only |

# Runtime use

```bash
uv run suggest-sanitization \
  --lists-path concepts.hdf5 \
  --critical-findings critical_findings.json \
  --output sanitization_suggestions.md \
  --semantic-bm25-fallback \
  --use-snogit-cache processed_snogit_cache.hdf5
```

Without `--use-snogit-cache`, semantic BM25 still ranks SNOMED FSNs from the main HDF5.

# Candidate gates and safeguards

BM25/SNOGIT candidates use the selected target view:

| Target view | Gate |
|---|---|
| policy | active AND whitelisted AND not blacklisted |
| release | active, plus optional embedded/custom blacklist exclusions |

All modes reject the unchanged source concept and SNOMED CT root. SNOGIT evidence must not bypass HDF5 validity gates.

Runtime safeguards include:

```text
max_postings_per_token
max_candidate_rows
max_hits
bm25_min_score
bm25_min_lexical_score
bm25_max_candidates
```

Repeated normalized query texts are cached during one resolver run.

# Processed cache compatibility

The cache stores a fingerprint of the main HDF5 so stale or mismatching caches can be rejected. Compatibility metadata includes release date, policy/view date, RF2 view, concept count, policy candidate count, concept-code hash, and policy-candidate hash.

# HDF5 cache layout

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

# Output evidence

Suggestion candidates may include:

```text
source = snomed_fsn | snogit
matched_term
source_member
matched_query_tokens
```

These fields explain why a candidate was suggested; they do not change acceptance rules.

# Known follow-up

Short/generic one-token annotations may produce noisy matches. If real data confirms this, consider stricter lexical overlap, minimum token counts, semantic-tag compatibility, or stronger score margins.
