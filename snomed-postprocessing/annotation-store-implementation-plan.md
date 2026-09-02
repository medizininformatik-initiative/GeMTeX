# Annotation Store Implementation Plan

## Goal

Add a CLI-only pipeline that reads one or more INCEpTION project/export ZIPs and creates a single SQLite database containing all SNOMED annotations across sites, export batches, documents, annotation views, and annotators.

The store should support downstream analysis of questions such as:

- Which SNOMED concepts occur in which documents?
- Which site/annotator/curation view annotated which SCTID at which offset?
- Which SCTIDs are unknown in the local SNOMED HDF5 concept store?
- How do annotation and curation views differ across sites?

No GUI integration is planned for the first version.

## Inputs

Primary input examples live under:

```text
/home/tec-nlp-prod/workspaces/semantic-snomed-grascco
```

Observed naming pattern:

```text
berlin_XMI_1-3.zip
berlin_XMI_2-3.zip
erlangen_XMI_1-3.zip
erlangen_XMI_2-3.zip
erlangen_XMI_3-3.zip
essen_flat_XMI_1-1.zip
leipzig_XMI_1-1.zip
münchen_XMI_1-3.zip
```

Important: a site may split its corpus into several batches. Missing future batches must be handled naturally. For example, Berlin currently has `1-3` and `2-3`; `3-3` can be appended later.

SNOMED metadata input:

```text
data/gemtex_snomedct_codes_release20260401_policy20240401.hdf5
```

This HDF5 contains concept metadata needed for enrichment:

- SCTID
- FSN
- semantic tag
- active flag

## Output

A single SQLite database, e.g.:

```text
data/semantic_snomed_annotations.sqlite
```

Default contents:

- annotation occurrences
- offset spans
- covered text only, not full document text
- SHA-256 hash of the complete CAS document text for reproducibility
- normalized SCTIDs
- FSN/semantic tag/active status where known
- provenance: site, export batch, document, view kind, annotator, CAS path

Unknown SCTIDs are retained with `fsn`, `semantic_tag`, and `active` set to `NULL`.

Optional full document text storage should be supported via a CLI flag, but disabled by default.

## CLI design

Add console script:

```toml
build-annotation-store = "snomed_post_processing.cli.app:build_annotation_store_cli"
```

Recommended first-use command:

```bash
uv run build-annotation-store \
  --input /home/tec-nlp-prod/workspaces/semantic-snomed-grascco \
  --snomed-hdf5 data/gemtex_snomedct_codes_release20260401_policy20240401.hdf5 \
  --output data/semantic_snomed_annotations.sqlite \
  --replace
```

Optional with document text:

```bash
uv run build-annotation-store \
  --input /home/tec-nlp-prod/workspaces/semantic-snomed-grascco \
  --snomed-hdf5 data/gemtex_snomedct_codes_release20260401_policy20240401.hdf5 \
  --output data/semantic_snomed_annotations_with_text.sqlite \
  --replace \
  --store-document-text
```

Append a later batch:

```bash
uv run build-annotation-store \
  --input /home/tec-nlp-prod/workspaces/semantic-snomed-grascco/berlin_XMI_3-3.zip \
  --snomed-hdf5 data/gemtex_snomedct_codes_release20260401_policy20240401.hdf5 \
  --output data/semantic_snomed_annotations.sqlite \
  --append
```

### Proposed options

```text
--input PATH                         ZIP file or directory containing ZIPs; repeatable if useful
--snomed-hdf5 PATH                   HDF5 concept metadata source
--output PATH                        SQLite output DB
--annotation-type TYPE               repeatable; default: gemtex.Concept
--id-prefix TEXT                     default: http://snomed.info/id/
--replace                            recreate output DB if it exists
--append                             append to an existing DB or create it if missing
--store-document-text                populate document_texts table; default false
--site TEXT                          optional manual site override for single-ZIP input
--fail-fast                          stop on first bad CAS; default false/warn-and-continue
--report PATH                        optional JSON import summary
--log-level LEVEL                    consistent with existing CLI logging
```

`--replace` and `--append` should be mutually exclusive. If neither is given and the output exists, fail with a clear message.

## Filename parsing

Infer site and batch metadata from filenames.

Examples:

| Filename | site | batch_index | batch_total |
|---|---:|---:|---:|
| `berlin_XMI_1-3.zip` | berlin | 1 | 3 |
| `berlin_XMI_2-3.zip` | berlin | 2 | 3 |
| `erlangen_XMI_3-3.zip` | erlangen | 3 | 3 |
| `essen_flat_XMI_1-1.zip` | essen | 1 | 1 |
| `münchen_XMI_1-3.zip` | münchen | 1 | 3 |

Suggested regex:

```text
^(?P<site>.+?)(?:_flat)?_XMI_(?P<batch_index>\d+)-(?P<batch_total>\d+)\.zip$
```

If parsing fails:

- use `--site` if supplied
- otherwise use filename stem as site and leave batch fields `NULL`
- emit warning

After processing, report missing batches per site, e.g.:

