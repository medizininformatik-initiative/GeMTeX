---
type: GUI Surface
title: Streamlit GUI
description: Browser UI structure and behavior for policy, check, suggestion review/apply, and INCEpTION deployment.
resource: /src/snomed_post_processing/gui
tags: [gui, streamlit, review, deployment]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: gui-source
    resource: /src/snomed_post_processing/gui
    title: GUI source package
  - id: deployment-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/inception-sanitized-deployment-workflow.md
    title: Deploying sanitized documents back to INCEpTION
  - id: release-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/release-view-normalization-and-blacklist-metadata.md
    title: Release-view normalization and blacklist metadata
---

# UI purpose

The Streamlit GUI wraps the same pipeline functions as the CLI. It is intended for browser-based policy creation, critical finding checks, suggestion generation, review decisions, local ZIP sanitization, and the one-step sanitized INCEpTION deployment workflow.

# Important source files

| File | Role |
|---|---|
| `/src/snomed_post_processing/gui/app.py` | Main Streamlit page setup and tab orchestration. |
| `/src/snomed_post_processing/gui/sidebar.py` | Shared input/sidebar controls, target-view selection, blacklist mode selection, INCEpTION API controls. |
| `/src/snomed_post_processing/gui/file_sources.py` | Shared file selector supporting Upload, Data directory, and Server path. |
| `/src/snomed_post_processing/gui/policy_tab.py` | Policy checks, persistent findings tables, and report downloads. |
| `/src/snomed_post_processing/gui/sanitization_check_tab.py` | Suggestion generation UI and settings metadata. |
| `/src/snomed_post_processing/gui/concept_rules.py` | Explicit concept-rule form, one-step application to review, and rule-decision review/clearing. |
| `/src/snomed_post_processing/gui/sanitization_run_tab.py` | Review/apply UI and INCEpTION deployment form. |
| `/src/snomed_post_processing/gui/downloads.py` | Markdown/JSON download helpers. |

# Contextual help

Use short widget tooltips for parameter meaning, scope and consequences; table-column help explains editable rule/review fields. Obvious labels do not need redundant tooltips. Keep essential safety notes visible: decisions are staged until export/upload, BM25 thresholds are unvalidated heuristics, and exclusion-list source findings remain manual. Longer mathematical explanations belong beside the D/M controls rather than in repeated captions.

Help covers ancestor-distance units, lexical token overlap, saved candidate limits, rule actions/overrides, review saving, file locations and deployment controls. Historical relationship descriptions appear in both generation and automatic-condition dropdowns. BM25 acceptance needs at least three distinct comparable saved targets; retrieval limits affect this condition.

The sidebar's **Replacement requirements → Allowed replacement concepts** selector and main banner describe which replacement suggestions are allowed: **Policy rules** requires active concepts in the loaded HDF5 inclusion list and outside its exclusion list; **Active release** allows any active release concept, with exclusions only when enabled in the sidebar. A shared caption states that tab 1's policy check is unaffected and explicit concept rules may override list restrictions. Date/snapshot details stay in the HDF5 metadata section. Tab 1 remains **Check policy** in both modes. Report-download help distinguishes CriticalFindings JSON, report JSON, suggestions JSON and reviewed decisions. Masked Markdown hides document/annotator names, **not clinical text**, and is not full anonymization.

Deployment tooltips distinguish local preparation from remote writes, disclose that connection checks contact INCEpTION during dry-run, warn that disabling TLS verification weakens security, and clarify that temporary-output overwrite is not a remote-project overwrite setting. Shell ZIP, repaired CAS artifacts and pipeline-report downloads have separate explanations. These are presentation-only changes; processing defaults and behavior remain unchanged.

# File source pattern

The GUI should use the shared file-source selector for large/server-side files:

```text
Upload
Data directory
Server path
```

This pattern applies to INCEpTION ZIPs, HDF5 files, CriticalFindings JSON, processed SNOGIT caches, SNOGIT ZIP/`.dat` sources, and custom blacklist rule files.

When the GUI creates a processed SNOGIT cache, it writes the HDF5 to a persistent subdirectory under the configured data directory when possible:

```text
<data-dir>/generated-snogit-caches/snogit_cache_<timestamp>.hdf5
```

If the data directory is unavailable, it falls back to a temporary directory. Suggestion generation prefers this selected/created server-side cache path over stale uploaded-file objects after download-button reruns.

