---
type: Runbook
title: Current validation backlog
description: Open testing, smoke-test, performance, and deployment validation work for SNOMED Post Processing.
tags: [follow-up, testing, validation, gui, deployment]
status: draft
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: test-tree
    resource: /test
    title: Test suite
  - id: cli-doc
    resource: /snomed-post-processing/interfaces/cli.md
    title: CLI and environment validation notes
---

# Current validation backlog

This page tracks validation that remains to be performed. Completed implementation history and deferred design enhancements are documented elsewhere; see [Future work](future-work.md) for the latter.

## Baseline status

The last recorded full-suite validation reported **280 passed, 3 existing GUI-default failures, and 2 warnings**. The three failures concern defaults for BM25 and TLS settings and were reproduced under both retained Python 3.9 and Python 3.11 environments. They were not suppressed or marked as expected failures.

The following baseline checks were recorded as passing:

- Python 3.11 dependency and lock consistency;
- core/native imports and CLI help entry points;
- shared Streamlit/NiceGUI launcher dispatch;
- focused NiceGUI JSON import, review, and connection regression checks.

A fresh full test run and live-service validation are still separate tasks.

## Open validation work

### Resolve or explicitly retain the three GUI-default failures

Determine whether BM25 and TLS defaults should be unchecked, update the implementation/tests consistently, and rerun the full suite. Do not mark the failures as expected without a deliberate product decision.

### End-to-end release-view tests

Add or run CLI/pipeline tests covering:

| Case | Expected release-view behavior |
|---|---|
| no blacklist flags | active concepts are allowed even if embedded-blacklisted |
| `--enforce-embedded-blacklist` | embedded-blacklisted concepts are excluded |
| `--custom-blacklist PATH` | custom-blacklisted concepts are excluded |
| both blacklist options | embedded and custom blacklist exclusions are both applied |

Include BM25/SNOGIT fallback in at least one release-view test if feasible.

### Manual GUI smoke test

Run Streamlit and verify suggestion generation for:

- policy view;
- active release view with no blacklist;
- active release view with embedded blacklist;
- active release view with custom blacklist;
- active release view with embedded and custom blacklist;
- release view with semantic BM25 fallback;
- release view with a processed SNOGIT cache.

Check that suggestion JSON metadata records the target view and blacklist settings.

### Large-dataset performance test

Measure runtime and memory for:

- custom-blacklist descendant resolution from HDF5 ancestor arrays;
- semantic BM25 fallback over main HDF5 FSNs;
- processed SNOGIT cache lookup;
- repeated annotation-text caching;
- policy and release mode at realistic data sizes.

### INCEpTION deployment validation

After a real `apply-decisions-to-inception --apply`, inspect the target project and verify:

- flattened documents are imported;
- Concept annotations and ManualReview markers are present as expected;
- the sentence-based editor loads all documents;
- the remote-upload compatibility issue count is zero.

This requires an approved live INCEpTION environment.

### Optional SNOGIT false-positive mitigation

If real data shows noisy suggestions for short or generic annotations, evaluate:

- a higher lexical-overlap threshold for one-token queries;
- a minimum token count before SNOGIT fallback;
- semantic-tag compatibility checks;
- a stricter score margin for ambiguous candidates.

This is conditional on observed false positives, not a required implementation task.
