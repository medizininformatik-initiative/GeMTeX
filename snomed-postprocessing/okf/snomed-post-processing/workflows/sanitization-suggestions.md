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

Release mode (**Active release** in the sidebar) deliberately has no inclusion-list requirement. Embedded exclusion-list enforcement stays optional; custom exclusions apply only when selected. The SNOMED root concept `138875005` is rejected as a generic replacement candidate.

# Selectable versus diagnostic candidates

Both structured and BM25 suggestions separate `candidates` (selectable) from `context_candidates` (diagnostic only). `candidate_count` counts selectable candidates. Rejected historical targets, ancestors rejected by distance limits, and BM25 hits below thresholds are context, not replacement choices. Overview/report displays explicitly label diagnostics as not selectable.

JSON serialization preserves this separation. BM25 fallback preserves diagnostic historical/ancestor context when it supplies a replacement. Regenerate suggestions after changing target settings; review and export use the generated candidates rather than adding another HDF5 validation layer. There is no legacy-file normalization or status-based selection allowlist.

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

# GUI suggestion defaults

In a new GUI session:

- Historical ancestor fallback and semantic BM25 fallback are enabled.
- BM25 also considers exclusion-list findings. This does not relax target-candidate validity gates.
- **Advanced suggestion settings** opens by default so SNOGIT cache selection is visible.
- **Use SNOGIT/interface terms for BM25 candidates** is selected by default. A compatible processed cache must be selected or created before generating suggestions with SNOGIT enabled. An explicit opt-out persists across reruns; CLI/API defaults are unchanged.
- All supported historical association types except `MOVED_FROM` and `REFERS_TO` are selected.
- Minimum lexical overlap ratio is `0.0`; minimum BM25 score remains `1.5`.
- Association meanings appear inline in the selection options, not in a separate explanation section.

Explicit settings, including an empty association-type selection, are preserved across reruns. An empty selection disables historical-association candidates; enabled ancestor/BM25 fallbacks can still produce suggestions. These are suggestion defaults, not automatic review approval.

CLI/API defaults remain conservative: association types `SAME_AS` and `REPLACED_BY`; ancestor and BM25 fallbacks are opt-in.

The GUI sidebar starts with no overlap-ignore layer selected. Users may explicitly add `webanno.custom.No_Human` if desired.

# Conditional review selection

**Apply Conditions** in the review GUI implements historical-association selection and an opt-in BM25 gap condition, combined using OR. Both are restricted to source findings from the inclusion-list check (`finding.list_type == "whitelist"`). Exclusion-list findings (`list_type == "blacklist"`) remain manual regardless of score gaps or unique historical targets. An annotation with an exclusion-list finding must not be automatically approved through a second inclusion-list finding either. Open exclusion-list findings prevent automatic document-review completion.

This is a source-finding restriction, not a new inclusion-list requirement on source or target concepts. Existing target-view gates, optional Active-release exclusions, and separately configured explicit concept rules are unchanged. BM25 suggestions for exclusion-list findings may still be generated for manual inspection. Lexical similarity is not clinical replacement evidence; comparative reliability has not been measured here. The historical condition requires exactly one distinct target among generated selectable candidates matching the selected association types; diagnostics are never promoted. Ancestor suggestions and duplicate identities remain manual. BM25 selection defaults off. When enabled, at least three distinct codes with valid comparable scores are required. Using all saved distinct ranked candidates, `D = first_gap / (first_gap + largest_later_gap)` and `M = first_gap / top_score` must pass configurable thresholds (initially `2/3` and `0.20`). Tied first place, invalid scores, mixed/unknown channels or index members, and unknown SNOGIT members remain manual. Saved manual choices and explicit rules are protected. Conditions set review decisions/provenance only; undo restores the last changed run without overwriting later manual saves. See [review/write-back](/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md) and `reviewer_followup_plan.md`, section 7. The assessment table and decisions provenance expose the measured gaps, source/member and configured thresholds. Empirical calibration remains outstanding; enabling the heuristic is an explicit review-policy choice, not clinical validation.

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

In the CLI, ancestor fallback is opt-in (the GUI enables it by default):

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
