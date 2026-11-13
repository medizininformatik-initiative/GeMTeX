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

# Annotator scope

The GUI's tab-1 annotator selection governs all checks, suggestions, rules, review and exports. Saved findings/suggestions/decisions record `metadata.annotators`; imported records are filtered against current scope. Narrower-source artifacts cannot silently cover a broadened scope. Review keeps original suggestion indices after filtering, and excluded selections/automatic Undo/review progress are invalidated on scope changes. Different regenerated/loaded suggestions reset generic choices with a notice, preventing old index-based selections from targeting another annotation.

Local ZIP write-back receives the annotator filter and leaves excluded CAS contents unchanged. Deployment filters both decisions and CAS extraction, so excluded annotators are not uploaded merely because their unchanged CAS is present in the source ZIP. Standalone deployment/artifact creation honors saved decision scope unless explicitly overridden by the caller. With no scope restriction, default behavior remains all annotators.

# Explicit concept rules

The reusable engine is `sanitization/concept_rules.py`. The GUI form is above fallback settings in **Suggest policy sanitization**:

- Number `410680006`: `clear_id`.
- Date `410671006`: replace with Date property `410672004`.
- Both rules are enabled initially; per-rule `override_policy` defaults to true, including new rows.

The form can add/edit/disable/remove rules and download/load separate concept-rules JSON (`snomed-post-processing.concept-rules`, version 1). The collapsible form uses the sidebar's target annotation layers and covers all documents within the shared annotator selection from tab 1 (empty = all); there are no separate rule-scope input boxes. Older saved scope filters are not reused for new GUI rule applications. It scans original JSONCAS/XMI annotations directly, including annotations absent from policy findings. It does not alter source CAS files or chain rules.

Workflow: **Apply rules to review → review/save choices → explicit export/upload**. The single submit saves and validates rules, scans the original annotations, and selects rule decisions without a separate preview/accept step. A summary shows ID removals, replacements, actual policy overrides, and manual conflicts. JSON uploads automatically load configuration once per file content, without applying decisions; download remains a separate button. Applying rules to review or rerunning Streamlit does not write CAS files. The review works without generic suggestions. Rule decisions reserve their annotation identities, so generic fallback choices cannot replace them. The inherited annotation-layer selection is shared by all rules. The engine API still supports document/annotator filters for programmatic callers.

`override_policy=true` permits targets outside the inclusion list or on the exclusion list; replacement targets must still exist and be active. With override off, selected target-view validity gates apply. `clear_id` has no target membership requirement. Provenance distinguishes override permission from `policy_overridden`, an actual bypass. GUI tooltips in both configuration and review explain this distinction and clarify that override does not replace existing review decisions. A visible configuration note states the same boundary. In review, permission and actual-use columns are read-only; only Apply stages an action for export/upload. Loaded rule decisions are checked for rule/action consistency and revalidated against the selected HDF5 before GUI export.

Review decisions carry the rule snapshot and actual override flag; decisions metadata carries rule definitions, scope, and reviewed-document state. No existing JSON identifiers are renamed or artifacts migrated. Rule-only documents are included in reviewed metadata only when all their decisions are selected.

Input/configuration changes block stale decisions. Conflicting manual decisions (including explicitly reviewed keep choices) block export until resolved. Reapplying rules preserves saved manual Apply-checkbox choices. **Clear all pending rule decisions** explicitly removes all pending rule decisions, including those choices, without reverting rule definitions or changing CAS files. Clear lives beside rule configuration/application in tab 2's **Concept rules** expander, with no separate Undo button or application-history snapshot; tab 3 retains only the resulting decisions and their review/save controls. The later association/BM25 condition form remains separate.

Only the configured ID feature changes for rule actions: `literal`, other features, annotation count, type, and offsets are preserved in JSONCAS/XMI and offline upload-artifact tests. Live INCEpTION reimport is a separate validation step requiring approval.

# Automatic review conditions

