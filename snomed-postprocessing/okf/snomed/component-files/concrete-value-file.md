---
type: File Format
title: "RF2 Concrete Value File"
description: "SNOMED CT RF2 file representing relationships from concepts to literal integer, decimal, or string values."
resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4.2-file-format-specifications/4.2.6-concrete-value-file-specification"
tags: [snomed-ct, rf2, component-file, concrete-value, relationship, schema]
status: stable
generated: { by: pi-coding-agent/gpt-5.5, at: 2026-08-07T10:15:52Z }
sources:
  - id: concrete-value-file
    resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4.2-file-format-specifications/4.2.6-concrete-value-file-specification.md"
    title: "Concrete Value File Specification"
    author: team:snomed-international
    last_modified: 2026-08-07
---

# Purpose

The Concrete Value File represents relationships where the relationship value is a literal concrete value rather than a destination concept.[^concrete-value-file]

# Schema

| Field | Type | Purpose | Mutable | Primary key notes |
|---|---|---|---|---|
| `id` | SCTID | Uniquely identifies the relationship. | No | Yes in Full and Snapshot. |
| `effectiveTime` | Time | Inclusive date when this relationship version state became current. Format `YYYYMMDD`. | Yes | Yes in Full; optional in Snapshot. |
| `active` | Boolean | Whether the relationship state is active or inactive from the nominal release date. | Yes | No. |
| `moduleId` | SCTID | Module for this relationship version; child of `900000000000443000 |Module|`. | Yes | No. |
| `sourceId` | SCTID | Source concept being defined by this relationship. | No | No. |
| `value` | String | Concrete literal value. Integers/decimals are prefixed with `#`; strings are double quoted and embedded quotes are escaped with backslash. | No | No. |
| `relationshipGroup` | Integer | Groups logically associated relationships with the same `sourceId`. | Yes | No. |
| `typeId` | SCTID | Data attribute type; must be subtype of `762706009 |Concept model data attribute (attribute)|`. | No | No. |
| `characteristicTypeId` | SCTID | Characteristic type; descendant of `900000000000449001 |Characteristic type|`. | Yes | No. |
| `modifierId` | SCTID | Description Logic restriction type; child of `900000000000450001 |Modifier|`. | Yes | No. |

# Value syntax

* Numbers are prefixed by `#`, for example `#500`.
* Strings are surrounded by double quotes.
* Double quotes inside strings are escaped with a backslash.[^concrete-value-file]

# Example semantics

A concrete value relationship may read as:

* source concept: `322236009 |Product containing precisely paracetamol 500 milligram/1 each conventional release oral tablet (clinical drug)|`
* relationship type: `1142135004 |Has presentation strength numerator value (attribute)|`
* value: `#500`[^concrete-value-file]

# Agent implications

* Parse `value` as a typed literal using RF2 concrete value syntax.
* Do not join `value` to the Concept File; use `typeId` to interpret what the literal means.
* Resolve `typeId` as a subtype of `762706009 |Concept model data attribute|`.
* Preserve relationship grouping behavior parallel to the [Relationship File](/component-files/relationship-file.md).

# Links

* [Relationship File](/component-files/relationship-file.md)
* [Concept File](/component-files/concept-file.md)
* [Metadata Hierarchy](/model/metadata-hierarchy.md)

[^concrete-value-file]: Derived from the extracted Concrete Value File Specification page.
