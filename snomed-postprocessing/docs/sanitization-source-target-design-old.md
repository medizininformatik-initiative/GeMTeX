# Archived design note: source-to-target sanitization

Status: **superseded** by `docs/sanitization-revised-design.md`.

This document preserves the main lessons from the earlier source-to-target sanitization proposal. The current implementation is finding-based: first produce structured `CriticalFinding` records, then generate suggestions only for those findings, then apply reviewed decisions to a copied project ZIP.

## Why this design was superseded

The original idea was to compare annotations against an explicit source HDF5 and target HDF5, then map source concepts to target concepts. That made sense for version-to-version migration, but it was too broad for the current policy workflow:

- The authoritative input is the current whitelist/blacklist policy check.
- Sanitization should only act on findings already reported as faulty.
- Blacklisted annotations require conservative handling and human review.
- Replacement candidates must pass the selected target-view validity gates.

## Lessons kept in the current design

### Keep `/concepts` as the shared concept universe

The compact HDF5 `/concepts` table remains useful for:

- code-to-index lookup
- FSN lookup
- active-state checks
- semantic tags
- ancestor arrays
- historical associations
- BM25 candidate corpora

Policy views should reference concept indices instead of duplicating large concept strings when possible:

```text
/policy_views/whitelist/0/concept_index
/policy_views/blacklist/0/concept_index
```

Legacy `/whitelist` and `/blacklist` groups can still be written for compatibility when requested.

### Ancestor fallback is useful but must be conservative

Ancestor fallback can propose a broader active ancestor when historical associations do not yield an acceptable target. The current implementation keeps this opt-in and bounded by distance limits.

Candidate validity is no longer hard-coded to whitelist-only semantics; it uses the selected target view:

```text
policy  -> active AND whitelisted AND not blacklisted
release -> active, plus optional embedded/custom blacklist exclusions
```

### BM25 is review assistance, not authority

Lexical similarity can help find candidates when historical/ancestor methods fail, but it must not bypass target-view gates. This applies to both SNOMED FSN BM25 and processed SNOGIT-cache evidence.

### Blacklist findings remain sensitive

Blacklisted annotations often represent intentional policy exclusions, not merely inactive/outdated concepts. Automatic replacement is disabled by default for blacklist findings. If BM25 suggestions are enabled for blacklist findings, they are review suggestions only and still require acceptable replacement candidates.

## Current references

Use these documents for the maintained design:

- `docs/sanitization-revised-design.md`
- `docs/release-view-normalization-and-blacklist-metadata.md`
- `docs/snogit-bm25-candidates-design.md`
- `README_alt.md`