`sanitization/conditions.py` plans conditional selections and one-run undo; `gui/sanitization_run_tab.py` integrates the review widgets. No CAS or HDF5 files are changed by these actions.

**Apply Conditions** considers only inclusion-list source findings (`list_type == "whitelist"`). A second exclusion-list finding for the same annotation blocks automatic selection. Duplicate source identities and ignored findings also stay manual. Only generated selectable historical candidates are considered, never `context_candidates`; the selected individual association types must yield exactly one distinct target code. The defaults are `SAME_AS`, `REPLACED_BY`, `WAS_A`, `ALTERNATIVE`, and `SIMILAR_TO`. Ancestor suggestions remain manual. An opt-in BM25 condition combines with historical selection using OR. With at least three distinct targets, `D = first_gap / (first_gap + max(all later adjacent gaps))` and `M = first_gap / top_score` must both pass configurable thresholds (initially `2/3` and `0.20`). Scores are sorted and deduplicated by target code using its best score. Tied first place, invalid scores, mixed/unknown source channels, differing members, or unknown SNOGIT members prevent automatic acceptance. All saved candidates are evaluated, never just the visible rows or diagnostic context. These thresholds remain unvalidated heuristics. Existing target-view filtering and optional Active-release exclusions are unchanged.

Existing selected manual replacements, deletions, manual-edit markers, saved/reviewed keep choices, restored non-automatic decisions, and explicit concept rules are protected. Saving a document's review form conservatively protects its decisions from subsequent automation. Condition decisions store `automatic_condition` with the source-check kind and target code plus `resolved=true`. Historical provenance records matching/configured relationship types. BM25 provenance (`kind="bm25_gap"`) records metric version, all distinct ranked codes/scores, candidate count, source/member, gap values, measured D/M and configured thresholds. Reviewed-document flags are set only for completed documents without exclusion-list or unresolved/manual-edit cases.

**Undo Automatic Conditions** restores the last changed run's decision state and newly set reviewed flags, but skips later manual changes. Its snapshot is session-only; identical repeated applications preserve it, while changed suggestions or explicitly loading another reviewed state discard it. Conditions add/update matching choices; stricter settings or disabling a condition do not silently remove previously selected choices. Automatic selections and owned document-review flags are cleared when suggestion content changes. The ordinary JSON decisions export/import preserves automatic provenance and reviewed state (`automatic_reviewed_documents` metadata), not the undo history. Explicitly loading a review state replaces prior local review-progress flags.

# Parallel NiceGUI review increment

NiceGUI now supports explicit selectable replacement/Keep/deletion/manual-edit staging, Save/discard,
document progress flags and version-1 decisions JSON download/restore using the
existing backend reader/writer. Presentation/navigation remain separate. Keep is
non-applying but human-reviewed; confirming a document protects its unchanged rows
from later automation. Pending edits block download. Metadata annotator coverage,
original indices, source identity/text and current selectable membership guard
imports; NiceGUI exports additionally bind full suggestions content by SHA-256.
Manual candidate ordinal/evidence preserves duplicate channels. Right-click Findings
for Accept Suggestion / Delete / Manual Review / Keep Original, or the Selected
finding candidate grid for Apply only. Accept Suggestion uses only a unique selectable
match for the saved proposed SCTID; otherwise choose a specific candidate and Apply.
Delete stages annotation removal, and Manual Review stages a later ManualReview
marker without resolving the finding. Opening a menu never stages. The separate
Keep original button is removed. Local saved actions can be changed or reset with
the Keep Original menu item; imported protected
actions remain read-only. No context-menu command itself writes CAS.

Imports replace review atomically, preserve existing provenance, and cannot
supersede newer uploads, demo reset or manual edits. Imported rule/deletion/manual-
edit/ID-removal actions are retained read-only, not revalidated against HDF5;
rule/manual conflicts fail rather than overwriting protected work. No CAS write-back,
conditions, rule application or deployment is connected in NiceGUI. JSON downloads
may contain clinical data and are the only application-level persisted review;
reload otherwise loses page state. See the GUI interface OKF for tests/limits.

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
