# Observed SNOMED CT RF2 ZIP Structure

This document summarizes the observed structure of `data/international.zip`, inspected directly from the ZIP without extraction. For each text file, only the header and at most the first 20 lines were inspected.

## Package identity

The ZIP contains a SNOMED CT International Edition RF2 production package:

```text
international/SnomedCT_InternationalRF2_PRODUCTION_20260401T120000Z/
```

The package metadata reports:

```text
effectiveTime: 20260401
previousPublishedPackage: SnomedCT_InternationalRF2_PRODUCTION_20260301T120000Z.zip
languageRefsets:
  900000000000508004 = Great Britain English language reference set
  900000000000509007 = United States of America English language reference set
```

The archive also contains macOS metadata entries such as `__MACOSX/` and `.DS_Store`. Ingestion code should ignore these.

## High-level layout

The observed package contains `Full` and `Snapshot` RF2 views:

```text
SnomedCT_InternationalRF2_PRODUCTION_20260401T120000Z/
├── Full/
│   ├── Terminology/
│   └── Refset/
│       ├── Content/
│       ├── Language/
│       ├── Map/
│       └── Metadata/
├── Snapshot/
│   ├── Terminology/
│   └── Refset/
│       ├── Content/
│       ├── Language/
│       ├── Map/
│       └── Metadata/
├── Readme_en_20260401.txt
└── release_package_information.json
```

No `Delta/` view was observed in this archive.

## RF2 file conventions observed

Most RF2 content files are UTF-8, tab-delimited text files. The first row is the column header. File names encode:

- content type, e.g. `Concept`, `Description`, `Relationship`, `Association`;
- view, e.g. `Full` or `Snapshot`;
- edition/module marker, e.g. `INT`;
- release date, e.g. `20260401`;
- language marker where applicable, e.g. `-en`.

Examples:

```text
sct2_Concept_Full_INT_20260401.txt
sct2_Description_Snapshot-en_INT_20260401.txt
der2_cRefset_AssociationFull_INT_20260401.txt
```

## Terminology files

### Concept

Observed files:

```text
Full/Terminology/sct2_Concept_Full_INT_20260401.txt
Snapshot/Terminology/sct2_Concept_Snapshot_INT_20260401.txt
```

Header:

```text
id effectiveTime active moduleId definitionStatusId
```

Use for:

- concept existence;
- active/inactive state;
- module membership;
- primitive vs fully defined status via `definitionStatusId`.

For a `Full` view, reconstruct the release state by keeping the latest row per `id` where `effectiveTime <= target_release_date`, then apply active filtering as needed. For a `Snapshot` view, rows already represent the package release state, but inactive rows may still be present, so `active == 1` must still be checked when active-only data is needed.

### Description

Observed files:

```text
Full/Terminology/sct2_Description_Full-en_INT_20260401.txt
Snapshot/Terminology/sct2_Description_Snapshot-en_INT_20260401.txt
```

Header:

```text
id effectiveTime active moduleId conceptId languageCode typeId term caseSignificanceId
```

Use for:

- Fully specified names, where `typeId = 900000000000003001`;
- synonyms, where `typeId = 900000000000013009`;
- term text and semantic tags embedded in FSNs.

The inspected International Edition package contains English description files (`-en`). German descriptions would require a German-language extension/package, not this International Edition ZIP.

For `Full` descriptions, reconstruct latest rows per description `id` first, then filter to active rows and the desired `typeId`/language.

### TextDefinition

Observed files:

```text
Full/Terminology/sct2_TextDefinition_Full-en_INT_20260401.txt
Snapshot/Terminology/sct2_TextDefinition_Snapshot-en_INT_20260401.txt
```

Header:

```text
id effectiveTime active moduleId conceptId languageCode typeId term caseSignificanceId
```

Use for textual definitions. These are not required for whitelist/blacklist checks or the first historical-association sanitization implementation.

### Relationship

Observed files:

```text
Full/Terminology/sct2_Relationship_Full_INT_20260401.txt
Snapshot/Terminology/sct2_Relationship_Snapshot_INT_20260401.txt
```

