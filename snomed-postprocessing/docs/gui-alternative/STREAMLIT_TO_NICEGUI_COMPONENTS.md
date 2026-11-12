# SNOMED-PP: Streamlit → NiceGUI replacement candidates

**Status:** migration design plus read-only NiceGUI demo/suggestions-JSON preview; real server startup/page construction checked; production workflows and browser interactions remain unvalidated. See [`gui/nicegui/README.md`](../../src/snomed_post_processing/gui/nicegui/README.md) for isolated setup and limitations.
**Documentation snapshot:** 2026-11-11; see [download manifest](references/nicegui/manifest.json).  
**Application inspected:** `C:/Users/fra3066mat/PycharmProjects/GeMTeX/snomed-postprocessing`.  
**Source paths below:** relative to `src/snomed_post_processing/`, unless stated otherwise. The original inventory predates the package relocation: all listed Streamlit `gui/*.py` modules now live under `gui/streamlit/*.py` (`snomed_post_processing.gui.streamlit`). The parallel `gui/nicegui/` package contains a read-only frontend for synthetic data or explicitly uploaded suggestions JSON. A new framework-neutral `gui/app.py` is the stable Python launcher; it defaults to Streamlit and selects NiceGUI with `--frontend nicegui`, using the same Python 3.11 project environment.

## 1. Goal and boundaries

The goal is a better **frontend experience**, especially:

1. More usable findings, suggestions, candidate and review tables.
2. Editing, searching and selecting without whole-script reruns.
3. Removing forms introduced merely to suppress those reruns.
4. Keeping focus, scroll position, selection and pending decisions stable during interaction.
5. Giving users clear feedback about staged edits versus actual project changes.

This is **not** a backend optimisation project. Preserve existing SNOMED checks, candidate scoring, policy restrictions, decision semantics, CLI and JSON/ZIP formats. Frontend event wiring must not accidentally launch processing on every input change.

**Recommended starting point:** NiceGUI `ui.aggrid` for the principal data workspaces, ordinary NiceGUI controls for settings and detail panels, and `ui.table` selectively for small tables. Do not reproduce the current form boundaries by default.

### Evidence and confidence

- **Documented API:** the named NiceGUI component/method is present in the downloaded documentation.
- **Design candidate:** a suggested composition or interaction; not a drop-in API equivalent.
- **Prototype check:** event ordering, edit preservation, grid configuration or visual behaviour that needs verification against a pinned NiceGUI version.

The live documentation is not version-pinned and includes underlying Quasar/AG Grid options. Pin the implementation dependencies before treating examples as an API contract. NiceGUI 4.0.0 is now installed as a project extra. Real loopback server/page-construction checks through both file and module forms of the shared launcher returned HTTP 200. Offline presentation-model/bootstrap/dispatch tests also pass; browser JavaScript and visual/interaction behavior still need verification.

## 2. The important replacement: reruns → events

| Streamlit mechanism | NiceGUI replacement candidate | Recommendation |
|---|---|---|
| `st.form(...)` to batch widget changes | Ordinary `ui.column`, `ui.card` or `ui.expansion` containing inputs | **Remove the batching boundary.** Input changes update UI state through callbacks/bindings. |
| `st.form_submit_button(...)` | `ui.button(..., on_click=...)` | Remove purely technical Save/Apply-settings buttons; retain deliberate workflow commands. |
| `st.session_state` | Per-page state object; optionally `app.storage.client` / `app.storage.tab` | Keep state independent of widgets. Do not replace with a process-global dictionary. |
| `st.rerun()` | `.set_text()`, `.set_value()`, bindings, targeted grid transactions / row updates | Update existing elements in place. No equivalent full-page rerun should be needed for routine review. |
| `@st.fragment` | Callback scoped to its owning elements; local `@ui.refreshable` only where needed | A callback does not rerun the page. Refreshable functions are for structural changes, not every keystroke. |
| Widget keys and editor-revision keys | Stable model IDs, retained component references and explicit selection state | Keep business identity; remove keys/revisions whose only purpose was forcing Streamlit reconstruction. |
| Widget defaults read on every rerun | Initialise from model once, then synchronise intentionally | Loading another artifact is an explicit state replacement, not another application of defaults. |
| Form submit as implicit validation boundary | Field validation plus command-level validation | Invalid intermediate input is allowed as a draft, but must not become an exportable decision. |

