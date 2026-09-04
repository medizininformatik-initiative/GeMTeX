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
| `/src/snomed_post_processing/gui/policy_tab.py` | Policy/HDF5 creation UI. |
| `/src/snomed_post_processing/gui/sanitization_check_tab.py` | Suggestion generation UI and settings metadata. |
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
