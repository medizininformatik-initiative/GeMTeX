---
okf_version: "0.2"
---

# SNOMED CT RF2 Release File Specification OKF Bundle

This OKF bundle translates the SNOMED CT RF2 component release file documentation into agent-traversable knowledge concepts. Source provenance is recorded primarily as upstream SNOMED/GitBook documentation URLs.

# Core concepts

* [RF2 Component Release File Specification](release-format-rf2.md) - Overview of SNOMED CT Release Format 2 component release files.
* [Release File Associations](model/release-file-associations.md) - How concepts, descriptions, relationships, identifiers, and metadata connect.
* [Metadata Hierarchy](model/metadata-hierarchy.md) - Metadata concepts used as controlled values in RF2 component files.
* [Implementation Notes](implementation-notes.md) - Practical guidance for parsers, loaders, and agents.

# Component file formats

* [Component Files](component-files/) - Index of RF2 component file schema concepts.
* [Concept File](component-files/concept-file.md) - Clinical concept rows and concept versioning.
* [Description File](component-files/description-file.md) - Terms attached to concepts.
* [Relationship File](component-files/relationship-file.md) - Concept-to-concept hierarchy and attribute relationships.
* [Identifier File](component-files/identifier-file.md) - Alternative identifiers associated with SNOMED CT components.
* [Concrete Value File](component-files/concrete-value-file.md) - Relationships to literal values.
* [Transitive Closure File](component-files/transitive-closure-file.md) - Generated closure of the subtype hierarchy.

# References

* [Source Documents](references/source-documents.md) - Upstream source document map.