**Important:** `@ui.refreshable` deletes and recreates its elements. Used around the whole review workspace, it can recreate the same focus/scroll/edit disruption we are trying to remove. The NiceGUI docs also warn that globally defined refreshables can share refresh state across visitors. Prefer per-page/local refreshables or per-page view instances.

References: [bindings](references/nicegui/section_binding_properties.md), [refreshable](references/nicegui/refreshable.md), [events](references/nicegui/section_action_events.md), [storage](references/nicegui/storage.md).

## 3. Table replacement strategy

### 3.1 `ui.aggrid` versus `ui.table`

| Requirement | `ui.aggrid` | `ui.table` | Preferred use here |
|---|---|---|---|
| Wide, dense analytical tables | Configurable grid with column definitions and AG Grid APIs | Quasar table with customisable columns and slots | AG Grid for findings, overview and review. |
| Sorting and searching | Text/number filters, floating filters and grid APIs | Sortable columns and table filter | Both; keep current exact filter semantics where required. |
| Row selection | `rowSelection`, `get_selected_row()` / `get_selected_rows()` | `selection`, `selected`, `on_select` | Both; selection means navigation, not approval. |
| Editing | Editable grid cells; events and explicit client-data retrieval | Custom cells/slots with controls and event handlers | AG Grid for rule/review editors; ordinary controls in detail panels for complex choices. |
| Rich per-row controls | Column/editor configuration; advanced renderers may need JavaScript | Scoped slots can contain NiceGUI controls; event bridging may still use small JS expressions | Table is a possible alternative for small highly interactive lists. |
| Incremental updates | `run_row_method`, `run_grid_method('applyTransaction', ...)` | Rows/columns can be updated | Prototype edit/selection stability, not just visual appearance. |
| Pandas bridge | `ui.aggrid.from_pandas(...)` | `ui.table.from_pandas(...)` | Useful for initial exploration, not a substitute for an identity/column model. |
| Small metadata table | Possible, but comparatively heavy visually | Simple fit | `ui.table`. |

**Default to AG Grid Community.** Document/annotator navigation can be implemented outside the grid; do not assume Enterprise row grouping, rich-select editors or master/detail features are included for free. The NiceGUI wrapper accepts an Enterprise bundle, but that does not grant a licence. Verify each optional AG Grid feature against the version bundled with the pinned NiceGUI release.

Sources: [AG Grid API and examples](references/nicegui/aggrid.md), [Table API and examples](references/nicegui/table.md).

### 3.2 Actual table sites in this app

| Current source / surface | Streamlit component | Recommended NiceGUI candidate | Frontend improvement and conditions |
|---|---|---|---|
| `gui/app.py`: embedded exclusion-list metadata | `st.dataframe` | `ui.table` | Small read-only table; sortable columns, concise rule labels. |
| `gui/policy_tab.py`, `render_findings_table`: document/annotator findings | Nested expanders + `st.dataframe` | One `ui.aggrid` + document/annotator navigator | Less nested scrolling; persistent column filters and selected finding; show full FSN/context in a detail pane. Keep all-result metrics distinct from visible-row counts. |
| `gui/sanitization_check_tab.py`, `_render_suggestion_overview` | `st.data_editor(disabled=True)` | Read-only `ui.aggrid` | Pin short identity/status columns; allocate width to covered text and FSN; move long rationale/candidate lists into a selected-row detail pane. This editor is currently read-only, not a decision editor. |
| `gui/concept_rules.py`, `_render_concept_rules_form` | Dynamic `st.data_editor` in a form | Editable `ui.aggrid` + Add/Delete rule buttons | Direct editing with validation indicators. Adding/removing a row is separate from scanning/applying rules. Use stable editor IDs even while a user edits the business Rule ID. |
| `gui/concept_rules.py`, `render_rule_review` | `st.data_editor` in a form; only Apply editable | `ui.aggrid` with editable Apply only | Checkbox commit updates staged review immediately. Permission and actual policy-override columns remain read-only. |
| `gui/sanitization_run_tab.py`, `_render_document_review_sections` | Per-document `st.data_editor` in forms | Review `ui.aggrid` + selected-finding action panel | Immediate staged changes without Save-table submissions. Preserve manual provenance, explicit keep decisions, unresolved state and document completion rules. |
| Same file, `_render_bm25_candidate_browser` | `st.dataframe` with single-row selection inside fragment | Read-only `ui.aggrid` with single-row selection | Search and inspect candidates without rebuilding the review workspace. Selection previews a candidate; a deliberate Use candidate action stages it. |
| Same file, `_render_automatic_conditions`: score-gap assessment | `st.dataframe` | Read-only `ui.aggrid`, or `ui.table` for small data | Keep numeric scores/D/M separate from formatted display strings. Flatten the current list-valued Scores field if using `ui.table`. |
| Same file, `_render_non_actionable_summary` | `st.dataframe` | `ui.table` or read-only `ui.aggrid` | Smaller summary can use table; align styling/status vocabulary with the main grid. |