```text
Site berlin: found batches 1,2 of expected 3; missing batch 3.
Site erlangen: found batches 1,2,3 of expected 3.
```

## Document name normalization

Normalize document names for cross-site comparison.

Examples:

```text
Albers.txt.xmi       -> Albers.txt
Albers.txt.json      -> Albers.txt
Albers.txt.zip       -> Albers.txt
Albers.txt           -> Albers.txt
```

Use the normalized name as the canonical `documents.document_name`.

## Views to include

Include both annotation and curation views:

```text
annotation/<document>/<annotator>.zip
curation/<document>/CURATION_USER.zip
```

Also support flat archive layouts, e.g. Essen, using:

```text
view_kind = flat
annotator = flat-archive
```

`.ser` files remain unsupported and should be skipped when JSON/XMI/nested ZIP CAS is available, consistent with current project behavior.

## Proposed schema

### `exports`

One row per input ZIP/batch.

```sql
create table exports(
  id integer primary key,
  site text not null,
  path text not null,
  filename text not null,
  batch_index integer,
  batch_total integer,
  batch_label text,
  imported_at text not null,
  unique(path)
);
```

### `documents`

Canonical normalized document names.

```sql
create table documents(
  id integer primary key,
  document_name text not null unique
);
```

### `document_hashes`

Complete CAS document text hashes. Populated by default without storing raw full text.

```sql
create table document_hashes(
  id integer primary key,
  document_id integer not null,
  export_id integer,
  text_hash text not null,
  source_path text,
  unique(document_id, export_id, text_hash),
  foreign key(document_id) references documents(id),
  foreign key(export_id) references exports(id)
);
```

### `document_texts`

Optional raw/full document text table. Only populated when `--store-document-text` is set.

```sql
create table document_texts(
  id integer primary key,
  document_id integer not null,
  export_id integer,
  text text not null,
  text_hash text not null,
  source_path text,
  unique(document_id, text_hash),
  foreign key(document_id) references documents(id),
  foreign key(export_id) references exports(id)
);
```

### `annotation_views`

One row per CAS view for a document.

```sql
create table annotation_views(
  id integer primary key,
  export_id integer not null,
  document_id integer not null,
  document_hash_id integer,
  document_text_id integer,
  view_kind text not null,
  annotator text not null,
  cas_path text not null,
  unique(export_id, document_id, view_kind, annotator, cas_path),
  foreign key(export_id) references exports(id),
  foreign key(document_id) references documents(id),
  foreign key(document_hash_id) references document_hashes(id),
  foreign key(document_text_id) references document_texts(id)
);
```

### `snomed_concepts`

Known concepts copied from HDF5.

```sql
create table snomed_concepts(
  sctid text primary key,
  fsn text,
  semantic_tag text,
  active integer
);
```

### `annotations`

One row per annotation occurrence.

```sql
create table annotations(
  id integer primary key,
  view_id integer not null,
  layer text not null,
  begin_offset integer not null,
  end_offset integer not null,
  covered_text text,
  sctid text,
  fsn text,
  semantic_tag text,
  active integer,
  raw_id text,
  literal text,
  annotation_hash text not null unique,
  foreign key(view_id) references annotation_views(id),
  foreign key(sctid) references snomed_concepts(sctid)
);
```

### Indexes

```sql
create index idx_exports_site on exports(site);
create index idx_exports_site_batch on exports(site, batch_index, batch_total);
create index idx_views_export_doc on annotation_views(export_id, document_id);
create index idx_views_annotator on annotation_views(annotator);
create index idx_annotations_view_offsets on annotations(view_id, begin_offset, end_offset);
create index idx_annotations_sctid on annotations(sctid);
create index idx_annotations_semantic_tag on annotations(semantic_tag);
```

## Convenience SQL views

### Flattened annotation occurrences

```sql
create view annotation_occurrences as
select
  e.site,
  e.filename as export_file,
  e.batch_index,
  e.batch_total,
  d.document_name,
  av.view_kind,
  av.annotator,
  av.cas_path,
  dh.text_hash as document_text_hash,
  a.layer,
  a.begin_offset,
  a.end_offset,
  a.covered_text,
  a.sctid,
  a.semantic_tag,
  a.fsn,
  a.active,
  a.raw_id,
  a.literal
from annotations a
join annotation_views av on av.id = a.view_id
join exports e on e.id = av.export_id
join documents d on d.id = av.document_id
left join document_hashes dh on dh.id = av.document_hash_id;
```

### Site-specific examples

Site views can be created later from the merged DB:

```sql
create view berlin_annotations as
select * from annotation_occurrences where site = 'berlin';
```

## Implementation structure

Add package:

```text
src/snomed_post_processing/annotation_store/
  __init__.py
  models.py
  filename.py
  snomed_lookup.py
  cas_views.py
  sqlite.py
```

Add pipeline:

```text
src/snomed_post_processing/pipelines/annotation_store.py
```

Update CLI:

```text
src/snomed_post_processing/cli/app.py
pyproject.toml
README.md
```

Optional tests:

