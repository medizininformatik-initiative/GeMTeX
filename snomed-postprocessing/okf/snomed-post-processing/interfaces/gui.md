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
| `/src/snomed_post_processing/gui/app.py` | Framework-neutral launcher: Streamlit by default; `--frontend nicegui` selects the prototype in the same Python environment. |
| `/src/snomed_post_processing/gui/streamlit/app.py` | Main Streamlit page setup and tab orchestration. |
| `/src/snomed_post_processing/gui/streamlit/sidebar.py` | Shared input/sidebar controls, target-view selection, blacklist mode selection, INCEpTION API controls. |
| `/src/snomed_post_processing/gui/streamlit/file_sources.py` | Shared file selector supporting Upload, Data directory, and Server path. |
| `/src/snomed_post_processing/gui/streamlit/policy_tab.py` | Policy checks, persistent findings tables, and report downloads. |
| `/src/snomed_post_processing/gui/streamlit/sanitization_check_tab.py` | Suggestion generation UI and settings metadata. |
| `/src/snomed_post_processing/gui/streamlit/concept_rules.py` | Explicit concept-rule form, one-step application to review, and rule-decision review/clearing. |
| `/src/snomed_post_processing/gui/streamlit/sanitization_run_tab.py` | Review/apply UI and INCEpTION deployment form. |
| `/src/snomed_post_processing/gui/streamlit/downloads.py` | Markdown/JSON download helpers. |

Launch with `python src/snomed_post_processing/gui/app.py` or `python -m snomed_post_processing.gui.app` (prefix with `uv run` in the project environment). This stable launcher defaults to `sys.executable -m streamlit run <absolute-path-to-streamlit/app.py>`; `--frontend nicegui` lazily calls the NiceGUI entry point in-process. It starts only the selected frontend, forwards its remaining options and propagates its exit status. Importing the launcher starts no server and imports neither GUI framework. Both use `.venv-py311`; enable the project extra with `UV_PROJECT_ENVIRONMENT=.venv-py311 uv sync --locked --extra nicegui`, then run `.venv-py311/Scripts/python -m snomed_post_processing.gui.app --frontend nicegui --show`. Keep `--extra nicegui` on uv run/sync commands to avoid removing optional packages. Direct backend startup remains available with `streamlit run src/snomed_post_processing/gui/streamlit/app.py`. Imports and AppTest mock targets use `snomed_post_processing.gui.streamlit.*`. `gui/__init__.py` remains framework-neutral, with no legacy module aliases or re-exports. The sibling `gui/nicegui/` package now contains suggestions inspection and explicit manual review JSON staging/import/export; see the NiceGUI section below. It is selectable through the shared launcher; Streamlit remains the default. The relocation changes paths only, not processing, defaults, state semantics or artifact formats.

## Relocation verification

Offline relocation checks cover the script-file entry point, framework-neutral `gui` namespace, relocated imports/mock targets, per-tab AppTests, shared scope and synthetic write-back workflow. Of 134 focused checks, 131 pass. Three existing assertions fail because the GUI currently initialises both BM25 automatic selection and **Disable TLS verification** to `True`, whereas the tests expect `False`. Both values were already present in `HEAD` before relocation; they were deliberately left unchanged in this path-only migration. In particular, current GUI TLS opt-out is preselected even though the deployment API still defaults to verification enabled. Resolve these defaults separately rather than hiding the failures or altering them during relocation. No network, live deployment or browser validation was performed.

# Shared review context

`review_context.py:ReviewContext` is framework-neutral and is now used by Streamlit's suggestion-metadata generation and review rows. `from_project_zip(data, file_name, annotators=...)` extracts scoped JSONCAS/XMI sofa text and document aliases; `from_metadata(metadata, document_texts=...)` adds saved snippets without opening metadata paths. `label(finding)` preserves project-text → identity-matched metadata snippet → placeholder precedence, two-word context, character fallback and display truncation. `missing_documents(findings)` provides diagnostics without document bodies. Streamlit retains selected-file reads, session caching keyed by source/normalized annotators, error handling and once-per-result warning suppression. No database/network access, global cache or GUI imports are introduced. NiceGUI now builds a page-local context from the uploaded suggestions metadata and uses its retained backend finding/original index for lookup. The existing Annotation text line displays matching saved context, otherwise the original covered text, without extra fields or missing-context messages. Context clears on navigation/source reset; failed uploads retain the old context. Malformed non-array context metadata is ignored. Project-ZIP loading remains disconnected; metadata paths are never opened. Nine targeted context tests pass, including scoped/original-index lookup and plain-text rendering. Context/scope/Streamlit regressions: 47 targeted tests pass, including a clean-process check that importing the shared module loads neither GUI framework.

