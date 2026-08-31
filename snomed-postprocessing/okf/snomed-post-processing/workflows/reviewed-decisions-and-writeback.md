---
type: Workflow
title: Reviewed decisions and local ZIP write-back
description: How human-reviewed sanitization decisions are represented and applied to copied INCEpTION project ZIPs or CAS bytes.
resource: /src/snomed_post_processing/pipelines/sanitization_run.py
tags: [workflow, decisions, writeback, jsoncas, xmi]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: sanitizer-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/sanitization-revised-design.md
    title: SNOMED sanitization design
  - id: run-code
    resource: /src/snomed_post_processing/pipelines/sanitization_run.py
    title: Sanitization run implementation
---

# Purpose

Reviewed decisions JSON is the bridge between suggestion generation and write-back. Decisions are produced or edited after human review, then evaluated against the original project ZIP as source input and written to a separate sanitized ZIP/artifact set, or applied to in-memory CAS bytes. The original project ZIP is not modified.

# Supported actions

| Action | Effect |
|---|---|
| `replace` / applicable `apply` decision | Replace matching annotation SCTID with reviewed target SCTID. |
| `delete` / `delete_annotation` | Remove the matching CAS annotation. |
| `manual_edit` / `manual_edit=true` | Keep original annotation and add a `ManualReview` marker. |
| no selection / skipped / no apply | Leave annotation unchanged. |

Precedence during application:

```text
manual_edit > delete > apply > keep unchanged
```

# Matching semantics

Decisions are matched conservatively by document, annotator, annotation layer, span/offset, source code, and optionally covered text. A decision that cannot be matched is reported as unmatched.

# Local ZIP write-back

`run_sanitization` creates a separate sanitized project ZIP:

- refuses to use the same input and output path;
- groups decisions by document and annotator;
- loads project metadata and TypeSystem where possible;
- rewrites JSONCAS/XMI members only;
- skips/removes `.ser` members from the sanitized export;
- updates `exportedproject.json` with sanitized labels;
- adds `webanno.custom.ManualReview` to project schema when manual-edit markers are needed.

# In-memory CAS sanitization

`sanitize_cas_bytes` applies the same decision semantics to one JSONCAS or XMI byte payload. This function is reused by INCEpTION upload-artifact generation.

Supported CAS formats:

```text
jsoncas
xmi
```

# ManualReview layer

Default layer:

```text
webanno.custom.ManualReview
```

Current features:

```text
source_code
suggestion_status
suggested_replacement
review_note
```

The layer copies Concept layer behavior/properties where possible but uses its own features. The old `covered_text` feature was removed because span coverage already exposes the covered text.

# Outputs and reports

`SanitizationRunResult` reports:

- output project path;
- total/applied decisions;
- changed annotation count;
- changed member count;
- unmatched decisions;
- skipped decisions.

# Related concepts

- [JSON artifacts](/snomed-post-processing/data/json-artifacts.md)
- [INCEpTION deployment](/snomed-post-processing/workflows/inception-deployment.md)
- [Sanitization suggestions](/snomed-post-processing/workflows/sanitization-suggestions.md)
