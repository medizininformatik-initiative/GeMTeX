---
type: Imported Documentation
title: "RF2 release ZIP to HDF5 ingestion"
description: Lossless OKF import of /snomed-post-processing/source-former documentation folder/rf2-to-hdf5-ingestion-design.md.
resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/rf2-to-hdf5-ingestion-design.md
tags: [snomed-post-processing, imported-docs, legacy-docs]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: original-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/rf2-to-hdf5-ingestion-design.md
    title: "Original /snomed-post-processing/source-former documentation folder/rf2-to-hdf5-ingestion-design.md"
    author: team:project-maintainers
---

# RF2 release ZIP to HDF5 ingestion

## Goal

Create a self-contained SNOMED HDF5 from an RF2 release ZIP for fast policy checking and sanitization. The HDF5 should contain concept metadata, compact policy views, and optional hierarchy data without requiring Snowstorm at runtime.

## Input views

| RF2 view | Behavior |
|---|---|
| Snapshot | Use the release state in Snapshot files. `--policy-date` must match the snapshot date when provided. |
| Full | Reconstruct component state at or before `--policy-date`. |

The selected HDF5 is a materialized view. Runtime checking/sanitization do not reconstruct arbitrary dates from one file.

## Relevant RF2 files

| RF2 file type | Used for |
|---|---|
| Concept | concept IDs and active state |
| Description | FSNs and semantic tags |
| Relationship | active `is-a` hierarchy and ancestor arrays |
| Association refsets | historical replacement suggestions |

See `/snomed-post-processing/source-former documentation folder/rf2-release-zip-structure.md` and `okf/snomed/` for release-format background.

## HDF5 layout

Core concept table:

```text
/concepts/codes
/concepts/fsn
/concepts/active
/concepts/semantic_tag_id
/concepts/semantic_tags
```

Optional hierarchy arrays:

```text
/concepts/ancestors_index
/concepts/ancestor_concept_index
/concepts/ancestor_distance
/concepts/min_depth_to_root
/concepts/max_depth_to_root
```

Compact policy views:

```text
/policy_views/whitelist/0/concept_index
/policy_views/blacklist/0/concept_index
/policy_views/<whitelist|blacklist>/0/root_codes
/policy_views/<whitelist|blacklist>/0/filter_tags
```

Historical associations:

```text
/historical_associations/source_index
/historical_associations/target_index
/historical_associations/association_type
```

Optional inactive `is-a` fallback edges:

```text
/historical_is_a/source_index
/historical_is_a/target_index
```

Optional legacy compatibility groups can be written with `--write-legacy-policy-groups`:

```text
/whitelist/0/codes
/whitelist/0/fsn
/blacklist/0/codes
/blacklist/0/fsn
```

## Whitelist and blacklist generation

In RF2 ZIP `--dump-mode version`, the positional `ROOT_CODE` creates the whitelist from active descendants-or-self. If omitted, `ROOT_CODE` defaults to the SNOMED CT root `138875005`.

A `--filter-list` supplied in version mode additionally creates the embedded blacklist. Filter-list entries are split as follows:

```text
numeric SCTID line -> blacklist active concept descendants-or-self
non-numeric line   -> blacklist active concepts by FSN semantic tag
```

This is the same rule format used by runtime custom release blacklists, although ingestion resolves descendants from the RF2 active parent map while runtime custom blacklist resolution uses compact HDF5 ancestor arrays.

## CLI examples

Create a whitelist HDF5 from RF2 ZIP:

```bash
uv run create-concepts-dump \
  --zip SnomedCT_Release_INT.zip \
  --output concepts.hdf5 \
  --policy-date YYYYMMDD \
  --include-ancestors \
  --dump-mode version \
  ROOT_CODE
```

Create whitelist and embedded blacklist in one run:

```bash
uv run create-concepts-dump \
  --zip SnomedCT_Release_INT.zip \
  --output concepts.hdf5 \
  --policy-date YYYYMMDD \
  --include-ancestors \
  --dump-mode version \
  --filter-list blacklist_rules.txt \
  ROOT_CODE
```

Create/update only a blacklist policy view:

```bash
uv run create-concepts-dump \
  --zip SnomedCT_Release_INT.zip \
  --output concepts.hdf5 \
  --policy-date YYYYMMDD \
  --dump-mode semantic \
  --filter-list blacklist_rules.txt
```

Use `--force-overwrite` to replace only the selected policy view. Use `--force-overwrite-concepts` only when the `/concepts` table itself should be rebuilt.

## Metadata

HDF5 files store release and policy provenance on `/concepts` and `/policy_views/...`. Blacklist rule metadata is stored compactly under:

```text
/metadata/blacklists/0/format_version
/metadata/blacklists/0/source_name
/metadata/blacklists/0/rules_raw
/metadata/blacklists/0/rules_kind
```

Expanded descendant lists are not stored in metadata; resolved concepts are represented by policy-view concept indices.

## Memory strategy

RF2 ingestion is designed to process large releases without loading unnecessary files. It keeps compact mappings for active concepts, FSNs, active parent relationships, and historical association rows. Ancestor arrays are computed only when requested with `--include-ancestors`.

## Related docs

- User guide: `README.md`
- Release-view blacklist semantics: `/snomed-post-processing/source-former documentation folder/release-view-normalization-and-blacklist-metadata.md`
- Sanitization design: `/snomed-post-processing/source-former documentation folder/sanitization-revised-design.md`
- SNOMED/RF2 background: `okf/snomed/`