# NiceGUI prototype (parallel frontend)

`gui/nicegui/app.py` remains a direct entry point and is also dispatched by the shared launcher. NiceGUI 4.0.0 is installed alongside Streamlit 1.50.0 in `.venv-py311` (Python 3.11.13), via the project's optional `nicegui` extra. The cross-platform lock has 100 packages (99 installed on Windows); only certifi/idna/Pygments changed among retained versions. The original Python 3.9 `.venv` remains untouched. The full regression run reports 280 passed, the same 3 pre-existing GUI-default failures and 2 warnings. The current bootstrap rejects unsupported Python/missing or mismatched NiceGUI versions, binds localhost by default, disables reload, and opens a browser only with `--show`.

`page.py` builds three workflow tabs with a document carousel around a read-only AG Grid Community finding/candidate workspace. Each document has a slide with its name as a heading; the Document column is omitted. Two grids and their existing controls are reused on the active slide, rather than instantiating grids for every document. Slides group only the loaded annotator scope, preserve original row indices, and filter presentation only: pending/saved choices survive navigation and Save/export still cover all documents. Navigation clears inspection and stale menus; delayed row events from hidden documents and old-source slide tokens are rejected. New sources park the workspace before deleting old slides, then reset review normally. Empty artifacts retain the global review controls. Targeted validation: 79 tests pass, and installed-SDK construction/navigation/repeated source reload checks preserve both grids; isolated Edge browser regression checks now verify finding clicks on first/forward/backward slides and after synthetic upload. Carousel keep-alive must remain disabled: cached panels otherwise retain stale rows from the moved grid's previous document (reproduced in the browser). Responsive sizing remains unverified. The tables are stacked vertically at all viewport sizes: full-width findings above full-width selected-finding details/candidates/review controls, rather than a narrow right-hand candidate pane. The findings grid's Covered text column has a 400 px minimum plus flexible remaining width, preventing collapse on initial load/upload. Candidate rank/score columns are compact and FSN has a 240 px minimum plus flexible remaining width; very narrow screens scroll within the grid instead of collapsing candidate text. Above the candidate table, annotation details occupy the left half and saved proposed SCTID/rationale/retrieval warnings the right half, stacking below the medium breakpoint. Original index is omitted from visible columns/details, and saved candidate count is omitted from details; original indices/counts remain in the model/backend artifacts for identity and provenance, without changing decision matching. Ignored is the last findings column and Document reviewed has no visible column. The document slide heading turns green/emphasized only for the saved reviewed-document flag (including imported flags), with a plain-text tooltip explaining progress. Pending mark/unmark changes do not recolor until Save choices; saved unmark/new-source reset clears styling. Green/emphasis classes are removed for unreviewed headings so styling does not stick after updates; headings use plain labels, not HTML renderers. Green is not proof every finding is resolved. Score cells use a display-only two-decimal formatter, with blank missing scores; numeric filtering/sorting, full-precision competition ranks, raw evidence and backend/JSON values are unchanged. This presentation-only change preserves row IDs, selection, staging and artifact semantics; visual/browser validation remains separate. `state.py` holds presentation-only state separately per page; `demo.py` supplies artificial data at startup. `suggestions.py` imports uploaded suggestions through the unchanged backend `read_sanitization_suggestions_json_with_metadata`, retains parsed backend objects/metadata server-side, and projects only in-scope rows for display. No project ZIP/HDF5 is opened. Uploads may contain clinical text; only explicitly uploaded content is read, and error messages do not echo it. Metadata paths are never opened.

