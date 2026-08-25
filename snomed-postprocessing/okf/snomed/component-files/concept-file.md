---
type: File Format
title: "RF2 Concept File"
description: "SNOMED CT RF2 file holding clinical concepts and their version states."
resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4.2-file-format-specifications/4.2.1-concept-file-specification"
tags: [snomed-ct, rf2, component-file, concept, schema]
status: stable
generated: { by: pi-coding-agent/gpt-5.5, at: 2026-08-07T10:15:52Z }
sources:
  - id: concept-file
    resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4.2-file-format-specifications/4.2.1-concept-file-specification.md"
    title: "Concept File Specification"
    author: team:snomed-international
    last_modified: 2026-08-07
---

# Purpose

The Concept File holds the clinical concepts that make up SNOMED CT. A concept is given meaning by its Fully Specified Name in the [Description File](/component-files/description-file.md) and by relationships in the [Relationship File](/component-files/relationship-file.md).[^concept-file]

# Schema

| Field | Type | Purpose | Mutable | Primary key notes |
|---|---|---|---|---|
| `id` | SCTID | Uniquely identifies the concept. | No | Yes in Full and Snapshot. |
| `effectiveTime` | Time | Inclusive date when the component version state became current. Format `YYYYMMDD`. | Yes | Yes in Full; optional in Snapshot. |
| `active` | Boolean | Whether the concept is active or inactive from the nominal release date. | Yes | No. |
| `moduleId` | SCTID | Module for this concept version; descendant of `900000000000443000 |Module|`. | Yes | No. |
| `definitionStatusId` | SCTID | Whether the concept is primitive or defined; descendant of `900000000000444006 |Definition status|`. | Yes | No. |

# Versioning

Only one concept row with the same `id` is current at a point in time. The current row is the row with the most recent `effectiveTime` before or equal to the target date. If that row has `active = 0`, the concept is inactive at that point.[^concept-file]

# Inactivation behavior

When a concept is made inactive:

* a new concept row is added with `active = 0` and `definitionStatusId` set to primitive;
* outgoing active relationships from the concept are inactivated by adding inactive relationship rows;
* active descriptions usually remain unchanged unless incorrect;
* historical association reference set rows may link the inactive concept to other concepts;
* active descriptions remaining on the inactive concept are marked through the description inactivation indicator reference set as `Concept non-current`.[^concept-file]

# Links

* [Description File](/component-files/description-file.md)
* [Relationship File](/component-files/relationship-file.md)
* [Release File Associations](/model/release-file-associations.md)
* [Metadata Hierarchy](/model/metadata-hierarchy.md)

[^concept-file]: Derived from the extracted Concept File Specification page.
