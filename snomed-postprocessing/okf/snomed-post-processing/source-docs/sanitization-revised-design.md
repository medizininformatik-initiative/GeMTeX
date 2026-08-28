---
type: Imported Documentation
title: "SNOMED sanitization design"
description: Lossless OKF import of /snomed-post-processing/source-former documentation folder/sanitization-revised-design.md.
resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/sanitization-revised-design.md
tags: [snomed-post-processing, imported-docs, legacy-docs]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: original-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/sanitization-revised-design.md
    title: "Original /snomed-post-processing/source-former documentation folder/sanitization-revised-design.md"
    author: team:project-maintainers
---

# SNOMED sanitization design

## Goal

Generate and apply reviewed sanitization decisions only for SNOMED CT annotations that were already reported as faulty findings. The workflow stays conservative: suggestions are evidence for human review, not automatic correction.

```text
policy/release check or loaded CriticalFindings
        |
suggestion generation
        |
human review decisions
        |
apply to copied INCEpTION ZIP
```

The original project ZIP is never modified in place.

## Inputs and outputs

Input:

- sanitization-ready SNOMED HDF5
- `CriticalFindings` JSON
- optional processed SNOGIT cache for BM25 evidence

Output:

- Markdown/JSON suggestion reports
- reviewed decisions JSON
- copied sanitized project ZIP

Sanitized ZIP export excludes `.ser` files. Reviewed decisions can replace SCTIDs or delete matching CAS annotations.

## Target-view validity

All replacement sources use the same selected target-view gates from `hdf5_handling/policy.py`.

| Target view | Candidate rule |
|---|---|
| policy | active AND whitelisted AND not blacklisted |
| release | active in selected release, plus optional embedded/custom blacklist exclusions |

Replacement candidates must also not be the SNOMED CT root or the unchanged source concept.

Policy mode remains authoritative for the current GeMTeX policy workflow. Release mode is intended for normalization to active release concepts without a whitelist requirement.

## Suggestion pipeline

For each finding, the resolver tries these sources in order:

1. **Historical association replacement**
   - Uses RF2 historical association refsets such as `SAME_AS`, `REPLACED_BY`, `POSSIBLY_EQUIVALENT_TO`, etc.
   - Only acceptable target-view candidates are retained.

2. **Active ancestor fallback** *(optional)*
   - Uses compact HDF5 ancestor arrays.
   - Can be limited by absolute and relative distance.

3. **Historical/inactive `is-a` ancestor fallback** *(optional)*
   - Uses stored inactive `is-a` edges under `/historical_is_a`.
   - Tries the inactive edge's active parent or an acceptable active ancestor above it.

4. **Semantic BM25 fallback** *(optional)*
   - Ranks SNOMED FSNs lexically.
   - May also use a processed SNOGIT cache as additional evidence.
   - Candidates still must satisfy the selected target-view gates.

5. **No replacement**
   - If no safe candidate is found, the finding remains for manual review/delete.

## Blacklist findings

Blacklist findings are conservative by default:

```text
blacklist finding + no explicit blacklist suggestion option
        -> blacklisted_no_auto_sanitization
```

Historical associations are mainly useful for inactive/outdated non-whitelisted findings. A blacklisted concept is often active but policy-forbidden, so automatic replacement can hide an intentional exclusion.

If blacklist suggestions are explicitly enabled, semantic BM25 may provide review candidates, but it still cannot bypass target-view gates.

## Semantic BM25 and SNOGIT guardrails

BM25 and SNOGIT are suggestion-only evidence:

- no raw SNOGIT ZIP parsing during `suggest-sanitization`
- processed SNOGIT caches are built separately
- selected HDF5 candidate gates remain authoritative
- ambiguous candidate sets are reported rather than auto-selected
- thresholds and max-candidate limits bound noisy fallback results

## Reviewed decisions and apply step

Reviewed decisions JSON is the bridge between suggestions and write-back. Supported actions include:

| Action | Effect |
|---|---|
| replace | replace matching annotation SCTID with reviewed target SCTID |
| delete | remove matching annotation |
| skip/no apply | leave annotation unchanged |

Write-back creates a separate sanitized ZIP. Matching is based on document/annotator/type/span/source-code metadata from the reviewed decision.

## Important status values

| Status | Meaning |
|---|---|
| `historical_replacement` | One acceptable historical association target found. |
| `ancestor_replacement` | One acceptable ancestor fallback target found. |
| `semantic_bm25_replacement` | One acceptable semantic BM25 candidate selected. |
| `ambiguous_*` | Multiple acceptable candidates require review. |
| `blacklisted_no_auto_sanitization` | Blacklist finding; automatic replacement disabled. |
| `no_policy_acceptable_candidate` | Candidates existed but failed selected target-view gates. |
| `no_replacement_found` | No candidate source produced an acceptable target. |

## CLI shape

Policy-mode suggestions:

```bash
uv run suggest-sanitization \
  --lists-path concepts.hdf5 \
  --critical-findings critical_findings.json \
  --output sanitization_suggestions.md
```

Release-mode suggestions:

```bash
uv run suggest-sanitization \
  --lists-path concepts.hdf5 \
  --critical-findings critical_findings.json \
  --output sanitization_suggestions.md \
  --target-view release
```

Optional release blacklist controls:

```bash
--enforce-embedded-blacklist
--custom-blacklist custom_blacklist.txt
```

Optional fallbacks:

```bash
--activate-historical-ancestor-fallback
--semantic-bm25-fallback
--blacklist-suggestions
--use-snogit-cache processed_snogit_cache.hdf5
```

## Related docs

- Release-view semantics and blacklist modes: `/snomed-post-processing/source-former documentation folder/release-view-normalization-and-blacklist-metadata.md`
- SNOGIT/BM25 details: `/snomed-post-processing/source-former documentation folder/snogit-bm25-candidates-design.md`
- RF2/HDF5 ingestion: `/snomed-post-processing/source-former documentation folder/rf2-to-hdf5-ingestion-design.md`
- User guide: `README.md`