**3. Review & apply → Load suggestions JSON** accepts one JSON file up to 50 MiB, with server-side size enforcement. Saved `metadata.annotators` scope is normalized by existing scope helpers and inherited without a broadening control; original suggestion indices remain those of the unfiltered source tuple. Duplicate findings remain distinct. **Use synthetic demo** resets this page only. Parsing runs via NiceGUI `run.io_bound`; newer uploads/demo reset supersede pending older loads. Failed loads retain the existing preview, selections and source label. State is not persisted across reloads; NiceGUI's normal upload transport may use temporary spool files.

Finding IDs include a new import snapshot plus original index; candidate IDs additionally include role and original ordinal, so the same SCTID can appear in multiple channels or as both selectable/context-only evidence without merging. Stale events cannot navigate into another imported artifact or excluded scope. SCTIDs remain strings; saved order/full-precision scores, `1,1,3` competition ties, ignored flags, original text/FSNs/spans, counts, rationale, proposed targets, retrieval-limit warnings and candidate evidence are retained. Context rows are unranked/non-selectable. Saved proposals are provenance, not preselected targets. Only affected detail/candidate panes update during navigation; normal filtering does not replace model state. Text uses labels/plain grid cells, not HTML; metadata and backend objects are not dumped into grid payloads.

Processing/shared scope controls, project/HDF5 loading, rule editing/application, generation, conditions, new ID-removal choices, ZIP write-back and deployment are **not connected**. Explicit Keep/replacement/deletion/manual-edit staging, Save, document flags and reviewed-decisions JSON download/restore are now connected (see below). Suggestions import is read-only, not HDF5 target revalidation. Placeholder buttons are disabled. Do not treat preview objects as backend findings or reviewed decisions. No existing scoring/policy/decision/CLI/artifact semantics were changed.

Offline tests cover model isolation, IDs, candidate membership, representation, frontend dispatch and bootstrap/error handling. Real file and module shared-launcher smoke checks started NiceGUI on temporary loopback ports and returned HTTP 200 containing the prototype warning, findings and candidate controls; both owned test processes were stopped afterward. File dispatch temporarily excludes the launcher directory from the process import path so sibling framework packages do not shadow the installed SDK; the original path is restored on return/error. An IDE can already have cached the local package under top-level `nicegui` before that exclusion: the launcher now removes only `nicegui`/`nicegui.*` aliases whose source files lie inside the local frontend folder, preserving the real installed SDK and `snomed_post_processing.gui.nicegui.*` imports. Follow-up validation: 31 focused tests pass; real module, file and deliberately preloaded-local-alias startup checks each return HTTP 200. The full suite was not rerun for this follow-up. Restart the IDE run to load the updated launcher. This verifies actual server startup/page construction, not browser JavaScript, visual layout, selection/focus/scroll or tab lifecycle. Those checks and backend adapter integration remain pending; no clinical project or live INCEpTION was used. Local reference sources: `/docs/gui-alternative/references/nicegui/` (AG Grid events/IDs, tabs, layout and storage) and `/docs/gui-alternative/STREAMLIT_TO_NICEGUI_COMPONENTS.md`.

## Read-only suggestions import validation

67 focused tests pass: new adapter/upload callbacks plus existing prototype, launcher, scope, findings IO and synthetic multi-annotator workflow checks. They cover exact backend-reader retention, metadata scope/original indices, duplicate identities/channels, safe malformed/oversized/read-error handling, ties, diagnostic separation, page isolation, stale events and out-of-order loads. A temporary loopback NiceGUI server exercised actual multipart upload using only the synthetic fixture: Alice-only metadata restricted display while retaining original indices; a later invalid upload preserved the previous rows/source. The server was stopped afterward. No clinical input or external INCEpTION was used. Browser JavaScript/visual interaction remains unverified; the full suite was not rerun for this increment.

## Explicit NiceGUI review JSON