There are **four `st.data_editor` call sites and five `st.dataframe` call sites** in the inspected GUI source. Loop-generated runtime tables may be more numerous.

### 3.3 Column configuration candidates

The following are AG Grid configuration candidates passed through `ui.aggrid`, not dedicated NiceGUI column classes. Prototype the precise configuration with the pinned grid version.

| Streamlit column behaviour | AG Grid candidate / alternative | App-specific constraint |
|---|---|---|
| `TextColumn(label, width=..., help=...)` | `headerName`, `width` / `minWidth` / `flex`, `headerTooltip`; detail-panel tooltip as fallback | Do not rely on horizontal scrolling as the only way to read FSNs. |
| `CheckboxColumn` | Boolean cell data type/editor/renderer; or `ui.checkbox` in an action panel | An Apply checkbox is **not** the grid's row-selection checkbox. |
| `NumberColumn(format=...)` | Numeric values plus a display `valueFormatter` | Rank and score sorting must remain numeric; keep original full-precision scores. |
| `SelectboxColumn(options=...)` | Community select editor where sufficient; `ui.select` in detail panel for searchable/rich choices | Only generated selectable candidates may become replacements. No free-text arbitrary target entry. |
| `disabled=[...]` / `disabled=True` | Per-column `editable` configuration / entirely read-only grid | Revalidate changed fields on the server; read-only UI is not an authorisation boundary. |
| Hidden helper columns | Hidden grid columns or, preferably, server-side model data | Hidden client columns are still disclosed to the browser. Do not ship secrets/private internal data. |
| `num_rows='dynamic'` | Add/Delete controls + grid transactions | New rules must retain existing defaults and be validated before application. |
| Styling through DataFrame formatting | Grid cell classes/styles and explicit status labels | Do not communicate approval/errors only through colour. |
| `hide_index=True` | No synthetic index column; explicit human-facing row number where useful | Display number is not record identity. Preserve original suggestion index for JSON compatibility. |
| `width='stretch'`, fixed table height | `.classes('w-full')` plus a bounded height/layout | Prototype long text, narrow screens and browser zoom. |

### 3.4 Requirements for all migrated tables

1. **Stable identity:** never address a decision by a sorted/filtered row position. Use an opaque stable row ID tied to original annotation identity and suggestion-set identity; keep original `suggestion_index` separately. Detect duplicate/ambiguous identities rather than merging them.
2. **SCTIDs stay strings:** never use JavaScript floating-point numbers for identifiers. Retain original values, not prettified labels.
3. **Separate selection from decision:** selecting a row opens details; it must not silently tick Apply or approve the document.
4. **Preserve client edits:** changing `grid.options['rowData']` can trigger a client rebuild and discard active edits. Use targeted row updates/transactions; where supported, `grid.props.suspend_updates()` keeps server data in sync without an additional rebuild.
5. **Explicit edit commit:** grid data is not updated until an active cell leaves edit mode. Consider `stopEditingWhenCellsLoseFocus=True`; before exporting/changing document, finish editing and ensure pending events are validated/acknowledged.
6. **Server is authoritative:** synchronise cell-change events into the review model. Do not assume editing the browser grid automatically changes Python `options['rowData']`.
7. **Export full review state:** use the authoritative model, not only selected, visible or filtered rows. `get_client_data(method='all_unsorted')` can reconcile a grid snapshot, but is not a durable storage or validation mechanism.
8. **Keep filters local to presentation:** searching, sorting and hiding rows must not change annotator processing scope, proposal eligibility or the underlying export set.
9. **Preserve candidate evidence:** competition ranks (e.g. 1, 1, 3), full-precision tie handling, retrieval-limit warnings and diagnostic-only targets survive display changes.
10. **Safe rendering:** render imported clinical text/FSNs as text. Avoid `html_columns` or unescaped custom HTML for these values. `ui.table` docs specifically warn against list-valued cells; flatten lists for display and retain structured data in the model/detail pane.

