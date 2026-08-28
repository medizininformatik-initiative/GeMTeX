---
type: Workflow
title: Sanitization suggestion generation
description: Conservative replacement suggestion pipeline using historical associations, ancestor fallback, BM25, and target-view gates.
resource: /src/snomed_post_processing/sanitization/resolver.py
tags: [workflow, sanitization, suggestions, historical-associations, bm25]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: sanitizer-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/sanitization-revised-design.md
    title: SNOMED sanitization design
  - id: release-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/release-view-normalization-and-blacklist-metadata.md
    title: Release-view normalization and blacklist metadata
  - id: resolver
    resource: /src/snomed_post_processing/sanitization/resolver.py
    title: Sanitization resolver implementation
---

# Goal

Generate replacement suggestions only for SNOMED CT annotations already reported as faulty `CriticalFinding` records. Suggestions are evidence for human review and do not automatically modify the original project.

# Target-view validity

All replacement sources share the same target-view gates from `/src/snomed_post_processing/hdf5_handling/policy.py`.

| Target view | Candidate rule |
|---|---|
| policy | active AND whitelisted AND not blacklisted |
| release | active in selected release, plus optional embedded/custom blacklist exclusions |

Release mode deliberately has no whitelist requirement. The SNOMED root concept `138875005` is rejected as a replacement candidate.

# Release-view blacklist modes

| CLI flags / GUI choices | Effective release-view rule |
|---|---|
| none / no blacklist | active concept |
| `--enforce-embedded-blacklist` | active AND not embedded-blacklisted |
| `--custom-blacklist PATH` | active AND not custom-blacklisted |
| both | active AND not embedded-blacklisted AND not custom-blacklisted |

Custom blacklist rules use the same input format as RF2 blacklist ingestion:

```text
numeric SCTID line -> exclude that concept and descendants
non-numeric line   -> exclude concepts by FSN semantic tag
```

Runtime SCTID descendant blacklist rules require compact ancestor arrays in the HDF5.

# Resolver order

For each finding, `SanitizationResolver.suggest` proceeds as follows:

1. Ignore `ignored=True` findings.
2. Refuse automatic sanitization for blacklist findings by default.
3. Require whitelist findings with a source code present in `/concepts`.
4. Try active allowed RF2 historical association targets.
5. If enabled, try active ancestor fallback.
6. If enabled, try historical/inactive `is-a` ancestor fallback.
7. Optionally, after resolver output, apply semantic BM25 fallback.
8. Otherwise report no replacement or no target-view-acceptable candidate.

# Historical associations

Historical association replacement uses RF2 historical association refsets such as:

```text
SAME_AS
REPLACED_BY
POSSIBLY_EQUIVALENT_TO
POSSIBLY_REPLACED_BY
WAS_A
MOVED_TO
REFERS_TO
SIMILAR_TO
```

Only active association rows with source and target concepts known in HDF5 can produce candidates. Allowed association types are CLI-configurable with repeated `--association-type`.

If exactly one acceptable target code remains, status is `historical_association_replacement`. If multiple acceptable target codes remain, status is `ambiguous_replacement`.

# Ancestor fallback

Ancestor fallback is opt-in:

```bash
--activate-historical-ancestor-fallback
```

It first uses active compact ancestor arrays under `/concepts`, then historical/inactive `is-a` edges under `/historical_is_a`.

Both absolute and relative limits are supported:

```text
ancestor_max_distance default: 3
ancestor_max_relative_distance default: 0.35
```

A candidate must satisfy the absolute limit and, when depth arrays exist, `distance / source_depth_to_root <= ancestor_max_relative_distance`. CLI negative values disable a limit.

Historical/inactive `is-a` traversal can propose either the inactive edge parent itself or an acceptable active ancestor above that parent. Nearest distance wins. Multiple equally near acceptable ancestor codes produce `ambiguous_ancestor`.

# BM25 and SNOGIT fallback

Semantic BM25 is optional and suggestion-only. It ranks lexical similarity between annotation text/source FSN and candidate terms from:

- SNOMED FSNs in the main HDF5;
- optionally, a processed SNOGIT cache.

BM25/SNOGIT candidates cannot bypass target-view gates and also reject unchanged source concepts and the SNOMED root.

# Important statuses

| Status family | Meaning |
|---|---|
| `historical_*` | Replacement found through RF2 historical association. |
| `nearest_*_ancestor` / `ancestor_*` | Replacement found through active or historical ancestor fallback. |
| `semantic_bm25_*` | Replacement found through lexical BM25 fallback. |
| `ambiguous_*` | Human choice required. |
| `blacklisted_no_auto_sanitization` | Blacklist finding not auto-sanitized. |
| `no_policy_acceptable_candidate` | Candidates existed but failed selected gates or distance limits. |
| `no_replacement` / no replacement found | No safe candidate source produced a replacement. |

# Related concepts

- [Critical-finding logging](/snomed-post-processing/workflows/critical-finding-logging.md)
- [Processed SNOGIT cache and BM25](/snomed-post-processing/workflows/snogit-bm25.md)
- [Reviewed decisions and write-back](/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md)
