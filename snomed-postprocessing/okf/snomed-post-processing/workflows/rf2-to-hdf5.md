---
type: Workflow
title: RF2/Snowstorm to HDF5 policy store
description: How SNOMED RF2 ZIPs or Snowstorm branches become compact HDF5 policy files.
resource: /src/snomed_post_processing/pipelines/hdf5_dump_creation.py
tags: [workflow, rf2, snowstorm, hdf5, snomed]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: ingestion-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/rf2-to-hdf5-ingestion-design.md
    title: RF2 release ZIP to HDF5 ingestion
  - id: rf2-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/rf2-release-zip-structure.md
    title: RF2 ZIP structure notes
  - id: hdf5-writer
    resource: /src/snomed_post_processing/release_ingestion/hdf5_writer.py
    title: HDF5 writer implementation
---

# Goal

Create a self-contained SNOMED HDF5 from an RF2 release ZIP, or from Snowstorm in legacy mode, for fast local policy checking and sanitization. Runtime checking/sanitization uses the selected materialized HDF5 and does not reconstruct arbitrary release dates on demand.

# RF2 input views

| RF2 view | Behavior |
|---|---|
| Snapshot | Use the already-materialized component state for one release date. If `--policy-date` is provided, it must match the snapshot date. |
| Full | Reconstruct component state at or before `--policy-date` by selecting latest RF2 rows at/before that date. |
| Delta | Not used by current ingestion. |

# RF2 files used

| Component | Typical pattern | Purpose |
|---|---|---|
| Concept | `sct2_Concept_*.txt` | SCTIDs and active state. |
| Description | `sct2_Description_*.txt` | FSNs and semantic tags. |
| Relationship | `sct2_Relationship_*.txt` | Active `is-a` parent map and ancestor arrays. |
| Association refset | `der2_cRefset_Association*.txt` | Historical replacement candidates. |

Other RF2 artifacts such as text definitions, maps, simple refsets, OWL expressions, and most metadata refsets are ignored by current policy/sanitization workflows.

# CLI examples

Create whitelist HDF5 from RF2 ZIP:

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

Use `--force-overwrite` to replace only the selected policy view. Use `--force-overwrite-concepts` only when `/concepts` should be rebuilt.

# Blacklist rule semantics

Filter-list entries are split as follows:

```text
numeric SCTID line -> blacklist active descendants-or-self
non-numeric line   -> blacklist active concepts by FSN semantic tag
```

Embedded blacklist creation uses an RF2 active parent map. Runtime custom blacklist resolution uses compact HDF5 ancestor arrays; semantics should remain aligned.

# Related concepts

- [HDF5 policy store](/snomed-post-processing/data/hdf5-policy-store.md)
- [Release view and blacklist behavior](/snomed-post-processing/workflows/sanitization-suggestions.md#target-view-validity)
- [Imported ingestion doc](/snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/rf2-to-hdf5-ingestion-design.md)
