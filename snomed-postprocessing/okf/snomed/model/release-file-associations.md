---
type: Concept Model
title: "RF2 Release File Associations"
description: "Associations between SNOMED CT RF2 concept, description, relationship, and metadata files."
resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4.1-associations-between-release-files"
tags: [snomed-ct, rf2, associations, graph, concept-model]
status: stable
generated: { by: pi-coding-agent/gpt-5.5, at: 2026-08-07T10:15:52Z }
sources:
  - id: associations
    resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4.1-associations-between-release-files.md"
    title: "Associations Between Release Files"
    author: team:snomed-international
    last_modified: 2026-08-07
---

# Core associations

Each [Concept File](/component-files/concept-file.md) row represents a version of a clinical concept. Multiple rows with the same `id` but different `effectiveTime` values are versions of the same concept.[^associations]

Each concept has two or more associated [Description File](/component-files/description-file.md) rows:

* at least one Fully Specified Name;
* at least one synonym.[^associations]

A description is linked to exactly one concept through `Description.conceptId`. All versions of a description must keep the same `conceptId`.[^associations]

Each [Relationship File](/component-files/relationship-file.md) row represents a relationship version from a source concept to a destination concept. Multiple rows with the same relationship `id` but different `effectiveTime` values are versions of the same relationship.[^associations]

# Relationship semantics

A relationship uses three important concept references:

| Field | Meaning |
|---|---|
| `sourceId` | Concept being defined by the relationship. |
| `destinationId` | Target concept of the relationship. |
| `typeId` | Relationship or attribute type concept. |

All versions of a relationship must keep the same `sourceId`, `destinationId`, and `typeId`.[^associations]

The most basic relationship is `116680003 |is a|`, which forms the subtype hierarchy. A child concept may have more than one parent concept. The root concept is `138875005 |SNOMED CT Concept|`.[^associations]

Attribute relationships use `typeId` values that are subtypes of `410662002 |Concept model attribute|`.[^associations]

# Metadata links

Many RF2 fields contain SCTIDs that refer to concepts in [Metadata Hierarchy](/model/metadata-hierarchy.md). These links provide enumerated controlled values rather than direct component-to-component semantics.

Examples:

* `moduleId` points into `900000000000443000 |Module|`.
* `definitionStatusId` points into `900000000000444006 |Definition status|`.
* `typeId` in descriptions points into `900000000000446008 |Description type|`.
* `characteristicTypeId` points into `900000000000449001 |Characteristic type|`.
* `modifierId` points into `900000000000450001 |Modifier|`.

# Agent implications

For graph construction:

1. Treat concepts as graph nodes keyed by `Concept.id`.
2. Attach descriptions to nodes through `Description.conceptId`.
3. Add directed edges from `Relationship.sourceId` to `Relationship.destinationId`.
4. Interpret `Relationship.typeId = 116680003` as an `is a` hierarchy edge.
5. Interpret other valid relationship `typeId` values as concept model attribute edges.
6. Filter by current effective state and `active = 1` before building a current graph.

[^associations]: Derived from the extracted Associations Between Release Files page.
