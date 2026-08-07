---
type: File Format
title: "RF2 Relationship File"
description: "SNOMED CT RF2 file representing concept-to-concept hierarchy and attribute relationships."
resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4.2-file-format-specifications/4.2.3-relationship-file-specification"
tags: [snomed-ct, rf2, component-file, relationship, hierarchy, schema]
status: stable
generated: { by: pi-coding-agent/gpt-5.5, at: 2026-08-07T10:15:52Z }
sources:
  - id: relationship-file
    resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4.2-file-format-specifications/4.2.3-relationship-file-specification.md"
    title: "Relationship File Specification"
    author: team:snomed-international
    last_modified: 2026-08-07
---

# Purpose

The Relationship File stores concept-to-concept relationships. These include `is a` subtype hierarchy relationships and concept model attribute relationships.[^relationship-file]

# Schema

| Field | Type | Purpose | Mutable | Primary key notes |
|---|---|---|---|---|
| `id` | SCTID | Uniquely identifies the relationship. | No | Yes in Full and Snapshot. |
| `effectiveTime` | Time | Inclusive date when this relationship version state became current. Format `YYYYMMDD`. | Yes | Yes in Full; optional in Snapshot. |
| `active` | Boolean | Whether the relationship state is active or inactive from the nominal release date. | Yes | No. |
| `moduleId` | SCTID | Module for this relationship version; child of `900000000000443000 |Module|`. | Yes | No. |
| `sourceId` | SCTID | Source concept being defined by this relationship. | No | No. |
| `destinationId` | SCTID | Destination concept representing the value of the attribute represented by `typeId`. | No | No. |
| `relationshipGroup` | Integer | Groups logically associated relationships with the same `sourceId`. | Yes | No. |
| `typeId` | SCTID | Relationship type or defining attribute. Must be `116680003 |is a|` or subtype of `410662002 |Concept model attribute|`. | No | No. |
| `characteristicTypeId` | SCTID | Characteristic type; descendant of `900000000000449001 |Characteristic type|`. | Yes | No. |
| `modifierId` | SCTID | Description Logic restriction type; child of `900000000000450001 |Modifier|`. | Yes | No. |

# Relationship examples

An `is a` relationship may be read as:

* source concept: `371883000 |Outpatient procedure|`
* relationship type: `116680003 |Is a|`
* destination concept: `71388002 |Procedure|`[^relationship-file]

# Agent implications

* Build hierarchy edges from active rows where `typeId = 116680003`.
* Build attribute edges from active rows where `typeId` is a subtype of `410662002 |Concept model attribute|`.
* Group active relationships by `sourceId` and `relationshipGroup` to preserve logically associated attributes.
* In practical terms, `modifierId` is currently usually `900000000000451002 |Some|` and can often be ignored for basic loading, but it should still be parsed and preserved.[^relationship-file]

# Links

* [Concept File](/component-files/concept-file.md)
* [Concrete Value File](/component-files/concrete-value-file.md)
* [Release File Associations](/model/release-file-associations.md)
* [Metadata Hierarchy](/model/metadata-hierarchy.md)

[^relationship-file]: Derived from the extracted Relationship File Specification page.
