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
| `/src/snomed_post_processing/gui/concept_rules.py` | Explicit concept-rule form, one-step application to review, and rule-decision review/undo. |
| `/src/snomed_post_processing/gui/sanitization_run_tab.py` | Review/apply UI and INCEpTION deployment form. |
| `/src/snomed_post_processing/gui/downloads.py` | Markdown/JSON download helpers. |

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

Use the single **Apply rules to review** button to save/validate the configuration, scan matching annotations, and select decisions in Review & apply. A summary reports ID removals, replacements, actual policy overrides, and manual conflicts. JSON uploads load configuration automatically without applying it; **Download concept rules JSON** remains separate. There are no Save, Preview, Load, or separate acceptance buttons in the rules form. All matching original annotations are considered, not just policy findings. `literal` is always preserved. Replacements require an existing active target even when overriding policy.

**Review & apply** shows a separate rule-decision editor, allowing Apply choices to be saved and automatic selections undone. Existing manual decisions are protected; stale inputs or conflicts block export. Rule-only reviews are supported without generating generic suggestions. The ordinary Run sanitization / deployment controls perform the actual write-back. See [rule semantics and write-back](/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md).

# Review and apply behavior

The review UI distinguishes **single/no-choice** replacement suggestions from rows that need an explicit manual candidate choice. “Single/no-choice” means that at most one replacement candidate is available; it does not mean the row has already been accepted. The review workspace provides bulk actions to apply or clear all single/no-choice replacements globally or within a document section. BM25 single-candidate suggestions are intentionally review suggestions and are not automatically accepted unless the user selects Apply or uses the bulk action.

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