## 4. General component mapping

These are the components actually present in the GUI, grouped by role. Composite equivalents are deliberate design choices rather than claimed one-to-one APIs.

### Layout and navigation

| Streamlit | NiceGUI candidate | Notes |
|---|---|---|
| `st.set_page_config` | `ui.page_title(...)`, page layout, `ui.run(...)` configuration | Title/layout/server settings are separate concerns. |
| `st.sidebar` | `ui.left_drawer` | Shared project/policy/scope settings; optionally collapsible. |
| `st.tabs` | `ui.tabs` + `ui.tab` + `ui.tab_panels` | Keep the three workflow areas initially; preserve model state across tab changes. |
| `st.columns` | `ui.row` / `ui.grid` | Responsive groups rather than fixed proportions everywhere. |
| `st.container(border=True)` | `ui.card` or styled `ui.column` | Manual-choice/detail sections. |
| `st.expander` | `ui.expansion` | Advanced settings and metadata; do not put every document in a permanent nested expansion tree. |
| `st.popover` | `ui.popup`, `ui.menu` or `ui.dialog` | Popup/menu for compact controls; dialog for long metadata/artifact lists. |
| `st.divider` | `ui.separator` | Direct replacement. |
| Long vertically stacked document sections | `ui.splitter` + navigator + bounded `ui.scroll_area` | Design candidate; keep main grid mounted while selection changes. |

References: [page layout](references/nicegui/section_page_layout.md), [tabs](references/nicegui/tabs.md), [menu](references/nicegui/menu.md), [dialog](references/nicegui/dialog.md).

### Inputs and commands

| Streamlit | NiceGUI candidate | Notes |
|---|---|---|
| `st.button` | `ui.button(on_click=...)` | Name the domain action, not its former form mechanism. |
| `st.checkbox` | `ui.checkbox(on_change=...)` | Good for individual staged Apply/flags. |
| `st.toggle` | `ui.switch` | Clear on/off settings. |
| `st.segmented_control` | `ui.toggle` | File source, policy/release mode and artifact source. |
| `st.pills` (current single document-focus choice) | `ui.toggle` | Match All / Needs choice / No replacement / Unreviewed. Use `ui.select(multiple=True)` only for genuinely multi-select filters. |
| `st.selectbox` | `ui.select` | `with_input=True` for longer lists. |
| `st.multiselect` | `ui.select(multiple=True)` | Annotators, historical association types and SNOGIT members. |
| `format_func` for options | `ui.select(options={value: label, ...})` | Values remain stable codes; labels may contain descriptions. Follow the component API rather than guessing mapping direction. |
| `st.text_input` | `ui.input` | `password=True` for password fields; do not persist credentials in user storage. |
| `st.text_area` | `ui.textarea` | Layer lists/descriptions; apply appropriate parsing/validation. |
| `st.number_input` | `ui.number` | Use min/max/step/validation. Handle cleared `None`, validate integer-only fields, and revalidate at command execution. |
| `st.file_uploader` | `ui.upload(on_upload=..., auto_upload=True)` | NiceGUI 3+ uses `e.file`, with async content/save access; adapt the upload helper instead of assuming Streamlit's `.getvalue()`. |
| `st.download_button` | `ui.button` + `ui.download.content(...)` / `.file(...)` | Capture validated state at click time; no download fragment needed. |
| `help=...` | Element `.tooltip(...)` / `ui.tooltip` | Keep essential warnings visible, not tooltip-only. Grid header help uses column configuration. |

References: [controls](references/nicegui/section_controls.md), [select](references/nicegui/select.md), [toggle](references/nicegui/toggle.md), [input](references/nicegui/input.md), [number](references/nicegui/number.md), [upload](references/nicegui/upload.md), [download](references/nicegui/download.md), [tooltip](references/nicegui/tooltip.md).

