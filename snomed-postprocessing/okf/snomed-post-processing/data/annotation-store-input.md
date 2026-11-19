# SQLite annotation store as project input

## Purpose

SQLite replaces the INCEpTION project as annotation data input in both frontends.
It is not an additional terminology store. The selected HDF5 remains authoritative
for policy, FSNs, activity and replacement eligibility. Existing engines and artifact
schemas are reused; there is no new processing engine or storage framework.

## Reader and schema

`src/snomed_post_processing/annotation_source.py` accepts schema v2 only and reads:

- `annotation_occurrence_links` → `annotations` and `annotation_views`;
- views → `documents`, `document_texts`, `exports`.

Every occurrence link contributes an annotation in its selected view. Do not count
or iterate only deduplicated `annotations` rows. The adapter returns existing
`TemporaryCorpus` / `DocumentAnnotations` structures and stored document text.
Stored `sctid` is already extracted; `raw_id`, cached FSN/activity and concept-cache
fields are not used to reinterpret codes or override HDF5 state. GUI SQLite settings
report `id_feature=sctid`, `id_prefix=""`.

Layer matching is exact because SQLite lacks CAS type inheritance. Annotators use
existing trim/lower scope semantics (empty = all). Ignore overlaps reuse `spans_match`;
a requested ignore layer absent from the selected data fails explicitly. Occurrence-to-view document-hash identity, nonnegative ordered offsets, text/offset agreement where full text
exists, and conflicting document text are checked. Missing full text is allowed;
review falls back to covered text/saved snippets.

## Scope and provenance

Explicit metadata inspection exposes `store_scope` tokens:

- `*:annotation` (or another view kind): that kind across exports;
- `1:annotation`: that kind in export 1;
- `*:*`: all exports/view kinds, available when multiple kinds exist.

A sole kind defaults to all exports of that kind. Mixed kinds require a choice.
Combined scopes reject more than one view with the same document name and normalized
annotator, even if payloads are identical. Choose a narrower scope rather than
silently merging/deduplicating. Conflicting texts for one document name also fail.
Source filename and scope are recorded in findings/suggestion metadata; reviewed
artifacts retain source metadata. NiceGUI job/rule binding and Streamlit rule/source
checks include SQLite scope. Input/scope changes never run processing or replace
loaded review choices.

## Integration and safety

`uima_processing.project` dispatches explicitly supplied SQLite files to this reader,
leaving ZIP extraction unchanged. Policy checking consumes the same corpus/report
engine. `preview_concept_rules` reads original stored IDs without chaining or editing
features and retains existing target validation/conflict protections. Explicit
`ReviewContext.from_project_path` reads SQLite text; metadata paths are never opened.
Both GUIs keep Upload / Data directory / Server path selection. Streamlit policy
reports for SQLite go into a temporary directory, not beside the database.

Connections use `mode=ro&immutable=1`, query-only mode and explicit close. Use a closed,
checkpointed snapshot; pending WAL is rejected. No DDL, migrations, database updates,
WAL/SHM creation or database write-back. CAS restoration/write-back/deployment is available only for the optional preservation extension described below.
Source stat changes during a read reject results. Only fixed `AnnotationStoreError`
messages may be displayed by NiceGUI; unrelated failures retain non-echoing errors.

## Optional complete CAS restoration

New stores built with `--store-cas` preserve raw complete JSONCAS/XMI, content-addressed type systems and optional original project configuration. Full document text is included. The core reader still checks stored exact layer names/SCTIDs without reconstructing CAS; preservation does not alter policy semantics. No old-store upgrades occur. See [schema extension](annotation-store-sqlite.md#optional-cas-restoration-extension).

Restoration requires one export/view scope (select it before generating review), complete CAS coverage, and a compatible explicit project-template ZIP if the export lacked configuration. `restore-annotation-store-cas` emits a new JSON/XMI workspace for existing shell/artifact deployment, not a native Java-serialized project backup. `run_sanitization` and `apply_decisions_and_upload_to_inception` restore internally; original ID settings are recovered automatically. Local sanitized ZIPs preserve excluded CAS unchanged; remote artifacts omit excluded CAS. Streamlit enables its existing controls only for eligible stores/scopes. NiceGUI adds an explicit offline review-package download with source/review revision guards; live deployment remains separate. Old stores remain analysis/review-JSON-only. Source DB bytes stay unchanged and metadata paths are never opened.

## Verification

Synthetic fixtures compare ZIP/SQLite findings, suggestions and concept-rule decisions,
occurrence counts, scoped filtering, document context, and unchanged database bytes.
Tests cover ambiguous views, missing ignore layers, invalid offsets/schema versions,
installed-SDK NiceGUI scope/check/generation/rules/review flow and Streamlit scope/check
flow. Streamlit segmented controls use its existing AppTest workaround. Focused
regression: 202 passed, one existing `SuggestionsUploadPageTest` stale-click/upload
failure, two warnings. Actual browser interaction and clinical-database processing
are not verified by these checks.

See [user guide](../../../docs/user-guide.md#sqlite-instead-of-an-inception-project).