# Policy terminology

User-facing labels and messages use **inclusion list** / **exclusion list** across the sidebar, check results, suggestion settings, review status, and metadata display. CLI help, console messages, and generated Markdown reports use the same wording.

This is a presentation change only: Python names, CLI flags, HDF5 paths, and JSON identifiers retain `whitelist`/`blacklist` where established. Actual storage paths shown in metadata are explicitly identified as HDF5 paths. Existing artifacts do not need migration; original clinical text and FSNs are not rewritten.

# Policy-check results

The policy-check tab displays the last successful check from `st.session_state["policy_check_result"]` on every rerun. Filtering or downloading does not rerun the check. Results persist within the current session, not across server restarts; changed project/HDF5 inputs require an explicit new check. A caption identifies results as the last successful check.

The MIE/audit findings display is grouped by document and annotator, with rows sorted initially by span offset. Each table shows SCTID, FSN, covered text, critical/ignored status, inclusion-/exclusion-list check, and annotation layer. Tables support Streamlit's interactive column sorting.

Summary metrics cover critical and ignored findings, inclusion-/exclusion-list findings, affected documents, and affected annotators. These metrics describe the complete result. Document/annotator group counts describe the filtered rows.

Filters support status, check type, SCTID substring, and case-insensitive covered-text substring. Clear all filters restores the full display. Filters never modify the stored findings or exported reports. Empty findings and empty filtered results have explicit messages.

CriticalFindings JSON, Markdown, masked Markdown, and report JSON downloads remain available. The table replaces the inline Markdown report preview, not the Markdown exports. The existing `critical_findings`, `critical_findings_json_text`, and `critical_findings_json_name` session fields remain populated for sanitization.

# Annotation ID feature and prefix

The sidebar annotation-layer settings include the configurable SNOMED ID feature name and prefix. The feature defaults to `id`; the prefix defaults to `http://snomed.info/id/`. Use an empty prefix for layers that store plain SCTIDs. The same feature/prefix settings are used when matching reviewed decisions and writing replacement IDs. See [Annotation layer requirements](/snomed-post-processing/data/annotation-layer-requirements.md).

# Replacement choice safety

Suggestion generation puts selectable replacements in `candidates` and rejected targets in `context_candidates`. Review offers only replacement candidates, not diagnostic context. Overview/report displays label diagnostics **Diagnostic candidates (not selectable)**.

**Active release** keeps optional exclusion-list enforcement, following the sidebar settings. Policy mode remains strict; explicit concept rules retain their existing **Override policy** behavior. Regenerate suggestions after changing target settings. No additional HDF5 revalidation is performed during generic review/export.

# Concept rules

The **Suggest policy sanitization** tab includes a **Concept rules** form in a collapsed-by-default expander above fallback settings. It defaults to Number `410680006` → remove ID only, and Date `410671006` → Date property `410672004`. Rules and per-rule **Override policy** are enabled by default. The form supports dynamic rows and separate rule JSON import/export. It uses the sidebar's target annotation layers across all documents and annotators; there are no separate rule-scope input boxes.

Column-header tooltips explain **Enabled**, **Name**, and the rule fields. **Override policy** is permission to bypass list restrictions, not permission to replace existing review decisions or bypass target existence/activity checks; it has no effect for **Remove ID only**. This distinction also appears as a visible note below configuration. In tab 3, **Override policy** and **Policy actually overridden** are read-only columns with tooltips distinguishing permission from an exception actually needed for that replacement. **Apply** stages an action for later export/upload; changing it does not immediately modify the project.

Use the single **Apply rules to review** button to save/validate the configuration, scan matching annotations, and select decisions in Review & apply. A summary reports ID removals, replacements, actual policy overrides, and manual conflicts. JSON uploads load configuration automatically without applying it; **Download concept rules JSON** remains separate. There are no Save, Preview, Load, or separate acceptance buttons in the rules form. All matching original annotations are considered, not just policy findings. `literal` is always preserved. Replacements require an existing active target even when overriding policy.

**Clear all pending rule decisions** is always visible with **Apply rules to review** in tab 2's **Concept rules** expander, disabled when no pending rule decisions exist. Clear removes all pending decisions, including saved Apply-checkbox choices, without changing rule definitions or CAS files. Reapplying rules preserves saved checkbox choices. There is no separate Undo button or application-history snapshot. **Review & apply** (tab 3) shows only the resulting rule-decision editor and its Save action, not the rule-management buttons. Existing manual decisions are protected; stale inputs or conflicts block export. Rule-only reviews are supported without generating generic suggestions. The ordinary Run sanitization / deployment controls perform the actual write-back. See [rule semantics and write-back](/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md).

