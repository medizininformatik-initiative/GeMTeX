# User guide: interpreting results and warnings

This companion to the [README](../README.md) collects detailed explanations without
expanding the main setup and workflow instructions.

## Contents

- [Workspace frontend](#workspace-frontend)
- [SQLite instead of an INCEpTION project](#sqlite-instead-of-an-inception-project)
- [Masked suggestion overview download](#masked-suggestion-overview-download)
- [Review keyboard navigation](#review-keyboard-navigation)
- [Resizing tables](#resizing-tables)
- [Document overview in review](#document-overview-in-review)
- [Candidate row colors](#candidate-row-colors)
- [Review summary counts](#review-summary-counts)
- [Exclusion-list findings without replacements](#exclusion-list-findings-without-replacements)
- [Diagnostic candidates](#diagnostic-candidates)
- [FSN postfix exclusions](#fsn-postfix-exclusions)
- [SNOGIT retrieval limits](#snogit-retrieval-limits)
  - [What the three limits mean](#what-the-three-limits-mean)
  - [Term rows, hits and final candidates](#term-rows-hits-and-final-candidates)
  - [What to do when a limit is reported](#what-to-do-when-a-limit-is-reported)

## Workspace frontend

Launch the default navigation workspace from the standard project environment:

```bash
uv run src/snomed_post_processing/gui/app.py --show
```

The project-authored shell adds a responsive header, collapsible workflow navigation,
bordered work surfaces and a shared right-hand settings drawer around the **same**
NiceGUI workflow. The navigation and three workflow tabs select the same persistent
panels; switching stages does not start processing, replace review, approve changes
or discard pending choices. **Inputs** opens the shared drawer from every stage.
Both annotator selectors display selected names as chips; their dropdowns show checked
icons and highlighted rows. Clearing all inclusion names still means **all annotators**,
unless exclusions restrict that scope. After saving review choices for a ZIP/API project,
use **3. Review & apply → Local ZIP write-back → Run sanitization** to create and download
a separate sanitized project ZIP. The selected ZIP filename must match the source recorded
by the review; the original source is never modified and no remote request is made.

On narrow screens, the menu button toggles navigation. Review remains bound to its
loaded artifact rather than the drawer's current source settings. JSON/Markdown and
masked CSV downloads behave as in the standard NiceGUI frontend. Reload still loses
in-memory state; download artifacts and decisions before leaving.

No login, account database, migrations, demo data, PWA/offline cache or additional
processing capabilities are enabled. This shell is not a security boundary.
The workspace is the default frontend. Use `--frontend streamlit` for the previous
Streamlit UI or `--frontend nicegui` for the plain NiceGUI shell. The workspace uses
system fonts and project-authored CSS without external asset fetches.
See the [workspace provenance](../src/snomed_post_processing/gui/workspace/PROVENANCE.md).

## SQLite instead of an INCEpTION project

Both frontends accept **Annotation source → Annotation store (SQLite)** instead of
an INCEpTION project ZIP/API source. The selected HDF5 remains the terminology and
policy source; SQLite supplies the annotations, documents, annotators and text.

1. Select a closed, checkpointed **schema v2** database using Upload, Data directory
   or Server path. For a large database outside `data`, use Server path.
2. Click **Inspect SQLite scopes**, then select **SQLite export / view**. A sole
   view kind is selected automatically. Combined exports/views are allowed only
   when each document/annotator identity is unambiguous; otherwise select a single
   export/view. Conflicting text for one document name is also rejected.
3. Select annotators and exact stored layer names, then **Run policy check**.
   Continue with suggestions, concept rules and review as usual; no ZIP/API is needed.

Annotation occurrences are preserved even when their payloads are deduplicated in
SQLite. Stored `sctid` values are used directly: ID-feature/prefix settings apply
only to project input. Stored FSNs/activity flags do not override the selected HDF5.
SQLite policy checking matches exact stored layer names rather than expanding
inherited types, even when optional CAS/type-system preservation is enabled. A requested ignore-overlap layer absent from the selected
data causes an explicit error. If document text is missing, full context is unavailable;
covered text and saved snippets remain usable.

The database is opened read-only, with no migration, updates or WAL/SHM creation.
Live databases with pending WAL content are rejected. Findings and suggestions retain
`store_scope` and source-file provenance in metadata; existing artifact formats remain
unchanged. Changing inputs does not run analysis or replace loaded review decisions.
For later INCEpTION review, create a **new** store with `build-annotation-store --store-cas`.
This optional mode preserves complete JSONCAS/XMI, full document text and project
configuration. Identical external type systems are stored once by SHA-256 and referenced;
different definitions remain separate. It retains all original features/layers, not
just extracted SNOMED annotations, and therefore adds sensitive clinical data and storage.
Existing stores are not upgraded.

Choose a **single export/view scope before generating the review**. Streamlit then
enables its normal sanitization/deployment controls for preserved CAS, restoring a
temporary project and the original ID feature/prefix automatically. Local sanitized
ZIPs retain excluded annotators unchanged; remote artifacts omit them. NiceGUI offers
**SQLite CAS restoration / INCEpTION review → Download INCEpTION review package (offline)**
after saving choices: extract it and follow its explicit deployment instructions.
No remote calls occur during NiceGUI preparation. If the export lacked project
configuration, select a compatible project-template ZIP. Stores without preserved CAS
remain review-JSON-only.

For a standalone restoration, use `restore-annotation-store-cas --store STORE.sqlite
--store-scope 1:annotation --output restored-project.zip`. This is a JSON/XMI workspace
for the shell/artifact workflow, **not a native full-project backup**: no Java `.ser`
files are generated. Restoring never edits the database. Live INCEpTION import/review
validation remains outstanding.

## Masked suggestion overview download

In Streamlit's **Suggest policy sanitization → Suggestion overview**, or NiceGUI's
**2. Suggest** results, use **Download masked overview CSV** to export all overview rows with only the
**Document** and **Annotator** columns pseudonymized. Repeated names get consistent
numbered aliases within that table (`document-1`, `annotator-1`, etc.). The aliases
are assigned by first appearance and are not shared with the masked policy report.

All other columns remain unchanged. NiceGUI exports document, annotator, source code,
status, replacement code, candidate count and covered text; Streamlit's richer overview
also includes offsets, candidate summaries and reasons. NiceGUI exports the loaded
artifact's scoped rows, for both generated and restored suggestions, regardless of
grid sorting/filtering. Stale generated results cannot be downloaded. **This is not full anonymization:** names may still
appear in free text. The UTF-8 CSV includes a BOM for spreadsheet compatibility;
import SCTID columns as text to avoid spreadsheet number conversion. It does not
modify the displayed table, saved suggestions or review decisions, and is not an
artifact for restoring review. Sorting the table in the browser does not change
the source row order used for export.

## Review keyboard navigation

In either NiceGUI shell, while **Review & apply** is active:

- **A / D**: inspect the previous / next finding in the current document.
- **W / S**: open the previous / next document.

Shortcuts use the respective table's current **filtered, sorted order**, without
wrapping at either end. With no visible finding selected, D starts at the first
visible finding and A at the last; the same first/last convention applies when the
current document is filtered out. Empty filtered tables do nothing. Finding
navigation highlights/reveals its row; document navigation clears inspection.

Use unmodified letters: shortcuts ignore Ctrl/Alt/Meta/Shift, held-key repeats,
and typing while inputs, selects, buttons or textareas have focus. **Arrow keys
retain normal table/input behavior.** Navigation never applies candidates, marks
documents reviewed, saves choices or changes export scope. Pending/saved decisions
remain intact. A delayed navigation response is ignored after leaving Review,
loading another artifact or changing the active document/finding.

## Resizing tables

In both NiceGUI shells, drag a table's **lower-right corner** up or down to resize
its height in desktop browsers. This applies to policy findings, the rule editor,
suggestion overview and all four review tables. Drag column-header borders to
resize individual column widths; tables retain their full available page width.

The document overview starts at a minimum **320 px**, enough for at least four
rows below headers/filters at the default styling. Other tables can shrink to
160 px. Resizing changes presentation only: it does not alter filters, selection,
review decisions or export scope. Heights survive normal grid data refreshes but
are not persisted to settings/artifacts and reset on page reload. Native drag
handles may not be available on touch browsers.

## Document overview in review

Both NiceGUI shells replace carousel dots with a sortable, filterable **Documents
in loaded artifact** table. Filter the Document column to find a name, or filter
by saved review status/pending edits, then click a row to open that document. The
current row is blue and a position label shows its index in the original artifact
order. The table scrolls rather than showing an indistinguishable dot per document.

**Findings** counts all findings for the document in the artifact scope. **Saved
document review** reflects the explicit saved document flag, not whether every
finding has an accepted replacement. **Pending edits** counts pending annotation
choices/actions plus a pending document-review flag; concept-rule edits remain
listed separately. Save and Discard refresh these indicators.

Navigation clears inspection but preserves pending/saved choices. Table filtering
and sorting do not change review/export scope or approve anything. Only documents
represented by the loaded scoped findings appear—not unrepresented project files.

## Finding review actions

In **Review & apply**, right-click a finding to stage one mutually exclusive action:
**Accept Suggestion**, **Remove concept ID**, **Delete**, **Manual Review**, or
**Keep Original**. Removing the concept ID preserves the annotation, span, type,
literal and other features; write-back clears only the ID feature configured in
Inputs/review metadata. Delete removes the annotation instead. Save choices before
exporting or running local write-back. Imported protected actions and concept-rule
reservations remain read-only in the generic menu.

## Candidate row colors

In **Review & apply**, both NiceGUI-based shells distinguish inspection from an
actual replacement choice:

- **Pale yellow:** a selectable candidate matching the **Saved proposed SCTID**.
  This is a saved suggestion, not an accepted or automatically selected choice.
- **Blue:** the candidate currently being inspected. Clicking never stages Apply.
- **Green:** the chosen replacement. **Review selection** says **pending Save** or
  **saved**; green alone does not mean it has been saved or written to CAS.
- If the green row is also being inspected, it has a **blue left edge** and an
  additional **inspecting** label. Green takes priority over blue, then yellow;
  proposal status remains in the text label when another color takes priority.
  Other rows say **Not chosen**. A duplicate proposed SCTID can mark multiple
  selectable evidence rows yellow; it never marks diagnostic-only rows or changes
  the existing requirement to explicitly choose a target.

Apply, Save, Discard, Keep, deletion/manual-review actions and restoring decisions
refresh the indicator. Navigating away clears inspection, but not the underlying
pending/saved choice. Diagnostic candidates can be inspected but never shown as
chosen. Exact candidate identity/evidence distinguishes duplicate SCTIDs. For
older decisions without an exact candidate ordinal, a unique selectable code can
be highlighted; ambiguous duplicate-code candidates are not guessed.

## Review summary counts

In Streamlit's **Review & apply**, the three candidate categories partition
**Suggestions**:

- **Single/no-choice:** a selectable replacement without a per-row choice form.
- **Need choice:** selectable candidates routed to the per-row choice form,
  including rows where a choice has already been saved.
- **No replacement:** no selectable replacement candidate is available.

An unselected tied result counts only under **Need choice**, not **No replacement**.
These are candidate categories, not approval or pending-review counts. The total
covers in-scope generic suggestions after concept-rule reservations; explicit rule
decisions are shown separately. **Documents** counts documents, not suggestions,
and is not part of the sum.

## Exclusion-list findings without replacements

The status **`exclusion_list_no_replacement`** means no selectable replacement
suggestion was generated for an exclusion-list finding; **manual review is required**.
It does not mean BM25 was necessarily disabled or never attempted.

- The initial structured resolver leaves exclusion-list findings unresolved.
- When BM25 suggestions for exclusion-list findings are enabled, a qualifying
  match changes the status to a BM25 suggestion or ambiguity. Other exclusion-list
  findings can therefore have suggestions in the same run.
- If BM25 finds no acceptable match or fails score thresholds, the no-replacement
  status remains and the reason explains the unsuccessful BM25 attempt.

This identifier replaces `blacklisted_no_auto_sanitization`. Older suggestions
files containing that identifier must be regenerated; no automatic conversion is
performed. Regeneration creates a new suggestions snapshot, so previously exported
reviewed decisions may no longer match it. Keep existing paired artifacts backed up.

## Diagnostic candidates

**Diagnostic candidates** are matches retained for explanation, **not selectable
replacements**. Examples include historical targets that fail the selected target
requirements, ancestors outside the configured distance limits, and BM25 matches
below score or lexical-overlap thresholds.

They help explain why no replacement was suggested or why other candidates were
retained. They do not count toward the selectable candidate count. After changing
relevant settings, regenerate suggestions; existing diagnostics are not
automatically promoted to selectable candidates.

## FSN postfix exclusions

In **Advanced suggestion settings → Excluded FSN postfixes**, each row has an
**Exclude** checkbox and a **Postfix** value. Only `action` is selected by default;
the other presets are available but unchecked. Uncheck every row to disable
postfix exclusion. In Streamlit, add/delete custom rows in the table and submit
**Apply suggestion settings**; in NiceGUI, use **Add postfix** or a row's remove
button. Editing settings never starts generation or changes existing review choices.

These are recurring **classification-like suffixes**, not guaranteed meaningless
text. They are candidates for reducing repetitive lexical evidence, not a general
recommendation to discard concept distinctions.

| Postfix | Exclude by default | Active concepts in local scan | Verified example FSN | SCTID |
|---|---|---:|---|---|
| `action` | Yes | 324 | Evaluation - action (qualifier value) | `129265001` |
| `unit of product usage` | No | 58 | Applicator - unit of product usage (qualifier value) | `1641000175108` |
| `dosing instruction fragment` | No | 35 | At - dosing instruction fragment (qualifier value) | `420246001` |
| `dosing instruction imperative` | No | 25 | Apply - dosing instruction imperative (qualifier value) | `417924000` |

Counts are from the read-only scan of
`data/gemtex_snomedct_codes_release20260401_policy20240401.hdf5`, not a global
SNOMED count or a count of policy-eligible replacements. All active matches for
these four postfixes had the semantic tag `qualifier value` in this snapshot.

Postfixes such as `non-surgical`, `open`, `closed`, and `normal` are **not**
presets: removing them can erase clinically meaningful distinctions. Even the
optional presets above can carry useful context; different concepts may become
lexically indistinguishable after stripping. BM25 similarity is not clinical
replacement confidence.

Matching removes the trailing semantic tag first, then inspects the last ASCII
hyphen surrounded by whitespace on **both sides**. Only a complete,
case-insensitive match to a selected literal postfix is removed, and only if a
nonempty first part remains. For example, selected `action` turns
`Evaluation - action (qualifier value)` into `Evaluation` for matching, while
`Evaluation-action (qualifier value)` remains `Evaluation-action`.
Ordinary internal hyphens remain intact; tokenization itself does not change.

The same cleanup applies to FSN index text and the source-FSN part of queries,
not annotation text or SNOGIT terms. Full FSNs, SCTIDs, semantic tags and the
separate tag boost remain unchanged. Selected postfixes are recorded in suggestion
metadata as `settings.bm25_excluded_fsn_postfixes`, with duplicates removed and
case/outer whitespace normalized. Changed settings require explicitly regenerating
suggestions, not rebuilding the processed SNOGIT cache. Standalone resolver/API and
CLI defaults retain postfixes; programmatic callers can opt in through
`excluded_fsn_postfixes`. The GUI default is `action` only.

## SNOGIT retrieval limits

SNOGIT supplies additional lexical evidence for BM25 suggestions. These search
limits bound processing time and memory; they are **not clinical confidence
thresholds** and do not relax inclusion/exclusion-list or active-target checks.

The search has several stages:

```text
Query tokens
  → collect matching SNOGIT term rows (postings and candidate-row limits)
  → score the accepted rows with BM25
  → retain top term hits (hit limit, with boundary ties)
  → apply target/score gates and merge evidence by SCTID
  → retain final suggestion candidates (a separate, tie-aware limit)
```

### What the three limits mean

| Warning | What is limited | Current default and behaviour |
|---|---|---|
| **SNOGIT postings limit** | Matches for one query token. A posting identifies an indexed term row containing that token. | If the token occurs in more than **250,000 term rows**, skip the entire token, rather than taking its first 250,000 matches. |
| **SNOGIT candidate-row limit** | The combined pool of distinct term rows accepted across query tokens. | If adding a token would expand that pool beyond **100,000 rows**, skip that entire token. Tokens are processed from rarest to most common, so more selective tokens are considered first. |
| **SNOGIT hit limit** | The scored term matches returned from SNOGIT, before final target filtering and SCTID deduplication. | Suggestion generation requests **`max(20 × requested candidate count, 50)` hits**. Lower-scoring hits are omitted; score ties at the boundary are retained subject to a safety cap. |

The first two limits apply **before scoring**. A skipped token contributes neither
new matching rows nor score contributions to rows already accepted through other
tokens. Consequently, these limits can affect both coverage and ranking. The hit
limit applies **after scoring** and trims the returned results.

The postings and candidate-row defaults are internal search safeguards, not
separate GUI controls. The requested final candidate count influences the hit
budget, but does not change either of those two safeguards. The low-level SNOGIT
search function itself defaults to 50 hits; the generation pipeline supplies the
larger budget shown above.

Boundary ties use full-precision scores, not rounded display values. Tie expansion
is capped at **`max(requested SNOGIT hit budget, 2,000)` term hits**. If that cap
cuts a tie group, an additional **SNOGIT tied-hit limit (N)** warning records the
actual cap. A hit-limit warning may appear alongside it.

### Term rows, hits and final candidates

These counts are different:

- A **term row** is an indexed SNOGIT term entry, not a project annotation or a
  unique SNOMED CT concept. Multiple terms can refer to the same SCTID.
- A **hit** is a term row returned with a BM25 score.
- A **final candidate** is a distinct target SCTID remaining after target/score
  checks and evidence merging. SNOMED FSN evidence may also contribute.

For example, requesting **5 final candidates** gives SNOGIT a budget of **100 term
hits**, potentially more when boundary ties are retained. Several hits may share
an SCTID, and some may fail target or score checks, so this does not guarantee
five final candidates. The final candidate limit separately retains cutoff ties,
subject to its own safety cap.

### What to do when a limit is reported

A warning means **retrieval was incomplete**, not necessarily that a displayed
candidate is wrong. Saved counts describe the retrieved/saved evidence, not the
complete number of possible matches.

- Review the available candidates and their evidence manually; do not interpret
  the first displayed match as a guaranteed best match over the complete index.
- Any recorded retrieval limit blocks the automatic BM25-acceptance heuristic.
  Manual choices remain available. This does not introduce automatic acceptance
  into frontends where that workflow is not connected.
- Loading a saved artifact cannot recover omitted matches. Regenerating with the
  same inputs and limits may produce the same warning; more complete retrieval
  requires investigating the limiting search stage first.
- Changing the requested candidate count can increase the hit budget, but does
  not fix postings/candidate-row omissions. Increasing internal safeguards can
  increase memory use and runtime and is not a confidence improvement.

These SNOGIT limits concern its evidence channel, not the separate SNOMED FSN
search. A limit on either channel still means the combined evidence is incomplete.

Implementation references: [SNOGIT search](../src/snomed_post_processing/sanitization/snogit_sidecar.py)
and [BM25 generation/merging](../src/snomed_post_processing/sanitization/semantic_bm25.py).
