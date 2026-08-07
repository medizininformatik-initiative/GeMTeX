---
type: Specification
title: "SNOMED CT RF2 Component Release File Specification"
description: "Overview of RF2 component release files used for official SNOMED CT production releases."
resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4-component-release-files-specification"
tags: [snomed-ct, rf2, release-format, component-files]
status: stable
generated: { by: pi-coding-agent/gpt-5.5, at: 2026-08-07T10:15:52Z }
sources:
  - id: overview-md
    resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4-component-release-files-specification.md"
    title: "Component Release Files Specification - Overview"
    author: team:snomed-international
    last_modified: 2026-08-07
  - id: upstream-overview
    resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4-component-release-files-specification"
    title: "SNOMED CT Release File Specification - Component Release Files Specification"
    author: "team:snomed-international"
    last_modified: 2025-10-01
---

# Definition

SNOMED CT Release Format 2 (RF2) is the official production release format for SNOMED CT component data. RF2 is designed to be flexible, stable, unambiguous, and useful for distribution while allowing future adaptation.[^overview-md]

RF2 component release files are not mandated for internal terminology development usage or as a generic interchange mechanism between terminology development systems.[^overview-md]

# Main section concepts

The component release file specification is organized around these linked concepts:

* [Release File Associations](/model/release-file-associations.md) - how RF2 component files connect.
* [Component File Formats](/component-files/index.md) - schema-level details for each component file.
* [Metadata Hierarchy](/model/metadata-hierarchy.md) - controlled values and metadata concepts used in component fields.

# Component file family

The primary component file formats are:

* [Concept File](/component-files/concept-file.md)
* [Description File](/component-files/description-file.md)
* [Relationship File](/component-files/relationship-file.md)
* [Identifier File](/component-files/identifier-file.md)
* [Concrete Value File](/component-files/concrete-value-file.md)
* [Transitive Closure File](/component-files/transitive-closure-file.md)

# Agent reading strategy

1. Read this overview first to establish scope.
2. Follow [Release File Associations](/model/release-file-associations.md) to understand graph semantics.
3. Follow each component schema under [Component File Formats](/component-files/index.md) when parsing or validating files.
4. Resolve metadata-constrained SCTID fields using [Metadata Hierarchy](/model/metadata-hierarchy.md).
5. Use [Implementation Notes](/implementation-notes.md) for loader and parser behavior.

[^overview-md]: Source concept derived from the upstream GitBook Markdown page.
