---
type: Runbook
title: Follow-ups and validation checklist
description: Open testing, smoke-test, performance, and deployment follow-up work for SNOMED Post Processing.
resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/release-view-follow-ups-and-docs-review.md
tags: [follow-up, testing, validation, gui, deployment]
status: draft
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: followups-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/release-view-follow-ups-and-docs-review.md
    title: Release-view follow-ups and documentation review
  - id: test-tree
    resource: /test
    title: Test suite
---

# Open follow-up work

## End-to-end option tests

Add CLI/pipeline tests for release-view behavior:

| Case | Expected release-view behavior |
|---|---|
| no blacklist flags | active concepts are allowed even if embedded-blacklisted |
| `--enforce-embedded-blacklist` | embedded-blacklisted concepts are excluded |
| `--custom-blacklist PATH` | custom-blacklisted concepts are excluded |
| both blacklist options | embedded and custom blacklist exclusions are both applied |

Include BM25/SNOGIT fallback in at least one release-view test if feasible.

## Manual GUI smoke test

Run Streamlit and verify suggestion generation for:

- policy view;
- active release view with no blacklist;
- active release view with embedded blacklist;
- active release view with custom blacklist;
- active release view with embedded + custom blacklist;
- release view with semantic BM25 fallback;
- release view with a processed SNOGIT cache.

Check that suggestion JSON metadata records target view and blacklist settings.

## Manual large-dataset performance test

Test realistic data sizes for:

- custom blacklist descendant resolution from HDF5 ancestor arrays;
- semantic BM25 fallback over main HDF5 FSNs;
- processed SNOGIT cache lookup;
- repeated annotation-text caching.

Track runtime and memory for policy mode and release mode.

## INCEpTION deployment validation

After real `apply-decisions-to-inception --apply`, inspect the target INCEpTION project:

- flattened documents imported;
- Concept annotations present;
- ManualReview markers present where expected;
- sentence-based editor loads all documents;
- remote-upload compatibility issue count is zero.

## Optional SNOGIT false-positive mitigation

If real data shows noisy suggestions for short/generic annotations, consider:

- higher lexical-overlap threshold for one-token queries;
- minimum token count before SNOGIT fallback;
- semantic-tag compatibility checks;
- stricter score margin for ambiguous candidates.

# Current validation snapshot

As of the prior implementation work, the full test run was:

```text
uv run pytest test -q
105 passed
```

# Documentation migration status

Every file formerly under the former documentation folder has been imported into this OKF bundle under `/snomed-post-processing/source-former documentation folder/`, and its content has also been consolidated into curated concept pages. Do not delete the former documentation folder automatically; deletion should be a separate human-approved cleanup step.