`review.py:ReviewSession` is separate from presentation/navigation state; `review_ui.py:ReviewControls` provides event adapters without importing either framework at module load. Uploaded suggestions enable distinct right-click menus: **Findings** offers **Accept Suggestion**, **Delete**, **Manual Review**, **Keep Original** (no Apply); the **Selected finding** candidate grid offers only **Apply**. Accept Suggestion explicitly stages the saved proposed SCTID only when it uniquely matches one selectable candidate, not the inspected/first candidate. Missing, unavailable, context-only or duplicate-channel matches are disabled and direct commands reject them. Candidate Apply targets the right-clicked selectable candidate; opening either menu never stages. Commands still require **Save choices** → **Download reviewed decisions JSON**. Delete stages `action=delete`, `delete_annotation=true`, `apply=false`, `resolved=true`; Manual review stages `action=manual_edit`, `manual_edit=true`, `apply=false`, `resolved=false`, for a later ManualReview marker while preserving the original annotation. Actions are mutually exclusive and new deletion/manual decisions carry no stale candidate evidence. Locally saved actions remain editable; imported protected actions remain read-only. The separate Use candidate and Keep original buttons are removed; Keep Original is in the findings menu to reset an action without deletion. Native right-click events capture the rendered row ID/pointer coordinates and open a custom NiceGUI context menu only after snapshot validation (no Enterprise module). Captured state/session/finding/candidate identity guards menu commands against intervening navigation/import/reset; menus close on review refresh. Shift + right-click and non-row clicks keep the browser menu. Clicking rows never stages, defaults never approve, context candidates cannot be staged, and pending changes block download until saved/discarded. Keep is `action=none`, `apply=false`, `reviewed_by_human=true`, not deletion/ID removal; `resolved` retains existing backend meaning. Document flags are staged then saved using a compact flat/round icon before each document heading (old mark/unmark buttons removed), without requiring finding selection. Grey outline means unreviewed, green filled means saved reviewed, and amber shows the pending effective flag; tooltip/ARIA label names the next action. Save commits and Discard restores saved icon state; headings remain green only for saved flags. Header callbacks capture source identity to reject stale-upload events. Confirming a document conservatively protects its non-rule generic rows as human-reviewed, like Streamlit. Unmarking progress does not undo manual choices. Filters do not limit export. Serialization runs off the UI loop, with revision checks before download so concurrent changes cannot publish stale review. Synthetic demo remains inspection-only.

The unchanged backend decisions reader/writer produce version-1 artifacts. Export retains original indices/scope, metadata settings, imported provenance/rule snapshots, and all in-scope generic rows (unreviewed rows remain non-applying). `manual_candidate`/`manual_candidate_ordinal` retain exact saved candidate evidence for duplicate code/channels; `metadata.nicegui_suggestions_sha256` binds the complete original suggestions tuple, independent of display filters. No metadata paths are followed. Suggestions metadata contributes only write-back settings, not full-document clinical contexts; any imported review context records are filtered to current scope. Legacy Streamlit artifacts without this fingerprint use original index/source-identity/text and current selectable-target checks, not HDF5 validation. Imports with narrower scope than the active artifact are rejected; broader artifacts are filtered to current scope without renumbering.

Import explicitly replaces current saved/pending choices and reviewed flags only after full successful parsing/validation (50 MiB). Invalid, oversized or unreadable imports retain review and do not echo content. Shared revision guards reject stale imports after newer uploads/demo reset; an edit revision prevents a slow import overwriting newer manual work. Successful new suggestions/demo reset all local review with a visible notice. Reload discards page state: only an explicit JSON download persists review, and that download may contain clinical text.

Imported rules are preserved read-only, reserve their source identities and conflict with selected/manual generic decisions rather than overwriting them. Imported deletion/manual-edit/ID-removal actions are protected; edit them in Streamlit. No rule/HDF5 revalidation or rule generation is claimed. Unrelated saves preserve automatic provenance; explicit human confirmation removes affected automatic ownership. CAS write-back and deployment stay disconnected.

97 focused tests pass, including exact synthetic Streamlit decisions round-trip, scope, original indices, protected actions, duplicate evidence, safe failures and race handling. Actual NiceGUI polling and WebSocket clients exercised listener events, scoped staging, Keep, Save, flags, binary JSON download, replacing import and failed-import retention without ASGI errors. Owned servers stopped; no clinical/external-service inputs. Full-suite and visual/browser-JavaScript checks were not performed for this increment; baseline default failures remain unresolved.

