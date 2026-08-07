---
type: Playbook
title: "Implementing RF2 Component File Readers"
description: "Practical guidance for agents and software loading SNOMED CT RF2 component files."
tags: [snomed-ct, rf2, parser, loader, implementation]
status: stable
generated: { by: pi-coding-agent/gpt-5.5, at: 2026-08-07T10:15:52Z }
sources:
  - id: agent-brief
    resource: "/release-format-rf2.md"
    title: "RF2 Component Release File Specification"
    author: pi-coding-agent/gpt-5.5
    last_modified: 2026-08-07
  - id: cheatsheet
    resource: "/component-files/index.md"
    title: "RF2 Component File Formats"
    author: pi-coding-agent/gpt-5.5
    last_modified: 2026-08-07
---

# Parsing model

RF2 component files are versioned row sets. Do not treat component identifiers as unique row keys in Full release files. Instead, group rows by the component identifier and resolve current state by `effectiveTime`.[^agent-brief]

# Loader workflow

1. Identify the file type from release package path/name.
2. Load the corresponding OKF schema:
   * [Concept File](/component-files/concept-file.md)
   * [Description File](/component-files/description-file.md)
   * [Relationship File](/component-files/relationship-file.md)
   * [Identifier File](/component-files/identifier-file.md)
   * [Concrete Value File](/component-files/concrete-value-file.md)
3. Parse tab-delimited UTF-8 rows.
4. Validate field count and basic datatypes.
5. Parse `effectiveTime` as `YYYYMMDD` where present.
6. Preserve all rows for historical reconstruction.
7. For current views, select max `effectiveTime` per identifier at or before the requested date.
8. Filter current active state using `active`.
9. Resolve SCTID-valued metadata fields using [Metadata Hierarchy](/model/metadata-hierarchy.md).
10. Construct graph associations using [Release File Associations](/model/release-file-associations.md).

# Version-state rule

For a component identifier and target date:

```text
current_row = row with greatest effectiveTime <= target_date
current_state = active if current_row.active == 1 else inactive
```

Snapshot files already represent a point-in-time view, but consumers should still preserve and parse `effectiveTime` when present.

# Graph construction rule

To build a current concept graph:

1. Load current active concepts from the [Concept File](/component-files/concept-file.md).
2. Attach current active descriptions through `Description.conceptId`.
3. Add active hierarchy edges from [Relationship File](/component-files/relationship-file.md) rows where `typeId = 116680003 |is a|`.
4. Add active attribute edges from relationship rows whose `typeId` is a valid concept model attribute.
5. Add concrete literal attributes from [Concrete Value File](/component-files/concrete-value-file.md).
6. Exclude inactive current rows unless historical analysis is required.

# Validation hints

* `moduleId` should resolve under `900000000000443000 |Module|`.
* `Concept.definitionStatusId` should resolve under `900000000000444006 |Definition status|`.
* `Description.typeId` should resolve under `900000000000446008 |Description type|`.
* `Description.caseSignificanceId` should resolve under `900000000000447004 |Case significance|`.
* `Relationship.characteristicTypeId` and `ConcreteValue.characteristicTypeId` should resolve under `900000000000449001 |Characteristic type|`.
* `Relationship.modifierId` and `ConcreteValue.modifierId` should resolve under `900000000000450001 |Modifier|`.
* `Identifier.identifierSchemeId` should resolve under `900000000000453004 |Identifier scheme|`.[^cheatsheet]

# Common mistakes

* Treating Full files as if they contain only one row per component.
* Dropping inactive rows and losing historical state.
* Using `languageCode` as dialect acceptability.
* Joining concrete `value` fields to concepts.
* Ignoring relationship groups when interpreting logical definitions.
* Assuming all relationship `typeId` values are hierarchy edges.

[^agent-brief]: Derived from the OKF RF2 overview and linked SNOMED source documentation.
[^cheatsheet]: Derived from the OKF component file schema concepts and linked SNOMED source documentation.