```text
test/test_annotation_store_filename.py
test/test_annotation_store_sqlite.py
test/test_annotation_store_pipeline.py
```

## Key internal data model

Implement a low-level CAS view iterator rather than reusing only `process_inception_zip()`, because this store must preserve exact provenance for each site/export/view/annotator/CAS member.

Suggested model:

```python
@dataclass(frozen=True)
class CasView:
    site: str
    export_path: pathlib.Path
    export_filename: str
    batch_index: int | None
    batch_total: int | None
    document_name: str
    view_kind: str        # annotation, curation, flat
    annotator: str
    cas_path: str
    cas: cassis.Cas
```

Suggested annotation model:

```python
@dataclass(frozen=True)
class AnnotationOccurrence:
    layer: str
    begin_offset: int
    end_offset: int
    covered_text: str
    sctid: str | None
    raw_id: str | None
    literal: str | None
    fsn: str | None
    semantic_tag: str | None
    active: bool | None
```

## Reusing existing code

Use existing UIMA ZIP/CAS helpers where possible:

- `_read_project`
- `_yield_matching_files`
- `_yield_flat_archive_files`
- `_prefer_non_ser_files`
- `_load_typesystem_from_zip`
- `_load_cas_from_zip_member`
- `_annotator_name_from_cas_path`

However, add new logic for:

- determining `view_kind` from `cas_path`
- preserving `cas_path`
- extracting raw feature values (`id`, `literal`)
- optional document text hashing/storage
- writing SQLite rows

## SNOMED HDF5 lookup

Read from compact HDF5 concept datasets:

```text
concepts/codes
concepts/fsn
concepts/semantic_tag_id
concepts/semantic_tags
concepts/active
```

Build a lookup:

```python
sctid -> ConceptMetadata(fsn, semantic_tag, active)
```

If an SCTID is absent, return null metadata and still store the annotation.

## Annotation hash

Use a deterministic hash to avoid duplicate insertion on append/retry.

Hash fields:

```text
export path or filename
site
batch_index
batch_total
document_name
view_kind
annotator
cas_path
layer
begin_offset
end_offset
sctid
covered_text
raw_id
literal
```

Use SHA-256 over a stable JSON serialization.

## Processing flow

1. Resolve input ZIPs.
2. Validate output mode: `--replace` / `--append`.
3. Initialize/open SQLite DB.
4. Read SNOMED HDF5 lookup.
5. Insert/update known concepts used by annotations, or prefill all concepts if acceptable.
   - Recommended first version: insert only concepts encountered in annotations.
6. For each ZIP:
   1. infer site and batch metadata
   2. create `exports` row
   3. iterate CAS views
   4. normalize document name and create `documents` row
   5. optionally store document text
   6. create `annotation_views` row
   7. extract annotations from configured layers
   8. enrich with HDF5 metadata
   9. insert `annotations`
7. Create/update convenience SQL views.
8. Print and optionally write JSON summary.

## Error handling

Default behavior should be robust:

- skip unsupported `.ser` if non-`.ser` CAS exists
- warn and continue for malformed CAS files
- collect failures in summary
- keep unknown SCTIDs

`--fail-fast` should raise immediately.

## Summary report

Print at end:

```text
Exports processed: N
Sites: berlin, erlangen, essen, leipzig, münchen
Documents: N
Annotation views: N
Annotations: N
Known SCTIDs: N
Unknown SCTIDs: N
Failed CAS members: N
Missing batches:
  berlin: missing 3 of 3
```

Optional JSON report structure:

```json
{
  "exports_processed": 0,
  "sites": {},
  "documents": 0,
  "annotation_views": 0,
  "annotations": 0,
  "known_sctids": 0,
  "unknown_sctids": [],
  "failed_cas_members": [],
  "missing_batches": []
}
```

## Test plan

1. Filename parser tests:
   - standard site batches
   - `_flat` variant
   - umlaut site name `münchen`
   - unparsable fallback
2. Document normalization tests.
3. SQLite schema creation and idempotent append tests.
4. SNOMED lookup test with a tiny temporary HDF5 file.
5. Pipeline smoke test using a minimal generated CAS ZIP, if feasible.
6. Manual smoke test against one real ZIP:

```bash
uv run build-annotation-store \
  --input /home/tec-nlp-prod/workspaces/semantic-snomed-grascco/berlin_XMI_1-3.zip \
  --snomed-hdf5 data/gemtex_snomedct_codes_release20260401_policy20240401.hdf5 \
  --output /tmp/annotation_store.sqlite \
  --replace
```

Then inspect:

```bash
sqlite3 /tmp/annotation_store.sqlite \
  "select site, document_name, view_kind, annotator, count(*) from annotation_occurrences group by 1,2,3,4 limit 20;"
```

## Documentation updates

Update `README.md` CLI command list and add a short usage section for `build-annotation-store`.

Potential OKF updates after implementation:

```text
okf/snomed-post-processing/workflows/annotation-store.md
okf/snomed-post-processing/data/annotation-store-sqlite.md
okf/snomed-post-processing/interfaces/cli.md
okf/snomed-post-processing/modules/module-map.md
```
