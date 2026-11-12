---
type: Runbook
title: Follow-ups and validation checklist
description: Open testing, smoke-test, performance, and deployment follow-up work for SNOMED Post Processing.
resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/release-view-follow-ups-and-docs-review.md
tags: [follow-up, testing, validation, gui, deployment]
status: draft
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: followups-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/release-view-follow-ups-and-docs-review.md
    title: Release-view follow-ups and documentation review
  - id: test-tree
    resource: /test
    title: Test suite
---

# Open follow-up work

## Python 3.11 migration validation

Configuration is prepared for Python 3.11.x: `pyproject.toml` uses `~=3.11.0`, `.python-version` is `3.11`, Docker uses `python3.11-bookworm-slim`, and the initial 62-package migration lock preserved retained dependency versions (the optional NiceGUI integration below subsequently extends it). PyInquirer has been replaced with Click. The 3.11 lock passes an offline consistency check.

With approval, `UV_PROJECT_ENVIRONMENT=.venv-py311 uv sync --locked --python <installed-3.11.13-interpreter>` created a fresh ignored environment and installed all 62 locked packages, including the editable project and Git-pinned SCTTSRApy. Installed package consistency, imports of native/core packages and all 11 Click entry-point help commands pass. PyInquirer/prompt-toolkit are absent. The original Python 3.9.23 `.venv` remains unchanged; no system-wide Python/PATH changes were made.

The initial full Python 3.11 migration suite reported **275 passed, 3 failed, 2 warnings**. HTTP requests and external DNS/socket connections were blocked during testing (local internal communication/test mocks allowed). These three failures were also reproduced under the preserved 3.9 environment:

- `test_gui_automatic_conditions.py::GuiAutomaticConditionsTest::test_bm25_is_opt_in_and_shares_the_last_run_undo`
- `test_gui_help_text.py::GuiHelpTextTest::test_automatic_condition_help_and_relationship_descriptions`
- `test_gui_help_text.py::GuiHelpTextTest::test_deployment_help_preserves_offline_defaults`

They assert BM25 opt-in / TLS opt-out should default to unchecked, while current GUI defaults are checked. Neither defaults nor tests were changed or marked xfail. No new Python-3.11-specific failure was identified, but this is not an all-green suite. Resolve these defaults separately.

Use `.venv-py311/Scripts/python.exe` in the IDE or set `UV_PROJECT_ENVIRONMENT=.venv-py311` for uv commands; do not allow default uv sync to replace the retained `.venv` inadvertently. Docker build/browser/live INCEpTION validation remain separate approved actions. NiceGUI is now installed as an optional project extra in that same environment; see the integration check below. Full browser interaction validation remains pending.

### Shared NiceGUI runtime

With approval, the `nicegui` project extra was added (`nicegui==4.0.0`) and installed into `.venv-py311` using `uv sync --locked --extra nicegui`. The lock now contains 100 packages across platforms (99 installed on Windows). Existing certifi/idna/Pygments versions were updated for NiceGUI's minimums; all other retained versions and the Git SDK revision are unchanged. Installed dependency and offline lock checks pass.

The shared launcher defaults to Streamlit; `--frontend nicegui` dispatches lazily in-process, using the same interpreter/environment without starting Streamlit. Options are backend-specific (`--port` for NiceGUI, `--server.port` for Streamlit). Unknown frontend values fail before either server starts. Both import and default behavior remain framework-neutral/Streamlit-compatible.

Both direct-file and module shared-launcher forms started temporary, owned NiceGUI servers on loopback. `GET /` returned HTTP 200 with the synthetic warning, findings and candidate controls; both processes were stopped after checking. File dispatch excludes the launcher directory while NiceGUI runs, preventing its sibling `nicegui/` package from shadowing the installed SDK; the original search path is restored even on startup errors. Browser JavaScript/visual interaction and real backend workflows are not validated by this check. No clinical project, live INCEpTION or Docker build was involved.

After adding launcher tests, the full suite reports **280 passed, the same 3 failures listed above, 2 warnings**. No failures were suppressed or defaults changed. Keep `--extra nicegui` on uv run/sync commands for the shared environment; plain base-only sync may uninstall it.

## End-to-end option tests

Add CLI/pipeline tests for release-view behavior:

| Case | Expected release-view behavior |
|---|---|
| no blacklist flags | active concepts are allowed even if embedded-blacklisted |
| `--enforce-embedded-blacklist` | embedded-blacklisted concepts are excluded |
| `--custom-blacklist PATH` | custom-blacklisted concepts are excluded |
| both blacklist options | embedded and custom blacklist exclusions are both applied |

Include BM25/SNOGIT fallback in at least one release-view test if feasible.

## Manual GUI smoke test

Run Streamlit and verify suggestion generation for:

- policy view;
- active release view with no blacklist;
- active release view with embedded blacklist;
- active release view with custom blacklist;
- active release view with embedded + custom blacklist;
- release view with semantic BM25 fallback;
- release view with a processed SNOGIT cache.

Check that suggestion JSON metadata records target view and blacklist settings.

## Manual large-dataset performance test

Test realistic data sizes for:

- custom blacklist descendant resolution from HDF5 ancestor arrays;
- semantic BM25 fallback over main HDF5 FSNs;
- processed SNOGIT cache lookup;
- repeated annotation-text caching.

Track runtime and memory for policy mode and release mode.

## INCEpTION deployment validation

After real `apply-decisions-to-inception --apply`, inspect the target INCEpTION project:

- flattened documents imported;
- Concept annotations present;
- ManualReview markers present where expected;
- sentence-based editor loads all documents;
- remote-upload compatibility issue count is zero.

## Optional SNOGIT false-positive mitigation

If real data shows noisy suggestions for short/generic annotations, consider:

- higher lexical-overlap threshold for one-token queries;
- minimum token count before SNOGIT fallback;
- semantic-tag compatibility checks;
- stricter score margin for ambiguous candidates.

# Current validation snapshot

As of the prior implementation work, the full test run was:

```text
uv run pytest test -q
105 passed
```

# Documentation migration status

Every file formerly under the former documentation folder has been imported into this OKF bundle under `/snomed-post-processing/source-former documentation folder/`, and its content has also been consolidated into curated concept pages. Do not delete the former documentation folder automatically; deletion should be a separate human-approved cleanup step.
