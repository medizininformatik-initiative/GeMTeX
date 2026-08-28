---
type: Imported Documentation
title: "Release-view follow-ups and documentation review"
description: Lossless OKF import of /snomed-post-processing/source-former documentation folder/release-view-follow-ups-and-docs-review.md.
resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/release-view-follow-ups-and-docs-review.md
tags: [snomed-post-processing, imported-docs, legacy-docs]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: original-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/release-view-follow-ups-and-docs-review.md
    title: "Original /snomed-post-processing/source-former documentation folder/release-view-follow-ups-and-docs-review.md"
    author: team:project-maintainers
---

# Release-view follow-ups and documentation review

## Open follow-up work

### 1. End-to-end option tests

Add tests that exercise the actual CLI/pipeline paths, not only helper-level validity:

| Case | Expected release-view behavior |
|---|---|
| no blacklist flags | active concepts are allowed even if embedded-blacklisted |
| `--enforce-embedded-blacklist` | embedded-blacklisted concepts are excluded |
| `--custom-blacklist PATH` | custom-blacklisted concepts are excluded |
| both blacklist options | embedded and custom blacklist exclusions are both applied |

Include BM25/SNOGIT fallback in at least one release-view test if feasible, to ensure the fallback path uses the same target-view gates.

### 2. Manual GUI smoke test

Run Streamlit and verify suggestion generation for:

- policy view
- active release view with no blacklist
- active release view with embedded blacklist
- active release view with custom blacklist
- active release view with embedded + custom blacklist
- release view with semantic BM25 fallback
- release view with a processed SNOGIT cache

Check that generated suggestion JSON metadata records the selected target view and blacklist settings.

### 3. Manual large-dataset performance test

Test on realistic data sizes:

- custom blacklist descendant resolution from HDF5 ancestor arrays
- semantic BM25 fallback over the main HDF5 FSNs
- processed SNOGIT cache lookup
- repeated annotation-text caching

Track runtime and memory for policy mode and release mode.

### 4. Optional SNOGIT false-positive mitigation

If real data shows noisy suggestions for short/generic annotations, consider stricter safeguards such as:

- higher lexical-overlap threshold for one-token queries
- minimum token count before SNOGIT fallback
- semantic-tag compatibility checks
- stricter score margin for ambiguous candidates

## Documentation cleanup status

Completed cleanup:

| File | Status |
|---|---|
| `README.md` | Main user guide; updated with release-view, blacklist, BM25, and processed SNOGIT-cache usage. |
| `/snomed-post-processing/source-former documentation folder/release-view-normalization-and-blacklist-metadata.md` | Focused release-view and blacklist semantics note. |
| `/snomed-post-processing/source-former documentation folder/rf2-to-hdf5-ingestion-design.md` | Shortened to current ingestion behavior, HDF5 layout, CLI examples, and key decisions. |
| `/snomed-post-processing/source-former documentation folder/sanitization-revised-design.md` | Shortened to current sanitization workflow, target-view gates, suggestion sources, and write-back behavior. |
| `/snomed-post-processing/source-former documentation folder/snogit-bm25-candidates-design.md` | Shortened to current processed-cache workflow, member selection, runtime usage, layout, and guardrails. |
| `/snomed-post-processing/source-former documentation folder/snomed-postprocessing-working.md` | Reduced to a maintainer entrypoint/module map. |
| `/snomed-post-processing/source-former documentation folder/rf2-release-zip-structure.md` | Reduced to project-relevant RF2 ZIP notes with OKF references. |
| `/snomed-post-processing/source-former documentation folder/sanitization-source-target-design-old.md` | Replaced with an archived superseded-design summary and retained lessons. |

Keep historical rationale in Git history; avoid re-expanding docs unless behavior changes materially.