Header:

```text
id effectiveTime active moduleId sourceId destinationId relationshipGroup typeId characteristicTypeId modifierId
```

Use for inferred relationship data. For hierarchy/ancestor support, use active `is-a` rows:

```text
typeId = 116680003
sourceId = child concept
destinationId = parent concept
```

For `Full`, reconstruct latest rows per relationship `id` before filtering to `active == 1` and `typeId == 116680003`.

### StatedRelationship

Observed files:

```text
Full/Terminology/sct2_StatedRelationship_Full_INT_20260401.txt
Snapshot/Terminology/sct2_StatedRelationship_Snapshot_INT_20260401.txt
```

Header matches the regular relationship file:

```text
id effectiveTime active moduleId sourceId destinationId relationshipGroup typeId characteristicTypeId modifierId
```

Use for stated relationships. For this project’s current hierarchy fallback design, the regular `Relationship` file is the preferred source for inferred parent hierarchy.

### RelationshipConcreteValues

Observed files:

```text
Full/Terminology/sct2_RelationshipConcreteValues_Full_INT_20260401.txt
Snapshot/Terminology/sct2_RelationshipConcreteValues_Snapshot_INT_20260401.txt
```

Header:

```text
id effectiveTime active moduleId sourceId value relationshipGroup typeId characteristicTypeId modifierId
```

Use for concrete-valued relationships such as numeric attribute values. Not required for concept hierarchy or historical association replacement.

### OWLExpression

Observed files:

```text
Full/Terminology/sct2_sRefset_OWLExpressionFull_INT_20260401.txt
Snapshot/Terminology/sct2_sRefset_OWLExpressionSnapshot_INT_20260401.txt
```

Header:

```text
id effectiveTime active moduleId refsetId referencedComponentId owlExpression
```

Use for OWL axioms. Not required for the first HDF5 ingestion/sanitization implementation unless more complete logical modelling is needed later.

### Identifier

Observed files:

```text
Full/Terminology/sct2_Identifier_Full_INT_20260401.txt
Snapshot/Terminology/sct2_Identifier_Snapshot_INT_20260401.txt
```

Header:

```text
alternateIdentifier effectiveTime active moduleId identifierSchemeId referencedComponentId
```

The inspected samples contained only the header. This file is not required for the proposed whitelist/blacklist or historical-association workflow.

## Refset/Content files

### Association refset

Observed files:

```text
Full/Refset/Content/der2_cRefset_AssociationFull_INT_20260401.txt
Snapshot/Refset/Content/der2_cRefset_AssociationSnapshot_INT_20260401.txt
```

Header:

```text
id effectiveTime active moduleId refsetId referencedComponentId targetComponentId
```

Use for historical association replacement candidates:

```text
source_code = referencedComponentId
target_code = targetComponentId
association_type = decoded refsetId
```

The first sampled rows include known association refsets such as:

```text
900000000000527005 = SAME_AS
900000000000526001 = REPLACED_BY
```

This confirms that the revised sanitization design can derive historical replacement suggestions from the International RF2 package.

### AttributeValue refset

Observed files:

```text
Full/Refset/Content/der2_cRefset_AttributeValueFull_INT_20260401.txt
Snapshot/Refset/Content/der2_cRefset_AttributeValueSnapshot_INT_20260401.txt
```

Header:

```text
id effectiveTime active moduleId refsetId referencedComponentId valueId
```

Use for attribute values attached to components. This can be useful for concept inactivation indicators and other metadata, but is not strictly required for the first replacement implementation if association rows alone are sufficient.

### Simple refset

Observed files:

```text
Full/Refset/Content/der2_Refset_SimpleFull_INT_20260401.txt
Snapshot/Refset/Content/der2_Refset_SimpleSnapshot_INT_20260401.txt
```

Header:

```text
id effectiveTime active moduleId refsetId referencedComponentId
```

Use for simple membership reference sets. Not required for the current critical-document checking workflow unless future list policies are derived from RF2 refset membership.

## Refset/Language files

Observed files:

```text
Full/Refset/Language/der2_cRefset_LanguageFull-en_INT_20260401.txt
Snapshot/Refset/Language/der2_cRefset_LanguageSnapshot-en_INT_20260401.txt
```

Header:

```text
id effectiveTime active moduleId refsetId referencedComponentId acceptabilityId
```

Use for preferred/acceptable terms in language dialects. The package metadata lists GB and US English language refsets. For FSN-only ingestion, this can be skipped; for preferred synonym display or search, it should be used.

## Refset/Map files

### ExtendedMap

Observed files:

```text
Full/Refset/Map/der2_iisssccRefset_ExtendedMapFull_INT_20260401.txt
Snapshot/Refset/Map/der2_iisssccRefset_ExtendedMapSnapshot_INT_20260401.txt
```

Header:

```text
id effectiveTime active moduleId refsetId referencedComponentId mapGroup mapPriority mapRule mapAdvice mapTarget correlationId mapCategoryId
```

Use for maps from SNOMED CT concepts to external classifications such as ICD. Not required for whitelist/blacklist or historical-association sanitization.

### SimpleMap

Observed files:

```text
Full/Refset/Map/der2_sRefset_SimpleMapFull_INT_20260401.txt
Snapshot/Refset/Map/der2_sRefset_SimpleMapSnapshot_INT_20260401.txt
```

Header:

```text
id effectiveTime active moduleId refsetId referencedComponentId mapTarget
```

Use for simple external maps. Not required for the proposed sanitization feature.

## Refset/Metadata files

Observed metadata files include:

```text
der2_cciRefset_RefsetDescriptor*_INT_20260401.txt
der2_ssRefset_ModuleDependency*_INT_20260401.txt
der2_ssccRefset_MRCMAttributeRange*_INT_20260401.txt
der2_cRefset_MRCMModuleScope*_INT_20260401.txt
der2_sssssssRefset_MRCMDomain*_INT_20260401.txt
der2_scsRefset_ComponentAnnotationStringValue*_INT_20260401.txt
der2_cissccRefset_MRCMAttributeDomain*_INT_20260401.txt
der2_ciRefset_DescriptionType*_INT_20260401.txt
der2_sscsRefset_MemberAnnotationStringValue*_INT_20260401.txt
```

These support RF2 metadata, module dependency information, MRCM constraints, annotation strings, and description type metadata. They are useful for validation or advanced tooling, but are not required for the first HDF5 ingestion needed by the revised sanitization design.

## Feasibility assessment for the revised designs

The ideas in `docs/sanitization-revised-design.md` and `docs/rf2-to-hdf5-ingestion-design.md` are feasible with this ZIP.

Confirmed required inputs:

| Needed for design | Observed file(s) | Feasible |
|---|---|---:|
| Target concept active state | `sct2_Concept_*` | yes |
| FSNs / semantic tags | `sct2_Description_*-en_*` with FSN `typeId` | yes |
| Historical associations | `der2_cRefset_Association*` | yes |
| Optional ancestor hierarchy | `sct2_Relationship_*` active `is-a` rows | yes |
| Language acceptability | `der2_cRefset_Language*-en_*` | yes, English only |

Important implementation caveats:

1. `Snapshot` rows represent the package release state but may include inactive rows. Always filter `active == 1` where active-only data is required.
2. `Full` rows must be reconstructed by latest row per component/member id at or before the target date before active filtering.
3. The International Edition ZIP observed here provides English terms/language refsets. German terms require a German extension release package.
4. Ingestion should ignore `__MACOSX` and `.DS_Store` entries.
5. The package has `Full` and `Snapshot` views but no observed `Delta` view.

## Conformance to general SNOMED RF2 structure

The ZIP conforms to the expected SNOMED CT RF2 International Edition release structure:

- tab-delimited RF2 text files;
- first row as column header for RF2 data files;
- terminology and refset separation;
- Full and Snapshot release views;
- concept, description, relationship, language, association, map, and metadata files;
- effective time and active columns for versioned RF2 components/members.

The extra macOS metadata entries are packaging noise and should be ignored by tooling.