**File-source selector:** preserve Upload / Data directory / Server path. Build it from `ui.toggle`, `ui.upload`, `ui.select` and `ui.input`, with visibility bindings instead of rerunning the selector. A server path is not a client-side file picker. Keep path validation and per-session artifact ownership.

**Search updates:** `ui.input(...).props('debounce=250')` is a documented debounce pattern. For column filtering, prefer the grid's built-in filters when they match the existing semantics. A small debounce avoids noisy frontend updates; it does not authorise regeneration of suggestions.

### Text, feedback and auxiliary displays

| Streamlit | NiceGUI candidate | Notes |
|---|---|---|
| `st.title`, `st.header`, `st.subheader` | Styled `ui.label` / semantic heading element | Establish a consistent heading scale. |
| `st.caption` | `ui.label(...).classes('text-sm ...')` | Compact help and result provenance. |
| `st.write` | Explicit `ui.label`, `ui.markdown`, table or detail component | NiceGUI has no reason to reproduce Streamlit's catch-all dispatch. |
| `st.markdown` | `ui.markdown` | Preserve sanitisation; use text for untrusted clinical snippets. |
| `st.json` | `ui.code(..., language='json')` or read-only formatted text | Prefer read-only metadata over an editable JSON editor. |
| `st.metric` | Composite `ui.card` + label/value + optional `ui.badge` | No claimed direct metric equivalent. Distinguish global counts and filtered counts. |
| `st.info`, `st.warning`, `st.error`, `st.success`, `st.sidebar.info` | Persistent card/label/icon or `ui.element('q-banner')`; `ui.notify` for transient acknowledgement | Persistent stale-input/conflict/safety notices must not disappear as toasts. |
| `st.spinner` | `ui.spinner` | Activity indicator only. |
| `st.progress` | `ui.linear_progress` + text label | Preserve meaningful progress text. |
| `st.status` | Composite status card + spinner/progress + `ui.log`, or `ui.notification` | No direct context-manager equivalent; keep final result/errors available. |

References: [text elements](references/nicegui/section_text_elements.md), [layout/notifications](references/nicegui/section_page_layout.md), [LLM reference](references/nicegui/llms.md).

## 5. Every current form: keep, remove or redesign?

There are eight `st.form` call sites. The document forms are instantiated repeatedly for documents.

| Current form / source | Why a boundary exists now | Proposed interaction without a Streamlit form |
|---|---|---|
| `inception_api_form`, `gui/sidebar.py` | Collect connection/export settings before request | Inputs update a connection draft. Keep explicit fetch/export command; never contact INCEpTION on typing. |
| `sanitization_suggestion_settings_form`, `gui/sanitization_check_tab.py` | Source explicitly says it avoids rerunning for every checkbox/threshold edit | **Remove Apply suggestion settings.** Update validated settings directly, show changed-since-generation status, and retain Generate suggestions as a separate command. |
| `concept_rules_form`, `gui/concept_rules.py` | Batch rule editor and submit scan | Edit rules directly; retain **Apply rules to review**, validating a complete snapshot before scanning. Keep import/export and Clear pending decisions separate. |
| `concept_rule_review_form`, same file | Submit Apply checkboxes | Commit each validated Apply change into staged review state. Remove **Save rule decisions**. |
| `single_choice_form_*`, `gui/sanitization_run_tab.py` | Batch per-document checkbox edits | Commit row actions directly. Remove **Save single/no-choice selections**; retain an explicit **Mark document reviewed** action with the same completion/protection semantics. |
| `manual_choice_form_*`, same file | Batch candidate/action selections | Select candidate/action in a persistent detail panel, then stage through a clear action or validated control commit. Remove technical **Save choices**; keep **Use candidate** and **Mark document reviewed** if they express deliberate review intent. |
| `sanitization_conditions_form`, same file | Batch automatic-condition configuration and apply | Thresholds update the draft/assessment only; retain **Apply Conditions** and **Undo Automatic Conditions**. Never run selection automatically when thresholds change. |
| `inception_pipeline_form`, same file | Collect deployment settings and explicit remote-write opt-in | Live validation/readiness display plus explicit deployment button. Keep dry-run default, remote-write consent and final confirmation for real upload. |

### Meaning of “saved” in the replacement UI

Use three distinct concepts:

