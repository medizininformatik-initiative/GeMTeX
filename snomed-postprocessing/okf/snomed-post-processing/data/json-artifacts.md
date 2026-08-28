---
type: Data Format
title: JSON artifacts
description: Structured JSON artifacts exchanged between checking, suggestion, review, apply, artifact generation, and deployment workflows.
resource: /src/snomed_post_processing
tags: [data-format, json, critical-findings, decisions, reports]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: findings-code
    resource: /src/snomed_post_processing/findings_io/json_io.py
    title: CriticalFindings JSON IO
  - id: suggestion-code
    resource: /src/snomed_post_processing/sanitization/json_io.py
    title: Sanitization suggestion JSON IO
  - id: decisions-code
    resource: /src/snomed_post_processing/sanitization/decisions_json.py
    title: Sanitization decisions JSON IO
  - id: deployment-code
    resource: /src/snomed_post_processing/pipelines/inception_apply_upload.py
    title: Deployment report writer
---

# CriticalFindings JSON

Produced by logging/check workflows and consumed by `suggest-sanitization`.

Each finding records:

```text
annotator
document
code
covered_text
offset
list_type
reason
layer
fsn
ignored
ignore_overlaps
```

`list_type` distinguishes whitelist findings from blacklist findings. Ignored findings are informational and are not sanitized automatically.

# SanitizationSuggestions JSON/Markdown

Suggestion generation writes human-readable Markdown and can write structured JSON for the review UI. Suggestions preserve the original finding plus status, replacement code/FSN, association type, candidate count, and candidates/context.

Candidate records may represent historical/ancestor candidates or semantic BM25 candidates. BM25 candidates can include evidence fields such as `source`, `matched_term`, `source_member`, and `matched_query_tokens`.

Suggestion JSON metadata records relevant generation settings, including target view and blacklist settings when generated through GUI/pipeline paths.

# Reviewed decisions JSON

Reviewed decisions use schema:

```text
snomed-post-processing.sanitization-decisions
```

Supported action semantics:

```text
replace
delete
keep unchanged
manual_edit
```

Older boolean-compatible fields are also recognized by the apply layer:

- `apply` with `valid_choice` and `replacement_code` means replacement;
- `delete_annotation` means delete;
- `manual_edit` means manual-review marker.

Decisions should be applied to the original project ZIP. Applying decisions to an already sanitized ZIP can cause double-application or duplicate markers.

# Upload artifact report

`build-inception-upload-artifacts` writes:

```text
inception-upload-artifacts-report.json
```

Key fields:

```text
mode = flattened-documents
source_project
output_dir
artifact_count
uploads[]
unmatched_decisions
skipped_decisions
```

Each upload includes source member, source document, source annotator, remote document name, output path, format, decision counts, changed annotation count, and remote-upload compatibility fields.

# Deployment report

`deploy-inception-sanitized-project` writes:

```text
inception-sanitized-deployment-report.json
```

It includes dry-run/applied state, shell/artifacts paths, planned upload count, planned remote documents, upload results, imported project ID/name after apply, warnings, and errors.

# One-step pipeline report

`apply-decisions-to-inception` writes:

```text
inception-apply-decisions-upload-report.json
```

It summarizes the whole pipeline: source project, decisions path, shell ZIP, artifact directory/report, deployment report, decision counts, artifact counts, remote-upload repair counts, compatibility issue counts, dry-run/applied state, deployment warning/error counts, and decisions metadata.

# Related concepts

- [Reviewed decisions and write-back](/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md)
- [INCEpTION deployment](/snomed-post-processing/workflows/inception-deployment.md)
