---
type: File Format
title: "RF2 Transitive Closure File"
description: "A generated file containing the transitive closure of the SNOMED CT subtype hierarchy."
resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/appendices/appendix-b.-specification-reference-information/t/transitive-closure-file"
tags: [snomed-ct, rf2, hierarchy, transitive-closure, generated-artifact]
status: stable
generated: { by: pi-coding-agent/gpt-5.5, at: 2026-08-07T10:15:52Z }
sources:
  - id: transitive-closure-file
    resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/appendices/appendix-b.-specification-reference-information/t/transitive-closure-file.md"
    title: "Transitive closure file"
    author: team:snomed-international
    last_modified: 2026-08-07
---

# Purpose

The transitive closure file contains the transitive closure of the SNOMED CT subtype hierarchy.[^transitive-closure-file]

# Distribution status

The transitive closure file is not currently distributed. It can be generated from the snapshot [Relationship File](/component-files/relationship-file.md).[^transitive-closure-file]

# Generation source

Generation depends on active subtype relationships where:

* `Relationship.typeId = 116680003 |is a|`
* `Relationship.active = 1`
* the relationship row is current in the snapshot being used

# Agent implications

* Treat this as a derived artifact, not a primary RF2 component source.
* Regenerate when the source snapshot relationship file changes.
* Use it for efficient ancestor/descendant queries when available.
* If absent, compute closure from active `is a` relationships.

# Links

* [Relationship File](/component-files/relationship-file.md)
* [Release File Associations](/model/release-file-associations.md)

[^transitive-closure-file]: Derived from the extracted Transitive closure file page.