- **Input draft:** e.g. an incomplete source SCTID while typing; not yet a valid rule.
- **Staged review state:** validated decisions acknowledged by the server, not yet written to a ZIP or INCEpTION.
- **Exported/applied artifact:** created only by an explicit export/sanitization/deployment command.

Removing form Save buttons must not imply restart-safe autosave. Initial implementation can retain existing JSON export/import persistence. Label feedback **“Staged in this session”**, not simply “Saved”, unless durable storage is implemented.

Marking a document reviewed is not the same as approving every proposal. A human explicitly keeping an annotation unchanged must still be distinguishable from an untouched/unresolved row. Preserve manual-protection/provenance rules currently associated with saving forms by recording intentional decisions explicitly in the model.

## 6. Proposed review workspace

```text
Project / HDF5 / shared annotator scope / policy-or-release indicator
Check policy | Suggest | Review & apply

Review & apply
┌────────────────┬─────────────────────────────┬────────────────────────┐
│ Documents      │ Findings / staged decisions │ Selected finding       │
│ search         │ sortable/filterable grid    │ covered text + context │
│ review counts  │ SCTID | text | status       │ FSN + rationale        │
│ focus filter   │ action | replacement        │ candidate grid/search  │
│ selected doc   │                             │ Use candidate / action │
└────────────────┴─────────────────────────────┴────────────────────────┘
Staged/session indicator | Mark document reviewed | Download decisions
Local sanitized ZIP / INCEpTION deployment remain explicit commands
```

Use ordinary `ui.row`/`ui.grid` or nested `ui.splitter` for resizable panes. Keep candidate details on the same screen instead of opening an additional fragment/expander above an unrelated form. On narrow displays, put details in a dialog or switchable panel; do not force three unreadably narrow columns.

**Recommended first prototype:** read-only findings grid + candidate grid + ordinary action controls in the detail pane. Introduce inline action editing after edit synchronisation is proven. A four-way action selector (Keep / Replace / Delete / Needs manual edit) is a useful design candidate to avoid contradictory checkboxes, but its adapter must preserve existing write-back precedence and the distinction between unresolved and intentionally kept decisions. Concept-rule `clear_id` is an additional distinct action and must not be confused with deleting the annotation.

Potential later enhancement: `ui.keyboard` shortcuts for next unresolved finding and explicit staging actions. Ignore shortcuts while typing and provide equivalent visible buttons. See [keyboard API](references/nicegui/keyboard.md).

## 7. Event/state contract for an implementation

Suggested model fields, not a new required backend schema:

- Selected document/finding/candidate IDs.
- Display filters, sort and column state.
- Draft settings and generation-settings snapshot.
- Rule definitions plus last-applied rule/input signature.
- Validated staged decisions with manual/automatic provenance.
- Document review progress, existing automatic-condition undo snapshot.
- Dirty/invalid/pending-edit state and source artifact identity.

Keep them in a per-page/session model. `app.storage.user` persists on the server and is shared across that user's tabs; it is not equivalent to an isolated Streamlit review session. Prefer per-tab state if parallel projects must not interfere. Do not put clinical text or credentials in persistent storage by accident.

Typical event flow:

```text
User commits a cell/control edit
  → extract record ID + changed field + proposed value
  → validate against authoritative row/candidate set and current input signature
  → reject with visible reason, or update staged decision + provenance
  → update only affected row, counts, detail controls and review flag
  → acknowledge session staging; do not rerender the whole workspace

User clicks export/apply
  → finish active editors and reconcile pending changes
  → require valid acknowledged state; recheck stale/conflict guards
  → take an immutable decision/settings snapshot
  → invoke existing export/apply workflow explicitly
```

NiceGUI forwards grid events through `.on(...)`; event payloads can contain cyclic references, so request only serialisable fields. Cell-change handlers, an edit-flush barrier and event revision handling need a browser prototype. Do not assume that awaiting `stopEditing` alone proves every server-side validation callback has completed.

Update loops need care: programmatic grid/model updates can trigger more events. Make handlers idempotent and distinguish synchronisation from intentional human edits so automatic provenance is not overwritten accidentally.

## 8. Preserve these safety and presentation invariants

