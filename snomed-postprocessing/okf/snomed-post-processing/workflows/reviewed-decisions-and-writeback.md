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
| `clear_id` with `apply=true`, `valid_choice=true`, and no replacement code | Set only the matching annotation ID feature to `None` (unset/null); keep the annotation and every other feature, including `literal`. |
| `delete` / `delete_annotation` | Remove the matching CAS annotation. |
| `manual_edit` / `manual_edit=true` | Keep original annotation and add a `ManualReview` marker. |
| no selection / skipped / no apply | Leave annotation unchanged. |

Precedence during application:

```text
manual_edit > delete > clear_id / replacement apply > keep unchanged
```

# Explicit concept rules

The reusable engine is `sanitization/concept_rules.py`. The GUI form is above fallback settings in **Suggest policy sanitization**:

- Number `410680006`: `clear_id`.
- Date `410671006`: replace with Date property `410672004`.
- Both rules are enabled initially; per-rule `override_policy` defaults to true, including new rows.

The form can add/edit/disable/remove rules and download/load separate concept-rules JSON (`snomed-post-processing.concept-rules`, version 1). The collapsible form uses the sidebar's target annotation layers and covers all documents and annotators; there are no separate rule-scope input boxes. Older saved scope filters are not reused for new GUI rule applications. It scans original JSONCAS/XMI annotations directly, including annotations absent from policy findings. It does not alter source CAS files or chain rules.

Workflow: **Apply rules to review → review/save choices → explicit export/upload**. The single submit saves and validates rules, scans the original annotations, and selects rule decisions without a separate preview/accept step. A summary shows ID removals, replacements, actual policy overrides, and manual conflicts. JSON uploads automatically load configuration once per file content, without applying decisions; download remains a separate button. Applying rules to review or rerunning Streamlit does not write CAS files. The review works without generic suggestions. Rule decisions reserve their annotation identities, so generic fallback choices cannot replace them. The inherited annotation-layer selection is shared by all rules. The engine API still supports document/annotator filters for programmatic callers.

`override_policy=true` permits targets outside the inclusion list or on the exclusion list; replacement targets must still exist and be active. With override off, selected target-view validity gates apply. `clear_id` has no target membership requirement. Provenance distinguishes override permission from `policy_overridden`, an actual bypass. Loaded rule decisions are checked for rule/action consistency and revalidated against the selected HDF5 before GUI export.

Review decisions carry the rule snapshot and actual override flag; decisions metadata carries rule definitions, scope, and reviewed-document state. No existing JSON identifiers are renamed or artifacts migrated. Rule-only documents are included in reviewed metadata only when all their decisions are selected.

Input/configuration changes block stale decisions. Conflicting manual decisions (including explicitly reviewed keep choices) block export until resolved. Reapplying rules preserves saved manual Apply-checkbox choices. **Clear all pending rule decisions** explicitly removes all pending rule decisions, including those choices, without reverting rule definitions or changing CAS files. Clear lives beside rule configuration/application in tab 2's **Concept rules** expander, with no separate Undo button or application-history snapshot; tab 3 retains only the resulting decisions and their review/save controls. The later association/BM25 condition form remains separate.

Only the configured ID feature changes for rule actions: `literal`, other features, annotation count, type, and offsets are preserved in JSONCAS/XMI and offline upload-artifact tests. Live INCEpTION reimport is a separate validation step requiring approval.

# Matching semantics

Decisions are matched conservatively by document, annotator, annotation layer, span/offset, source code, and optionally covered text. A decision that cannot be matched is reported as unmatched. Matching is planned against original IDs before modifications, preventing accidental chaining. Ambiguous concept-rule matches and multiple decisions targeting one annotation are rejected.

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
