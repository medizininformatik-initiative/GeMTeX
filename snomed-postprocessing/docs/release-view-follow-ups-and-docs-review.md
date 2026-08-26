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
| `README_alt.md` | Main user guide; updated with release-view, blacklist, BM25, and processed SNOGIT-cache usage. |
| `docs/release-view-normalization-and-blacklist-metadata.md` | Focused release-view and blacklist semantics note. |
| `docs/rf2-to-hdf5-ingestion-design.md` | Shortened to current ingestion behavior, HDF5 layout, CLI examples, and key decisions. |
| `docs/sanitization-revised-design.md` | Shortened to current sanitization workflow, target-view gates, suggestion sources, and write-back behavior. |
| `docs/snogit-bm25-candidates-design.md` | Shortened to current processed-cache workflow, member selection, runtime usage, layout, and guardrails. |
| `docs/snomed-postprocessing-working.md` | Reduced to a maintainer entrypoint/module map. |
| `docs/rf2-release-zip-structure.md` | Reduced to project-relevant RF2 ZIP notes with OKF references. |
| `docs/sanitization-source-target-design-old.md` | Replaced with an archived superseded-design summary and retained lessons. |

Keep historical rationale in Git history; avoid re-expanding docs unless behavior changes materially.