Right-click action follow-up: 107 focused checks pass, including scope/synthetic workflows, mutually exclusive action flags, local reversal versus protected restore, stale menus/navigation/snapshots, and existing JSON fidelity/races. The actual native JavaScript handler was checked for exact row-ID/coordinate emission and preservation of Shift/non-row browser defaults. Real loopback WebSocket/polling listeners exercised Apply, Delete, Manual review, Save, scoped binary JSON, local reversal and protected replacing import without ASGI errors; the owned server was stopped. This is protocol/handler validation, not a visual check of menu positioning or real browser event bubbling/focus. No clinical data/external services or full-suite run.

Split-menu follow-up: 110 focused tests pass. Findings now has exactly Accept Suggestion / Delete / Manual Review / Keep Original, and Selected finding candidates only Apply; the Keep original button is removed. Tests distinguish proposal acceptance from inspected/first-candidate application, reject absent/context-only/duplicate proposals, and preserve stale-menu/import/scope guards. Actual WebSocket/polling listener checks passed all five commands, JSON evidence/flags and protected restore. Menu positioning and real DOM event bubbling/focus still require visual/browser validation.

## Socket.IO ASGI compatibility guard

The installed Engine.IO ASGI translator returns `{}` when the first received frame is `http.disconnect`/`websocket.disconnect`; `AsyncServer.handle_request` then indexes `REQUEST_METHOD` and raises KeyError. This was reproduced directly with the installed adapter. The adapter also emits mixed-case response header names, violating ASGI's lowercase requirement: Starlette's gzip middleware misses the existing Engine.IO `Content-Encoding`, adds a second encoding, and larger polling updates fail to decode. A connected-upload check reproduced this as two gzip headers and a polling transport disconnect.

`nicegui/transport.py:EarlyDisconnectGuard` wraps only NiceGUI's `/_nicegui_ws` mount during `_load_ui`, before `ui.run`. It returns for an initial disconnect, otherwise replays the first frame once and forwards the stream unchanged. Response header names are lowercased while preserving values, repeats, order and body bytes. Normal HTTP/WebSocket handshakes, lifespan, uploads/other routes and downstream errors are not suppressed. Setup is idempotent and fails explicitly if the expected mount cannot be found. There is no site-packages patch, dependency downgrade, invented WSGI request or global compression change.

61 focused transport/launcher/prototype/import checks pass, including real installed Engine.IO and Starlette gzip regressions. Live loopback checks using both polling and WebSocket Socket.IO clients passed NiceGUI page handshakes, scoped synthetic suggestions upload, live UI updates and invalid-upload feedback without server ASGI errors. Test servers were stopped; no external service or clinical data was used. Full-suite and visual/browser-JavaScript testing were not performed for this fix. Stop/restart the server and then refresh the browser to load it (`reload=False` means browser refresh alone is insufficient).

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

# Shared annotator scope

**Tab 1 → Select annotators to include** is the processing scope for every tab, not just a policy-table filter. Empty means all; names are matched case-insensitively. It applies to policy checks, session/uploaded findings, suggestion generation, concept-rule scans, restored decisions, review/automatic conditions, decision downloads, local write-back and deployment artifacts. Rules still scan all documents in the selected layers, including annotations absent from findings, but only for included annotators; **Override policy** never bypasses this scope. Context extraction/cache is scoped as well. Policy results produced for another scope cannot be displayed/downloaded as current reports. Findings, suggestions or reviewed decisions produced for a narrower scope cannot silently be reused after broadening it.

Review rows retain original suggestion indices when filtered. Scope changes discard excluded annotators' pending selections, clear automatic Undo and reset document-review progress; previously excluded choices do not silently reappear if the scope is broadened. Included choices remain, but stale rule scans require reapplication. Replacing suggestions resets generic review choices to avoid index reassignment; a visible notice asks users to save review JSON first. Explicit rule choices are retained. Imported decisions are filtered against current scope rather than changing it. Restored generic decision indices must match annotation identities in the loaded suggestions; a differently filtered/reordered source cannot silently reuse them. JSON metadata records `annotators` (empty = all).

