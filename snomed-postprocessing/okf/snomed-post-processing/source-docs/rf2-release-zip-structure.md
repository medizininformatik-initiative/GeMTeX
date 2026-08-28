---
type: Imported Documentation
title: "RF2 ZIP structure notes for this project"
description: Lossless OKF import of /snomed-post-processing/source-former documentation folder/rf2-release-zip-structure.md.
resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/rf2-release-zip-structure.md
tags: [snomed-post-processing, imported-docs, legacy-docs]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: original-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/rf2-release-zip-structure.md
    title: "Original /snomed-post-processing/source-former documentation folder/rf2-release-zip-structure.md"
    author: team:project-maintainers
---

# RF2 ZIP structure notes for this project

This document summarizes the RF2 ZIP parts relevant to SNOMED Postprocessing. For general RF2 background, prefer the local OKF notes under `okf/snomed/`.

## Package layout

SNOMED CT RF2 release ZIPs usually contain language/refset-specific files under `Full/`, `Snapshot/`, and/or `Delta/` directories. This project uses:

| View | Meaning in this project |
|---|---|
| Snapshot | Already-materialized component state for one release date. |
| Full | Historical component rows used to reconstruct state at `--policy-date`. |
| Delta | Not used for current HDF5 ingestion. |

## Files used by ingestion

| RF2 component | Typical filename pattern | Purpose |
|---|---|---|
| Concept | `sct2_Concept_*.txt` | concept IDs and active state |
| Description | `sct2_Description_*.txt` | FSNs for labels and semantic tags |
| Relationship | `sct2_Relationship_*.txt` | active `is-a` hierarchy and ancestor arrays |
| Association refset | `der2_cRefset_Association*.txt` | historical replacement candidates |

Other RF2 files, such as text definitions, maps, simple refsets, OWL expressions, and metadata refsets, are not required for the current policy/sanitization workflows.

## Important fields

RF2 files are tab-separated and include an `effectiveTime` and `active` column. Full-view ingestion keeps the latest row at or before the requested policy date.

Key fields used here:

| File | Fields |
|---|---|
| Concept | `id`, `effectiveTime`, `active` |
| Description | `conceptId`, `typeId`, `term`, `active`, language fields |
| Relationship | `sourceId`, `destinationId`, `typeId`, `active`, `characteristicTypeId` |
| Association refset | `referencedComponentId`, `targetComponentId`, refset ID / association type |

The active `is-a` type is used to build parent maps and ancestor arrays.

## FSNs and semantic tags

Blacklist semantic-tag rules rely on FSNs. The semantic tag is parsed from the final parenthesized suffix of the FSN, for example:

```text
Appendectomy (procedure) -> procedure
```

The HDF5 stores semantic tags categorically under `/concepts/semantic_tag_id` and `/concepts/semantic_tags`.

## Association refsets

Historical associations support sanitization suggestions for inactive/outdated concepts. The maintained implementation maps association refset IDs to human-readable association types and stores source/target concept indices in HDF5.

Examples of useful association semantics include:

```text
SAME_AS
REPLACED_BY
POSSIBLY_EQUIVALENT_TO
WAS_A
MOVED_TO
```

Only active association rows whose source and target concepts are known in the HDF5 are useful for runtime suggestions.

## Current limitations

- Delta releases are not part of the current ingestion path.
- Text definitions, maps, OWL axioms, and most metadata refsets are ignored.
- Runtime analysis uses the materialized HDF5; it does not reopen RF2 ZIPs.

## Related docs

- Ingestion design: `/snomed-post-processing/source-former documentation folder/rf2-to-hdf5-ingestion-design.md`
- Sanitization design: `/snomed-post-processing/source-former documentation folder/sanitization-revised-design.md`
- Local RF2 background: `okf/snomed/release-format-rf2.md`
- Component notes: `okf/snomed/component-files/`