- The shared annotator selection remains processing scope, not merely a grid filter. Scope changes retain current invalidation/blocking behaviour.
- Changing display filters never changes stored findings or exported reports.
- Changed source artifacts/settings visibly mark generated results stale; do not silently reinterpret existing suggestions.
- Rules can stage decisions without generic suggestions; rule-only review remains supported.
- Rules do not chain, and manual decisions/explicit keeps remain protected.
- Diagnostic candidates remain non-selectable; tied BM25 candidates are not preselected.
- Changing automatic-condition settings does not clear or recompute existing decisions until an explicit action. Existing Undo semantics remain intact.
- Preserve inclusion/exclusion terminology, heuristic warnings, policy-override permission versus actual override, and visible stale/conflict messages.
- Downloads do not recalculate findings or regenerate suggestions.
- Staging a decision changes no CAS/project file. Local output is separate from the original ZIP. Remote writes remain explicit and opt-in.

## 9. Prototype acceptance checklist

### Tables and direct interaction

- [ ] Sort/filter a grid, edit a row, and confirm the intended annotation changes—not the row at its old position.
- [ ] Selection, scroll position, column widths and focus remain stable during unrelated edits and counter updates.
- [ ] Test long FSNs, long covered text, missing values, duplicate findings and numeric ties.
- [ ] Verify numeric score sorting and string SCTIDs, including IDs unsuitable for JavaScript numeric representation.
- [ ] Changing filters never drops staged decisions; exporting includes the complete in-scope review state.
- [ ] Candidate preview does not approve; a deliberate selection/stage action does not write CAS.
- [ ] Press Enter/Tab/Escape, click another document, and click Download while a cell is editing: no last edit silently disappears.
- [ ] An invalid edit is visible and cannot leak into exported decisions; programmatic synchronisation does not create human provenance.

### No-form workflow

- [ ] Every ordinary checkbox/select/threshold change updates the relevant view without a full workspace rebuild.
- [ ] There is no Save/Apply-settings button whose only purpose is rerun avoidance.
- [ ] Apply rules, Apply Conditions, Undo, Generate, sanitization and deployment still require their explicit commands.
- [ ] Intentional Keep and Mark reviewed preserve existing manual-protection/completion semantics.
- [ ] File import/tab changes do not reset unrelated pending choices or restore discarded choices.
- [ ] Two browser tabs/projects do not share review decisions accidentally.
- [ ] Session staging, durable export and remote application have clearly different feedback.

### Scope and limits

- [ ] Compare exported decisions and resulting offline artifacts with the current GUI for the same deliberate choices.
- [ ] Validate safety guards independently of visible/hidden/disabled client controls.
- [ ] Check keyboard accessibility, non-colour status cues, browser zoom and narrow layouts.

## 10. Suggested implementation order

1. Pin and validate a compatible Python/NiceGUI environment. The project is now configured for Python 3.11.x, matching NiceGUI 4.0.0's Python 3.11+ minimum. The `nicegui` project extra installs NiceGUI 4.0.0 alongside Streamlit in `.venv-py311`. The 100-package cross-platform lock updates certifi/idna/Pygments only among retained versions (99 installed on Windows). Full regression: 280 passed, 3 pre-existing GUI-default failures, 2 warnings. Dependency consistency and a real shared-launcher HTTP 200 startup/page check pass. Browser interactions and backend adapters still need validation. The preserved 3.9 environment is untouched.
2. Prototype the suggestion overview and candidate browser against **synthetic data or explicitly approved fixtures**. Do not load clinical project contents just to build a visual mockup.
3. Establish stable row identities and a framework-independent staged review model, reusing existing decision validation/serialisation helpers.
4. Migrate review controls and prove edit/selection/provenance correctness before removing the corresponding Streamlit Save buttons.
5. Replace settings forms with bound controls and explicit domain commands; migrate rule editor, metadata and file-source selector.
6. Retain the existing Streamlit app until no-form interaction and export equivalence are verified.

No backend algorithm changes are required by this plan. Existing blocking calls may need a thin execution adapter so they do not freeze NiceGUI's shared UI event loop; that is frontend integration plumbing, not a scoring/performance redesign.

### First increment implemented

