---
type: Reference
title: "SNOMED CT Metadata Hierarchy"
description: "Metadata concepts that provide controlled values for RF2 component release file fields."
resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4.3-metadata-hierarchy"
tags: [snomed-ct, rf2, metadata, controlled-values, sctid]
status: stable
generated: { by: pi-coding-agent/gpt-5.5, at: 2026-08-07T10:15:52Z }
sources:
  - id: metadata
    resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4.3-metadata-hierarchy.md"
    title: "Metadata Hierarchy"
    author: team:snomed-international
    last_modified: 2026-08-07
---

# Definition

The metadata hierarchy defines sets of concepts that represent allowed enumerated values and supporting metadata used by RF2 component release files.[^metadata]

The root metadata concept is:

* `900000000000441003 |SNOMED CT Model Component (metadata)|`

This concept is a subtype of the SNOMED CT root concept `138875005 |SNOMED CT Concept|`.[^metadata]

# Major metadata branches

| SCTID | Term | Role |
|---|---|---|
| `106237007` | `Linkage concept` | Concepts specifying semantic relationships and asserted associations. |
| `370136006` | `Namespace concept` | Concepts specifying allocated extension namespaces. |
| `900000000000442005` | `Core metadata concept` | Values referenced from component files such as Concept, Description, Relationship, and Identifier. |
| `900000000000454005` | `Foundation metadata concept` | Metadata supporting extensibility and reference sets. |
| `762947003` | `OWL metadata concept` | Metadata used in OWL reference sets. |

# Core metadata values used by component files

| Metadata concept | Common RF2 field usage |
|---|---|
| `900000000000443000 |Module|` | `moduleId` in component files. |
| `900000000000444006 |Definition status|` | `Concept.definitionStatusId`. |
| `900000000000446008 |Description type|` | `Description.typeId`. |
| `900000000000447004 |Case significance|` | `Description.caseSignificanceId`. |
| `900000000000449001 |Characteristic type|` | `Relationship.characteristicTypeId`, `ConcreteValue.characteristicTypeId`. |
| `900000000000450001 |Modifier|` | `Relationship.modifierId`, `ConcreteValue.modifierId`. |
| `900000000000453004 |Identifier scheme|` | `Identifier.identifierSchemeId`. |

# Important concept-model references

| SCTID | Term | Usage |
|---|---|---|
| `116680003` | `Is a` | Relationship type for subtype hierarchy edges. |
| `410662002` | `Concept model attribute` | Supertype for regular relationship attribute types. |
| `762706009` | `Concept model data attribute` | Supertype for concrete value attribute types. |

# Linked schemas

* [Concept File](/component-files/concept-file.md)
* [Description File](/component-files/description-file.md)
* [Relationship File](/component-files/relationship-file.md)
* [Identifier File](/component-files/identifier-file.md)
* [Concrete Value File](/component-files/concrete-value-file.md)

[^metadata]: Derived from the extracted Metadata Hierarchy page.
