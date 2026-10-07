---
type: Data Format
title: Annotation layer requirements for SNOMED sanitization
description: Required and configurable shape of INCEpTION/UIMA annotation layers that can be checked and sanitized as SNOMED CT annotations.
resource: /src/snomed_post_processing/uima_processing/extraction.py
status: stable
tags: [data-format, inception, uima, cas, annotation-layer, snomed, sanitization]
generated: { by: pi-coding-agent/gpt-5.5, at: 2026-09-10T00:00:00Z }
sources:
  - id: extraction
    resource: /src/snomed_post_processing/uima_processing/extraction.py
    title: Annotation extraction
  - id: project-processing
    resource: /src/snomed_post_processing/uima_processing/project.py
    title: INCEpTION project processing
  - id: policy-check
    resource: /src/snomed_post_processing/pipelines/document_logging.py
    title: Critical-finding logging pipeline
  - id: writeback
    resource: /src/snomed_post_processing/pipelines/sanitization_run.py
    title: Reviewed decision write-back
---

# Purpose

This page describes how an INCEpTION/UIMA annotation layer must expose SNOMED CT IDs to be usable by the policy-check and sanitization workflows.

# Minimal target-layer requirements

A checkable SNOMED annotation layer must be a UIMA span annotation layer with:

| Requirement | Meaning |
|---|---|
| Layer/type name | The fully qualified UIMA type name, e.g. `gemtex.Concept` or `webanno.custom.Concept`. |
| Begin/end offsets | Normal UIMA annotation offsets are used to preserve span provenance and match reviewed decisions. |
| Covered text | Derived from the CAS span; stored in findings/decisions for review and conservative matching. |
| ID feature | A string feature containing either a plain SCTID or a prefixed SCTID URI/string. |

The ID feature defaults to:

```text
id
```

The ID prefix defaults to:

```text
http://snomed.info/id/
```

With these defaults, the feature value is expected to look like:

```text
http://snomed.info/id/<SCTID>
```

# Configurable fields

The following are user-facing configuration points:

| Setting | CLI option | GUI location | Default |
|---|---|---|---|
| Target annotation layer(s) | `--annotation-type` | Sidebar → Annotation layers | `gemtex.Concept`, `webanno.custom.Concept` in current GUI/CLI defaults |
| SNOMED ID feature name | `--id-feature` | Sidebar → Annotation layers | `id` |
| SNOMED ID prefix | `--id-prefix` | Sidebar → Annotation layers | `http://snomed.info/id/` |
| Ignore-overlap layer(s) | `--ignore-overlap-type` | Sidebar → Annotation layers | `webanno.custom.No_Human` |
| Ignore-overlap matching mode | `--ignore-overlap-mode` | Sidebar → Annotation layers | `overlap` |

Use an empty ID prefix when the configured feature stores plain SCTIDs:

```bash
uv run log-critical-documents \
  --annotation-type webanno.custom.MyConcept \
  --id-feature snomedId \
  --id-prefix "" \
  --lists-path concepts.hdf5 \
  project.zip
```

# Extraction behavior

For each configured target annotation layer, the checker:

1. selects annotations of that UIMA type;
2. reads the configured ID feature;
3. strips the configured prefix when present;
4. lowercases and trims the value;
5. treats empty, `null`, `none`, and `nan` values as missing;
6. records SCTID, layer, offsets, covered text, document, annotator/view, and ignore-overlap state.

Policy checks are exact SCTID checks against the selected HDF5 policy/release view.

# Write-back behavior

Reviewed sanitization decisions are matched conservatively by document, annotator/view, layer, span offsets, source SCTID, and optionally covered text.

When a replacement is applied, the configured ID feature is updated. If the current value uses the configured prefix, the replacement is written with that prefix. If the configured prefix is empty, or the current value is plain, the replacement is written as a plain SCTID.

# Manual-review layer

Rows marked for manual editing do not change the original SNOMED annotation. Instead, write-back adds a manual-review marker layer, by default:

```text
webanno.custom.ManualReview
```

The manual-review layer carries these string features:

```text
source_code
suggestion_status
suggested_replacement
review_note
```

# Current limitations

- The ID feature is assumed to be a string-like scalar feature.
- Multi-feature concept encodings are not currently supported.
- Non-SCTID identifiers must be normalized before policy checking.
- The target layer must be readable from JSONCAS or XMI; Java serialized CAS (`.ser`) is not editable by this Python workflow.

# Related concepts

- [Critical-finding logging](/snomed-post-processing/workflows/critical-finding-logging.md)
- [Reviewed decisions and write-back](/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md)
- [INCEpTION CAS and ZIP](inception-cas-and-zip.md)
- [JSON artifact formats](json-artifact-formats.md)