Local sanitized ZIPs retain excluded CAS members unchanged. Upload preparation omits excluded annotator/curation CAS entirely, including otherwise unchanged ones; filtering only decisions would not be sufficient. Saved decision scope is also honored by standalone artifact/deployment pipelines. Without a scope, CLI/API defaults remain all annotators. Remote validation still requires an approved test project.

# Policy-check results

The policy-check tab displays the last successful check from `st.session_state["policy_check_result"]` on every rerun. Filtering or downloading does not rerun the check. Results persist within the current session, not across server restarts; changed project/HDF5 inputs require an explicit new check. A caption identifies results as the last successful check.

The MIE/audit findings display is grouped by document and annotator, with rows sorted initially by span offset. Each table shows SCTID, FSN, covered text, critical/ignored status, inclusion-/exclusion-list check, and annotation layer. Tables support Streamlit's interactive column sorting.

Summary metrics cover critical and ignored findings, inclusion-/exclusion-list findings, affected documents, and affected annotators. These metrics describe the complete result. Document/annotator group counts describe the filtered rows.

Filters support status, check type, SCTID substring, and case-insensitive covered-text substring. Clear all filters restores the full display. Filters never modify the stored findings or exported reports. Empty findings and empty filtered results have explicit messages.

CriticalFindings JSON, Markdown, masked Markdown, and report JSON downloads remain available. The table replaces the inline Markdown report preview, not the Markdown exports. The existing `critical_findings`, `critical_findings_json_text`, and `critical_findings_json_name` session fields remain populated for sanitization.

# Annotation ID feature and prefix

The sidebar annotation-layer settings include the configurable SNOMED ID feature name and prefix. The feature defaults to `id`; the prefix defaults to `http://snomed.info/id/`. Use an empty prefix for layers that store plain SCTIDs. The same feature/prefix settings are used when matching reviewed decisions and writing replacement IDs. See [Annotation layer requirements](/snomed-post-processing/data/annotation-layer-requirements.md).

# BM25 matching settings

**Advanced suggestion settings → Matching semantic-tag boost (%)** controls the separate score bonus for matching source/candidate FSN tags (default 10%, range 0–100; 0 disables it). A tooltip explains the multiplier and unchanged lexical overlap, and the active-settings notice shows the selected percentage. Known FSNs are indexed/queried without the trailing semantic tag; full display labels, clinical parentheses and SNOGIT terms are preserved. Suggestion JSON settings record the boost and FSN-tag exclusion. Regenerate suggestions after changing scoring settings; automatic-acceptance thresholds remain unvalidated heuristics.

# Replacement choice safety

Suggestion generation puts selectable replacements in `candidates` and rejected targets in `context_candidates`. Review offers only replacement candidates, not diagnostic context. Overview/report displays label diagnostics **Diagnostic candidates (not selectable)**.

**Active release** keeps optional exclusion-list enforcement, following the sidebar settings. Policy mode remains strict; explicit concept rules retain their existing **Override policy** behavior. Regenerate suggestions after changing target settings. No additional HDF5 revalidation is performed during generic review/export.

# Concept rules

The **Suggest policy sanitization** tab includes a **Concept rules** form in a collapsed-by-default expander above fallback settings. It defaults to Number `410680006` → remove ID only, and Date `410671006` → Date property `410672004`. Rules and per-rule **Override policy** are enabled by default. The form supports dynamic rows and separate rule JSON import/export. It uses the sidebar's target annotation layers across all documents within the shared annotator selection from tab 1; there are no separate rule-scope input boxes.

Column-header tooltips explain **Enabled**, **Name**, and the rule fields. **Override policy** is permission to bypass list restrictions, not permission to replace existing review decisions or bypass target existence/activity checks; it has no effect for **Remove ID only**. This distinction also appears as a visible note below configuration. In tab 3, **Override policy** and **Policy actually overridden** are read-only columns with tooltips distinguishing permission from an exception actually needed for that replacement. **Apply** stages an action for later export/upload; changing it does not immediately modify the project.