# Review and apply behavior

The review UI distinguishes **single/no-choice** replacement suggestions from rows that need an explicit manual candidate choice. “Single/no-choice” does not mean accepted. Global and per-document bulk apply/clear buttons are replaced by an **Automatic conditions** form in tab 3 with **Apply Conditions** and **Undo Automatic Conditions**.

The historical condition selects a replacement only for an inclusion-list source finding (`list_type == "whitelist"`) whose chosen historical relationship types yield exactly one distinct selectable target. Defaults: `SAME_AS`, `REPLACED_BY`, `WAS_A`, `ALTERNATIVE`, `SIMILAR_TO`. Several relationships to the same code count as one target; multiple target codes remain manual. The condition reads individual candidate relationships, not a combined summary string.

An optional **Enable BM25 automatic selection (heuristic)** checkbox adds a second condition, combined with historical acceptance using **OR**. It defaults off. Threshold controls default to `D >= 2/3` and `M >= 0.20`, where `D = first_gap / (first_gap + largest_later_gap)` and `M = first_gap / top_score`. All saved candidates are sorted and deduplicated by target code (best score), with at least three distinct targets required. Every later adjacent gap participates, not just the gap between ranks 2 and 3. The collapsed **BM25 score-gap assessment** table shows candidate count, scores, metrics and reasons before manual-choice protection. Thresholds are unvalidated heuristics, not clinical confidence.

Exclusion-list source findings, annotations also reported by the exclusion-list check, duplicate annotation identities, ignored findings, and ancestor suggestions remain manual. BM25 with fewer than three targets, tied first place, invalid scores, unknown/mixed FSN/SNOGIT channels or differing index members also stays manual. A SNOGIT channel needs a known member. Pure comparable channels may qualify only when BM25 selection is explicitly enabled. Existing manual actions, saved keep choices, restored non-automatic decisions, and explicit concept-rule decisions are protected. Target eligibility comes from suggestion generation; Active-release optional exclusions are unchanged and no extra HDF5 validation layer is added.

Automatically selected decisions carry `automatic_condition` provenance and `resolved=true`. A document is marked reviewed only when its remaining decisions are resolved and no exclusion-list/open/manual-edit case prevents completion. Undo restores the last changed run's choices and newly set document-review flags, skipping later manual changes. Repeated identical Apply clicks do not replace the previous undo snapshot. Changing suggestions clears automatic selections/progress and stale undo history; loading reviewed decisions preserves provenance but does not restore undo history. Both actions change review state only, never CAS files. Conditions add/update matching choices; changing thresholds or disabling a condition does not silently clear earlier selections. Use Undo to reverse the last changed run. Candidate count refers to the saved suggestion set; increase retrieval count and regenerate if fewer than three distinct BM25 targets were saved. Empirical calibration remains outstanding.

The review UI supports these reviewed actions:

```text
replace
delete
keep unchanged
needs manual edit marker
```

No selection means keep unchanged. Action precedence in write-back is:

```text
manual_edit > delete > apply > keep unchanged
```

# INCEpTION deployment UI

The one-step deployment workflow is exposed under:

```text
3. Review & apply → Apply decisions and upload to INCEpTION
```

The deployment settings live inside a Streamlit form. The submit button uses the stable label:

```text
Run INCEpTION deployment pipeline
```

This matters because checkbox changes inside a form do not trigger reruns, so labels should not depend dynamically on form-internal values.

GUI deployment supports:

- dry-run/offline preparation by default;
- optional connection check;
- explicit remote apply checkbox;
- project name/slug/description;
- INCEpTION URL, username, password;
- annotation user;
- downloads for shell ZIP, repaired upload artifacts ZIP, and pipeline report JSON.

The legacy GUI action `Run sanitization` still only creates a local sanitized project ZIP and download; it does not build/deploy INCEpTION artifacts.

# Related concepts

- [Reviewed decisions and write-back](/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md)
- [One-step INCEpTION deployment](/snomed-post-processing/workflows/inception-deployment.md)
- [CLI commands](/snomed-post-processing/interfaces/cli.md)
