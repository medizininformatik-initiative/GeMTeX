---
type: File Format
title: "RF2 Identifier File"
description: "SNOMED CT RF2 file associating alternative identifiers with SNOMED CT components."
resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4.2-file-format-specifications/4.2.4-identifier-file-specification"
tags: [snomed-ct, rf2, component-file, identifier, schema]
status: stable
generated: { by: pi-coding-agent/gpt-5.5, at: 2026-08-07T10:15:52Z }
sources:
  - id: identifier-file
    resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4.2-file-format-specifications/4.2.4-identifier-file-specification.md"
    title: "Identifier File Specification"
    author: team:snomed-international
    last_modified: 2026-08-07
---

# Purpose

The Identifier File associates alternative identifiers, represented in their native identifier scheme, with SNOMED CT components.[^identifier-file]

# Schema

| Field | Type | Purpose | Mutable | Primary key notes |
|---|---|---|---|---|
| `alternateIdentifier` | String | Alternative identifier in its native scheme. | No | Yes in Full and Snapshot. |
| `effectiveTime` | Time | Inclusive date when the alternative identifier was associated with the component. | Yes | Yes in Full; optional in Snapshot. |
| `active` | Boolean | Whether the association is active or inactive from the `effectiveTime`. | Yes | No. |
| `moduleId` | SCTID | Source module that created this association; child of `900000000000443000 |Module|`. | Yes | No. |
| `identifierSchemeId` | SCTID | Identifier scheme concept; descendant of `900000000000453004 |Identifier scheme|`. | No | Yes in Full and Snapshot. |
| `referencedComponentId` | SCTID | SNOMED CT component associated with the alternative identifier. | Yes | No. |

# Agent implications

* Key full/snapshot identifier rows by `alternateIdentifier`, `identifierSchemeId`, and release-version key behavior.
* Resolve `identifierSchemeId` through [Metadata Hierarchy](/model/metadata-hierarchy.md).
* Use `referencedComponentId` to link an external/native identifier back to its SNOMED CT component.
* Preserve inactive rows for historical lookup.

# Links

* [Concept File](/component-files/concept-file.md)
* [Release File Associations](/model/release-file-associations.md)
* [Metadata Hierarchy](/model/metadata-hierarchy.md)

[^identifier-file]: Derived from the extracted Identifier File Specification page.
