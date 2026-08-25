---
type: File Format
title: "RF2 Description File"
description: "SNOMED CT RF2 file containing terms and descriptions attached to concepts."
resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4.2-file-format-specifications/4.2.2-description-file-specification"
tags: [snomed-ct, rf2, component-file, description, terms, schema]
status: stable
generated: { by: pi-coding-agent/gpt-5.5, at: 2026-08-07T10:15:52Z }
sources:
  - id: description-file
    resource: "https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4.2-file-format-specifications/4.2.2-description-file-specification.md"
    title: "Description File Specification"
    author: team:snomed-international
    last_modified: 2026-08-07
---

# Purpose

The Description File stores human-readable text descriptions associated with [Concept File](/component-files/concept-file.md) records. Each concept has at least one Fully Specified Name and at least one synonym.[^description-file]

# Schema

| Field | Type | Purpose | Mutable | Primary key notes |
|---|---|---|---|---|
| `id` | SCTID | Uniquely identifies the description. | No | Yes in Full and Snapshot. |
| `effectiveTime` | Time | Inclusive date when this description version state became current. Format `YYYYMMDD`. | Yes | Yes in Full; optional in Snapshot. |
| `active` | Boolean | Whether the description state is active or inactive from the nominal release date. | Yes | No. |
| `moduleId` | SCTID | Module for this description version; child of `900000000000443000 |Module|`. | Yes | No. |
| `conceptId` | SCTID | Concept to which this description applies. | No | No. |
| `languageCode` | String | Two-character ISO-639-1 language code; language only, not dialect/country. | No | No. |
| `typeId` | SCTID | Description type; child of `900000000000446008 |Description type|`. | No | No. |
| `term` | String | UTF-8 text value of the description version. | Yes | No. |
| `caseSignificanceId` | SCTID | Case significance; child of `900000000000447004 |Case significance|`. | Yes | No. |

# Term constraints

* The `term` field has an overall maximum length of 32 KB.
* Additional maximum lengths and text formats are configurable by description type in the Description Format Reference Set.
* The Description Format Reference Set defines whether terms are plain text, limited HTML, or XHTML.
* Control characters including tabs, carriage returns, and line feeds do not appear in plain text or limited HTML term formats.[^description-file]

# Agent implications

* Use `conceptId` to attach descriptions to concepts.
* Do not infer dialect acceptability from `languageCode`; it only records language level.
* Resolve `typeId` to distinguish Fully Specified Name, synonym, and other description types.
* Resolve `caseSignificanceId` before performing case-sensitive term matching.

# Links

* [Concept File](/component-files/concept-file.md)
* [Release File Associations](/model/release-file-associations.md)
* [Metadata Hierarchy](/model/metadata-hierarchy.md)

[^description-file]: Derived from the extracted Description File Specification page.
