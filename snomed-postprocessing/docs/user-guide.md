# GUI user guide

This guide covers the default NiceGUI workspace and the retained Streamlit fallback.
For installation and CLI usage, see the [main README](../README.md).

## Contents

- [Workspace frontend](#workspace-frontend)
- [Core workflow](#core-workflow)
- [Deploying a reviewed project to INCEpTION](#deploying-a-reviewed-project-to-inception)
- [SQLite instead of an INCEpTION project](#sqlite-instead-of-an-inception-project)
- [Review workspace](#review-workspace)
  - [Finding review states](#finding-review-states)
- [Masked suggestion overview download](#masked-suggestion-overview-download)
- [Suggestion warnings and diagnostics](#suggestion-warnings-and-diagnostics)
- [FSN postfix exclusions](#fsn-postfix-exclusions)
- [SNOGIT retrieval limits](#snogit-retrieval-limits)

## Workspace frontend

Launch the default NiceGUI workspace from the repository root:

```bash
uv run src/snomed_post_processing/gui/app.py --show
```

The public frontend choices are:

```bash
--frontend nicegui     # default workspace
--frontend streamlit   # previous UI
```

NiceGUI listens on `127.0.0.1:8080` by default. Use `--port`, `--host`, or
`--show` as needed. **Inputs** opens the shared settings drawer from every workflow
stage. Changing tabs does not start processing, approve findings, or discard review
choices.

Inputs, credentials, review state, and generated results are page-local. Restarting
or using development reload discards them, so download decisions and output artifacts
before leaving. The source ZIP, SQLite database, HDF5, cache, and project template are
always treated as read-only inputs.

Annotator scope applies across checking, generation, rules, review, write-back, and
deployment. Empty inclusion means all annotators; exclusions take precedence.

## Core workflow

1. **Check policy**
   - Select a project ZIP, INCEpTION API export, or SQLite annotation store.
   - Select the SNOMED HDF5, annotation layers, ID settings, and annotator scope.
   - Run a policy check or restore a compatible CriticalFindings JSON artifact.
2. **Suggestions & rules**
   - Generate suggestions from the current findings, or restore suggestions JSON.
   - Optionally configure SNOGIT/BM25 and explicit concept rules.
   - Use **Load in review (replaces review)** to hand generated or restored suggestions
     to the review stage. Generation alone does not replace review state.
3. **Review & apply**
   - Inspect findings and candidates, stage actions, and save choices.
   - Optionally apply guarded historical/BM25 automatic conditions; Undo affects only
     their automatic ownership, not later manual choices.
   - Download reviewed-decisions JSON before write-back or deployment.
4. **Prepare output**
   - Prepare a complete sanitized project ZIP and deployment artifacts.
   - Optionally upload them as a new INCEpTION project.

Restored artifacts retain their recorded scope and settings. Broader or incompatible
inputs are rejected instead of being silently combined. Failed or stale background
work does not replace the last valid result.

## Deploying a reviewed project to INCEpTION

After saving review choices, open **Review & apply → INCEpTION deployment**.

### Prepare offline

Select **Prepare deployment artifacts**. No INCEpTION connection or credentials are
required. Preparation validates the source/review binding and creates:

- a complete sanitized project ZIP for ZIP/API sources;
- a schema-only project shell;
- repaired CAS upload artifacts;
- preparation and deployment reports.

These files are frozen together; changing the source or review invalidates them.
Preparation never modifies the source or contacts INCEpTION.

### Upload remotely

Deployment uses a separate URL, username, password, annotation user, and TLS setting.
Connection testing is optional and read-only. To upload, provide the required
connection fields, confirm the operation, and select **Upload as new INCEpTION
project**.

Deployment always creates a separate project and never overwrites the source. If an
upload fails after project import, inspect INCEpTION before retrying; the new project
may already exist. Prepare fresh artifacts before another attempt. Disable TLS
verification only when the certificate cannot yet be trusted correctly.

## SQLite instead of an INCEpTION project

Select **Annotation source → Annotation store (SQLite)** to use a read-only schema-v2
annotation store instead of a project ZIP/API export.

1. Select a closed, checkpointed database. Live databases with pending WAL content
   are rejected.
2. Select **Inspect SQLite scopes**, then choose one export/view scope. Combined scopes
   are accepted only when document, annotator, text, and annotation identities remain
   unambiguous.
3. Select exact stored layer names and annotator scope, then continue with policy
   checking, suggestions, rules, and review.

SQLite supplies annotations, provenance, document text, and annotators. The selected
HDF5 remains authoritative for SNOMED policy, FSNs, and activity. The database is never
migrated or modified.

### Preserved CAS output

Ordinary schema-v2 stores are analysis/review-JSON-only. To support complete CAS
restoration, create a new store with:

```bash
build-annotation-store --store-cas
```

This preserves complete JSONCAS/XMI, document text, type systems, and available project
configuration. It therefore stores sensitive clinical data and can be substantially
larger.

Choose a single scope before generating the review. After saving choices, use the
SQLite restoration/offline-package control or the deployment preparation flow. If the
store lacks project configuration, provide a compatible project-template ZIP.
Excluded annotator CAS is omitted from remote deployment artifacts.

Standalone restoration is also available:

```bash
restore-annotation-store-cas \
  --store STORE.sqlite \
  --store-scope 1:annotation \
  --output restored-project.zip
```

The result is a JSON/XMI workspace, not a native Java `.ser` backup. Restoration never
edits the database.

## Review workspace

### Document and finding navigation

The **Documents in loaded artifact** table is sortable and filterable. Clicking a row
opens that document. Its finding count covers the loaded artifact scope; saved review
status is an explicit progress flag, not proof that every finding has a replacement.
Filtering and sorting change presentation only and never limit export.

#### Review keyboard navigation

While **Review & apply** is active:

- **A / D** — previous / next visible finding.
- **W / S** — previous / next visible document.

Navigation follows the current filtered and sorted table order and does not wrap.
Shortcuts are ignored while typing, when modifiers are pressed, or while another tab is
active. Navigation never stages or saves a decision.

#### Resizing tables

On desktop browsers, drag a table's lower-right corner to change its height and drag
column-header borders to resize columns. Heights survive normal data refreshes but reset
on page reload. Resizing affects presentation only.

### Finding review actions

Right-click a finding to stage one mutually exclusive action:

- **Accept Suggestion** — uses the saved proposed SCTID only when it uniquely matches a
  selectable candidate.
- **Remove concept ID** — preserves the annotation and clears only its configured ID
  feature during write-back.
- **Delete** — removes the annotation during write-back.
- **Manual Review** — preserves the annotation and adds a ManualReview marker.
- **Keep Original** — records explicit human review without changing the annotation.

Right-click a selectable candidate and choose **Apply** to stage that exact candidate.
Diagnostic candidates cannot be applied. Validated imported generic decisions remain
editable; concept-rule reservations remain read-only until revalidated through the rule workflow.

Use **Save choices** before downloading decisions or preparing output. **Discard pending
changes** restores the last saved state. Reloading the page is not a save operation.

### Finding review states

The **Review** column distinguishes pending edits, saved decisions, imported actions,
automatic choices, and concept-rule ownership:

| State | Meaning |
|---|---|
| **Unreviewed** | No saved human or automatic decision exists. |
| **Pending Keep / replacement / deletion / manual review / ID removal** | A local change is staged but has not been committed with **Save choices**. |
| **Saved Keep** | A human explicitly reviewed the finding and retained the original annotation. |
| **Saved replacement: SCTID** | A local or restored replacement is saved and remains editable unless another workflow owns it. |
| **Saved deletion / manual review / ID removal** | The special action was staged locally and saved; it remains editable in the current session. |
| **Imported deletion / manual review / ID removal** | The saved action came from reviewed-decisions JSON. It will be exported/applied and can be replaced with another finding action after import validation. |
| **Automatic historical condition / BM25 gap: SCTID** | A guarded automatic condition selected the saved replacement. |
| **Reserved by concept rule** | A concept-rule decision owns the annotation; change it through the rule Apply choices or clear/reapply the rules. |
| **Imported concept-rule decision (read-only)** | An imported rule decision is retained but cannot be edited as a generic finding action. |

An imported decision is not unreviewed: it remains part of reviewed-decisions export and
downstream write-back/deployment. Imported generic actions are editable after successful
identity/scope validation. Concept-rule decisions remain read-only because the rule workflow
owns and revalidates them separately.

### Candidate row colors

- **Pale yellow** — matches the saved proposed SCTID; it is not accepted automatically.
- **Blue** — currently inspected; clicking does not stage Apply.
- **Green** — chosen replacement; the row text distinguishes pending Save from saved.
- **Green with a blue edge** — chosen and currently inspected.

Exact candidate identity is retained, including duplicate SCTIDs from different evidence
channels. Diagnostic rows can be inspected but never appear as chosen.

### Review summary counts

In Streamlit, the generic suggestion summary partitions rows into:

- **Single/no-choice** — selectable replacement without a per-row choice form.
- **Need choice** — selectable candidates requiring an explicit choice, including saved
  choices.
- **No replacement** — no selectable replacement exists.

These categories sum to Suggestions. They describe candidate availability, not approval
or pending-review state. Documents is a separate document count.

## Masked suggestion overview download

**Download masked overview CSV** replaces only the Document and Annotator columns with
stable numbered aliases within that export. All other columns, including covered or free
text, remain unchanged.

This is therefore **not anonymization**. Names or identifying information may still
appear in text fields. The CSV covers the full scoped result, independent of displayed
sorting/filtering, and cannot be used to restore review state. SCTID columns should be
imported into spreadsheet software as text.

## Suggestion warnings and diagnostics

### Exclusion-list findings without replacements

`exclusion_list_no_replacement` means that no selectable replacement was produced and
manual review is required. BM25 may still have run but found no acceptable result.
Older artifacts using `blacklisted_no_auto_sanitization` must be regenerated; they are
not converted automatically.

### Diagnostic candidates

Diagnostic candidates explain discarded or insufficient evidence, such as inactive or
policy-ineligible historical targets, distant ancestors, or BM25 matches below the
configured thresholds. They do not count as selectable candidates and cannot be applied.
Changing settings requires regeneration; existing diagnostics are not promoted in place.

## FSN postfix exclusions

**Advanced suggestion settings → Excluded FSN postfixes** removes selected trailing
classification-like phrases from FSN text used for BM25 matching. It does not alter the
stored FSN, annotation text, SCTID, semantic tag, or SNOGIT terms.

The GUI defaults to excluding only `action`. Optional presets are:

- `unit of product usage`
- `dosing instruction fragment`
- `dosing instruction imperative`

These phrases can still carry meaning. Suffixes such as `non-surgical`, `open`, `closed`,
and `normal` are deliberately not presets because removing them can erase clinically
important distinctions. BM25 similarity is not clinical replacement confidence.

Matching is case-insensitive and requires a complete suffix after an ASCII hyphen with
spaces on both sides. For example, selected `action` changes
`Evaluation - action (qualifier value)` to `Evaluation` for matching, while
`Evaluation-action (qualifier value)` is unchanged. Unchecking every row disables this
cleanup. Changes require regeneration, not rebuilding the SNOGIT cache.

## SNOGIT retrieval limits

SNOGIT provides lexical evidence for BM25. Retrieval limits bound runtime and memory;
they are not clinical confidence thresholds.

| Warning | Meaning | Default behavior |
|---|---|---|
| **Postings limit** | One query token occurs in too many indexed term rows. | Skip that token above 250,000 rows. |
| **Candidate-row limit** | Accepted rows across query tokens would become too large. | Skip the token that would exceed 100,000 rows. |
| **Hit limit** | Lower-scoring term hits were omitted after scoring. | Request `max(20 × candidate count, 50)` hits and retain boundary ties within the safety cap. |
| **Tied-hit limit** | A very large boundary tie exceeded its cap. | Cap at `max(requested hit budget, 2,000)` term hits. |

A term row is an indexed SNOGIT term entry, a hit is a scored term row, and a final
candidate is a distinct SCTID remaining after target checks and evidence merging.
Several hits can map to one SCTID, and some hits may be rejected, so the hit budget does
not guarantee the requested number of final candidates.

Any retrieval-limit warning means evidence may be incomplete. It does not prove a shown
candidate is wrong, but it blocks automatic BM25 acceptance. Manual review remains
available. Regenerating with unchanged inputs and limits may reproduce the same warning;
increasing the requested candidate count changes the hit budget but does not resolve
postings or candidate-row omissions.

Implementation details are documented in the local
[SNOGIT/BM25 knowledge page](../okf/snomed-post-processing/workflows/snogit-bm25.md).
