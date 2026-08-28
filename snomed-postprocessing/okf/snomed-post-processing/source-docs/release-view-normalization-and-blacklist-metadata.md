---
type: Imported Documentation
title: "Release-view normalization and blacklist metadata"
description: Lossless OKF import of /snomed-post-processing/source-former documentation folder/release-view-normalization-and-blacklist-metadata.md.
resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/release-view-normalization-and-blacklist-metadata.md
tags: [snomed-post-processing, imported-docs, legacy-docs]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: original-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/release-view-normalization-and-blacklist-metadata.md
    title: "Original /snomed-post-processing/source-former documentation folder/release-view-normalization-and-blacklist-metadata.md"
    author: team:project-maintainers
---

# Release-view normalization and blacklist metadata

## Goal

The GUI/CLI support two sanitization target views over INCEpTION/UIMA SNOMED CT annotations:

1. **Policy view**: candidates must satisfy the materialized whitelist/blacklist policy.
2. **Release view**: candidates only need to be active concepts in the selected SNOMED CT release, with optional blacklist exclusions.

Both workflows use the same high-level phases:

```text
INCEpTION export + HDF5
        |
Check annotations / load CriticalFindings
        |
Suggest replacements
        |
Review suggestions
        |
Apply reviewed decisions to a copied export
```

The selected HDF5 is the materialized SNOMED view. Runtime checking and sanitization do not reconstruct arbitrary earlier snapshots from one HDF5. To target another policy date or release snapshot, create/select an HDF5 built for that date.

## Candidate validity

### Policy view

Policy mode remains the strict GeMTeX policy workflow. An annotation or replacement candidate is acceptable when its concept is:

```text
active
AND in whitelist policy view
AND not in blacklist policy view
```

Replacement candidates must also not be the SNOMED CT root.

### Release view

Release mode deliberately has no whitelist requirement. By default, a replacement candidate is acceptable when its concept is:

```text
active in the selected release
```

Replacement candidates must also not be the SNOMED CT root. Blacklist exclusions are opt-in.

## Release-view blacklist modes

Release mode can use the embedded HDF5 blacklist, a custom runtime blacklist, both, or neither:

| CLI flags / GUI choices | Embedded HDF5 blacklist | Custom blacklist | Effective release-view rule |
|---|---:|---:|---|
| none / no blacklist | ignored | none | active concept |
| `--enforce-embedded-blacklist` | enforced | none | active AND not embedded-blacklisted |
| `--custom-blacklist PATH` | ignored | enforced | active AND not custom-blacklisted |
| both | enforced | enforced | active AND not embedded-blacklisted AND not custom-blacklisted |

The embedded blacklist is read from:

```text
/policy_views/blacklist/0/concept_index
```

A custom blacklist file uses the same rule format as RF2 blacklist ingestion:

```text
numeric SCTID line -> exclude that concept and descendants
non-numeric line   -> exclude concepts by FSN semantic tag
```

Example:

```text
substance
373873005
organism
```

Embedded blacklist creation and runtime custom-blacklist resolution intentionally use different traversal backends because they run at different times:

| Path | Descendant backend |
|---|---|
| RF2/HDF5 ingestion | active RF2 parent map |
| runtime custom blacklist | compact HDF5 ancestor arrays |

The blacklist semantics should stay aligned between these two paths.

## Blacklist metadata in HDF5

HDF5 files store compact blacklist provenance/rule metadata, not expanded per-rule descendant lists:

```text
/metadata/blacklists/0/format_version
/metadata/blacklists/0/source_name
/metadata/blacklists/0/rules_raw
/metadata/blacklists/0/rules_kind
```

`rules_kind` contains:

```text
fsn_tag
concept_descendants
```

Resolved blacklist concepts are stored in the policy view (`/policy_views/blacklist/0/concept_index`). Numeric rule FSNs can be looked up dynamically from `/concepts` for GUI display.

## Implementation status

Implemented:

- Policy-mode checking and sanitization keep strict whitelist/blacklist semantics.
- Release-view suggestion generation is available in CLI and GUI.
- Historical association, ancestor fallback, semantic BM25, and processed SNOGIT-cache candidates all use the selected target-view validity gates.
- CLI release-view options:
  - `--target-view release`
  - `--enforce-embedded-blacklist`
  - `--custom-blacklist PATH`
- GUI release-view options:
  - no blacklist
  - enforce embedded HDF5 blacklist
  - use custom blacklist rule file via Upload / Data directory / Server path
- HDF5 blacklist rule metadata is written and displayed in metadata summaries.

Still separate/future work:

- Release-view check pipeline for producing CriticalFindings directly from active-release validity.
- Large-dataset smoke/performance testing for custom blacklist resolution, BM25, and processed SNOGIT-cache workflows.