Use the single **Apply rules to review** button to save/validate the configuration, scan matching annotations, and select decisions in Review & apply. A summary reports ID removals, replacements, actual policy overrides, and manual conflicts. JSON uploads load configuration automatically without applying it; **Download concept rules JSON** remains separate. There are no Save, Preview, Load, or separate acceptance buttons in the rules form. All matching original annotations are considered, not just policy findings. `literal` is always preserved. Replacements require an existing active target even when overriding policy.

**Clear all pending rule decisions** is always visible with **Apply rules to review** in tab 2's **Concept rules** expander, disabled when no pending rule decisions exist. Clear removes all pending decisions, including saved Apply-checkbox choices, without changing rule definitions or CAS files. Reapplying rules preserves saved checkbox choices. There is no separate Undo button or application-history snapshot. **Review & apply** (tab 3) shows only the resulting rule-decision editor and its Save action, not the rule-management buttons. Existing manual decisions are protected; stale inputs or conflicts block export. Rule-only reviews are supported without generating generic suggestions. The ordinary Run sanitization / deployment controls perform the actual write-back. See [rule semantics and write-back](/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md).

# Review and apply behavior

The review UI distinguishes **single/no-choice** replacement suggestions from rows that need an explicit manual candidate choice. “Single/no-choice” does not mean accepted. In Streamlit's batched manual-choice form, **Apply this replacement** stays enabled whenever selectable candidates exist, even while the dropdown still shows no selection or another action is currently checked. This permits selecting a target and changing action checkboxes in one submission without an intermediate Save. Saving with no target clears Apply; deletion/manual edit still takes precedence. Rows without selectable candidates keep Apply disabled. Dropdown changes do not rerun Python until the form is submitted. Global and per-document bulk apply/clear buttons are replaced by an **Automatic conditions** form in tab 3 with **Apply Conditions** and **Undo Automatic Conditions**.

For large first-place BM25 ties (more than five targets), a collapsed **Browse BM25 candidates** expander appears above the document's manual-choice form, identified by row number and source SCTID. It provides SCTID/FSN search and a scrolling read-only table with single-row selection and precise scores. Browser ranks and replacement-choice hints use shared competition ranks for numerical ties (1, 1, 3), using the same full-precision tolerance as BM25 rather than rounded display values; filtering does not renumber candidates. **Use selected candidate** stages the selected SCTID in the form's compact dropdown; **Save choices** commits it. No tied candidate is preselected; smaller ties keep the normal dropdown with a no-selection option. Browser keys follow annotation identity, table selections map to SCTIDs using the rendered snapshot, and filtering does not silently change a pending selection. For staged/restored choices, Session State is authoritative; dropdown and action-checkbox defaults are supplied only when their keys are not initialized, avoiding Streamlit's duplicate-default warning. Search/selection is isolated in a Streamlit fragment; staging refreshes the form without writing CAS. Recorded retrieval limits are visible and block automatic BM25 acceptance; counts are lower bounds when coverage is incomplete. The generation candidate limit is soft and includes cutoff ties, with explicit safety caps.

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

# Document section opening controls

In review, **Open document sections** replaces the misleading **Focus documents** pills. These are expansion controls, not filters: every document and its decision widgets remain rendered, and opening/collapsing never changes selections or export scope. Each button has its own hover help. The default is **Collapse all**; **All** opens even reviewed sections, while **Unreviewed** opens only sections not marked reviewed. **Needs choice** opens unreviewed sections with at least one unresolved multi-choice row, using the same resolution predicate as the review counters (applied replacement, deletion or manual-edit selection). Already resolved choices no longer match. **No replacement** opens unreviewed sections with a row displaying no selected replacement; selectable candidates may still exist, as its tooltip explains.

Explicit button clicks clear the temporary keep-document-open override and increment a separate opening revision. A keyed wrapper reapplies expansion even on repeated clicks/manual expander toggles, without changing inner widget keys or the review-state revision. Choices remain stable; no widgets are hidden or removed merely to focus the display.

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
