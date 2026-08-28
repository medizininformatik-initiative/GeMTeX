---
type: Data Format
title: HDF5 policy store layout
description: Compact HDF5 layout used for concepts, policy views, historical associations, ancestor arrays, and metadata.
resource: /src/snomed_post_processing/hdf5_handling/policy.py
tags: [data-format, hdf5, policy, snomed]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: ingestion-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/rf2-to-hdf5-ingestion-design.md
    title: RF2 release ZIP to HDF5 ingestion
  - id: release-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/release-view-normalization-and-blacklist-metadata.md
    title: Release-view normalization and blacklist metadata
  - id: policy-code
    resource: /src/snomed_post_processing/hdf5_handling/policy.py
    title: HDF5 policy helper implementation
---

# Role

The HDF5 file is the app's materialized SNOMED release and policy store. Runtime checks and sanitization suggestion logic should access it through `/src/snomed_post_processing/hdf5_handling/policy.py` rather than directly addressing datasets.

# Core concept table

```text
/concepts/codes
/concepts/fsn
/concepts/active
/concepts/semantic_tag_id
/concepts/semantic_tags
```

`/concepts` is the shared concept universe for code lookup, FSN display, active-state checks, semantic tag filtering, ancestor arrays, historical associations, and BM25 candidate corpora.

# Optional hierarchy arrays

```text
/concepts/ancestors_index
/concepts/ancestor_concept_index
/concepts/ancestor_distance
/concepts/min_depth_to_root
/concepts/max_depth_to_root
```

Ancestor arrays support runtime custom blacklist descendant resolution and optional ancestor fallback suggestions. Depth arrays support relative ancestor-distance limits.

# Policy views

```text
/policy_views/whitelist/0/concept_index
/policy_views/blacklist/0/concept_index
/policy_views/<whitelist|blacklist>/0/root_codes
/policy_views/<whitelist|blacklist>/0/filter_tags
```

Policy views store compact concept indices rather than duplicating large code/FSN strings. Optional legacy groups can be written for compatibility:

```text
/whitelist/0/codes
/whitelist/0/fsn
/blacklist/0/codes
/blacklist/0/fsn
```

# Historical associations

```text
/historical_associations/source_index
/historical_associations/target_index
/historical_associations/association_type_id
/historical_associations/association_types
/historical_associations/effective_time
/historical_associations/active
/historical_associations/refset_id
```

These datasets support direct historical replacement suggestions for inactive/outdated concepts.

# Historical/inactive is-a fallback edges

```text
/historical_is_a/source_index
/historical_is_a/parent_index
/historical_is_a/effective_time
```

These optional edges support historical ancestor fallback after active ancestor fallback fails.

# Blacklist rule metadata

HDF5 stores compact blacklist provenance/rule metadata, not expanded per-rule descendants:

```text
/metadata/blacklists/0/format_version
/metadata/blacklists/0/source_name
/metadata/blacklists/0/rules_raw
/metadata/blacklists/0/rules_kind
```

`rules_kind` values include:

```text
fsn_tag
concept_descendants
```

Resolved blacklist concepts live in `/policy_views/blacklist/0/concept_index`.

# Candidate validity API

`CandidateValiditySets` captures active state, whitelist indices, embedded blacklist indices, runtime blacklist indices, mode, and blacklist enforcement. `candidate_validity_from_sets` implements:

```text
policy  -> active AND whitelist AND not blacklist
release -> active AND not runtime blacklist AND optionally not embedded blacklist
```

# Related concepts

- [RF2/Snowstorm to HDF5](/snomed-post-processing/workflows/rf2-to-hdf5.md)
- [Sanitization suggestions](/snomed-post-processing/workflows/sanitization-suggestions.md)
