---
type: Architecture Decision Record
title: Design decisions and invariants
description: Consolidated current decisions governing SNOMED policy checking, sanitization, release view, BM25, and INCEpTION deployment.
resource: /src/snomed_post_processing
tags: [decisions, invariants, architecture]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: docs-folder
    resource: /snomed-post-processing/source-docs/index.md
    title: Migrated original project docs
  - id: source-tree
    resource: /src/snomed_post_processing
    title: Application source tree
---

# Current decisions

- Policy mode is authoritative for the GeMTeX policy workflow: active + whitelist - blacklist.
- Release mode allows all active concepts by default; embedded blacklist is ignored unless explicitly enabled.
- In release-view suggestion generation, users may optionally add a runtime custom blacklist; policy mode instead uses the materialized embedded whitelist/blacklist policy views in the HDF5.
- All suggestion sources use the same selected target-view gates.
- Blacklist findings are not automatically sanitized by default.
- Suggestions are review evidence, not authority.
- BM25 and SNOGIT evidence are fallback/review assistance and cannot bypass HDF5 validity gates.
- Historical associations are tried before ancestor fallback and BM25.
- Ancestor fallback is optional and bounded by absolute and relative distance limits by default.
- Reviewed decisions should be evaluated against the original project ZIP as the source input and written to a separate sanitized ZIP/artifact set; using an already sanitized ZIP as input can cause double-application or duplicate markers.
- The original project ZIP is not modified in place.
- Delete decisions remove matching CAS annotations.
- Manual edit decisions keep the original annotation and add a ManualReview marker (UIMA layer).
- Decision precedence is `manual_edit > delete > apply > keep unchanged`.
- No selection means keep unchanged.
- Sanitized ZIP export excludes `.ser` files.
- Python should not attempt direct `.ser` generation.
- Preferred INCEpTION deployment is schema-shell ZIP import plus remote JSONCAS/XMI upload.
- Flattened documents mode is the first deployment target; preserve-annotators mode is deferred.
- Deployment is dry-run by default and real remote writes require explicit `--apply`.
- Remote-upload-compatible artifacts are persisted by default.
- `INITIAL_CAS.*` and `.ser` members are ignored for upload-artifact generation.
- The ManualReview layer copies Concept behavior/properties where possible but owns only its manual-review features.
- ManualReview features are `source_code`, `suggestion_status`, `suggested_replacement`, and `review_note`; `covered_text` was removed.
- GUI INCEpTION deployment settings are in a Streamlit form with stable submit label `Run INCEpTION deployment pipeline`.

# CAS repair invariants

For remote-upload-compatible artifacts:

```text
Every non-whitespace text region is inside exactly one non-overlapping Sentence span.
Whitespace-only gaps may remain outside sentences.
All visible/editor-relevant project/custom annotation ranges are covered by visible Sentence rows.
CASMetadata is present.
DocumentMetaData is removed.
```

# Superseded design retained as lesson

The older source-HDF5-to-target-HDF5 migration design was superseded by a finding-based workflow. Current sanitization acts only on critical findings produced by policy checking, making the flow narrower, safer, and easier to audit.

# Related concepts

- [Sanitization suggestions](/snomed-post-processing/workflows/sanitization-suggestions.md)
- [Reviewed decisions and write-back](/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md)
- [INCEpTION deployment](/snomed-post-processing/workflows/inception-deployment.md)
- [Imported archived design note](/snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/sanitization-source-target-design-old.md)