- Direct `gui/nicegui/app.py` entry point plus shared launcher `--frontend nicegui`; Streamlit remains the default and Docker behavior is unchanged.
- NiceGUI 4.0.0 pinned in the project's optional `nicegui` extra; standalone `requirements.txt` retains the reference pin. Both frontends are installed in the same `.venv-py311`, with real startup/page construction verified and 280 regression tests passing (3 baseline GUI-default failures remain).
- Three workflow tabs; Community AG Grid findings and candidate preview with stable IDs, literal string SCTIDs, numeric scores, competition-rank ties and diagnostic-only targets.
- Per-page presentation state; read-only grids and in-place detail updates. Selection is navigation, not decision approval.
- Initially synthetic in-memory data only. The subsequent read-only import increment below adds explicitly uploaded suggestions JSON; project/HDF5 processing, shared-scope controls, rules, staging and export/deployment remain disconnected, with action buttons disabled.
- Offline state/bootstrap/dispatch tests plus actual loopback server/page smoke check. Browser JavaScript/visual interaction and backend adapter integration remain open prerequisites before enabling real workflows.

### Read-only suggestions import implemented

- Upload up to 50 MiB through **Review & apply → Load suggestions JSON**; existing backend reader/schema used unchanged. Full parsed suggestions and metadata retained server-side.
- Inherit saved annotator scope without broadening; keep original unfiltered suggestion indices. No HDF5 validation, retrieval, scoring, processing or staging is invoked.
- Snapshot/index IDs for findings; additional role/ordinal IDs for candidates. Duplicate findings/SCTIDs/channels are not merged, context stays non-selectable/unranked, saved proposals are not preselected, and stale events are rejected.
- Preserve saved scores/order, competition ties, rationale, text/FSNs/spans, ignored state, proposed targets, counts, retrieval limits and candidate evidence. Use text rendering only and avoid echoing content in import errors.
- Atomic imports and per-page state; invalid/unreadable/oversized files retain the previous preview. Worker parsing with revision guards prevents late uploads overriding newer imports or explicit demo reset. No application persistence/export; framework upload spooling may occur.
- 67 focused tests pass. Real local NiceGUI multipart upload verified the Alice-scoped synthetic fixture with original indices and preservation after an invalid upload. No real clinical project or external service was used; owned test server stopped. Full-suite and browser/visual interaction checks were not rerun for this increment.

### Socket.IO transport boundary verified

HTTP-only page/upload smoke checks did not exercise a live browser connection. Follow-up testing reproduced an Engine.IO `REQUEST_METHOD` KeyError for an initial ASGI disconnect and mixed-case response headers causing duplicate gzip compression of larger polling updates through Starlette. A mount-local application guard now handles initial disconnects and ASGI response-header casing, preserving healthy frames, bodies, compression and downstream errors. No installed SDK patch or dependency downgrade is used.

61 focused checks pass, including actual Engine.IO and Starlette gzip regressions. Real polling and WebSocket clients completed NiceGUI handshakes, scope-aware synthetic JSON upload, live UI updates and invalid-upload feedback without ASGI errors. Owned loopback servers stopped; no clinical/external-service inputs. Full-suite and visual/browser-JavaScript checks were not rerun for this follow-up. Restart the server to apply the guard.

## 11. Sources and local references

### Downloaded NiceGUI documentation

Twenty-one targeted pages are stored under [`references/nicegui/`](references/nicegui/README.md), including the API references for AG Grid, tables, inputs, selectors, uploads/downloads, layout, bindings, refreshable UI, events and storage. The [manifest](references/nicegui/manifest.json) records URLs, retrieval time, content types, byte lengths and SHA-256 hashes. Original upstream documentation remains attributed to NiceGUI/Zauberzeug and its contributors; this is a local reference snapshot, not our own API specification.

Refresh explicitly with `uvx --offline python scripts/download_nicegui_docs.py` when a cached Python runtime is available. The downloader uses only the standard library but **does access the network** and overwrites the selected snapshot files. It does not install NiceGUI or fetch the entire documentation website.

### Application source inspected

`gui/app.py`, `gui/policy_tab.py`, `gui/sanitization_check_tab.py`, `gui/sanitization_run_tab.py`, `gui/concept_rules.py`; file-source/sidebar/download usage was inventoried by source search. Source anchors are function/form names rather than fragile line numbers.

### Local OKF consulted

Relative to the application project:

- `okf/snomed-post-processing/index.md`
- `okf/snomed-post-processing/interfaces/gui.md`
- `okf/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md`

These informed scope, review/provenance and write-back invariants; source code was used to identify the actual widgets and form boundaries.
