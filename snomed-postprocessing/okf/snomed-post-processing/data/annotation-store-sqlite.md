---
type: SQLite Schema
title: Annotation store SQLite schema
description: Database schema for merged SNOMED annotation occurrences imported from INCEpTION export ZIPs.
resource: /src/snomed_post_processing/annotation_store/sqlite.py
tags: [sqlite, annotation-store, inception, uima, snomed]
status: draft
generated: { by: pi-coding-agent/gpt-5, at: 2026-09-02T00:00:00Z }
sources:
  - id: implementation
    resource: /src/snomed_post_processing/annotation_store/sqlite.py
    title: SQLite writer and schema
  - id: pipeline
    resource: /src/snomed_post_processing/pipelines/annotation_store.py
    title: Annotation-store build pipeline
  - id: checker
    resource: /src/snomed_post_processing/pipelines/annotation_store_check.py
    title: Content-hash applicability checker
  - id: inception-cas
    resource: /okf/snomed-post-processing/data/inception-cas-and-zip.md
    title: INCEpTION CAS and ZIP handling
---

# Annotation store SQLite schema

The annotation store is a single-file SQLite database produced by `build-annotation-store`. It merges SNOMED annotation occurrences from multiple INCEpTION export ZIPs, sites, batches, CAS views, and annotators.

The database is intended for downstream analysis and reproducibility checks, not as an INCEpTION project replacement. The source export ZIPs are not modified.

# Applicability principle

Annotation offsets are applicable to a document **only when the complete document text hash matches**.

Do not rely on normalized document names for applicability. Document names are retained as provenance/search metadata, but exact content identity is represented by:

```sql
document_hashes.text_hash
```

The hash is SHA-256 over the complete CAS sofa/document text encoded as UTF-8.

# Tables

## `exports`

One row per imported export ZIP/batch.

| Column | Type | Description |
|---|---|---|
| `id` | integer primary key | Export row id. |
| `site` | text not null | Site inferred from filename or CLI override. |
| `path` | text not null unique | Absolute path to the export ZIP at import time. |
| `filename` | text not null | Export ZIP filename. |
| `batch_index` | integer nullable | Batch number from names like `berlin_XMI_1-3.zip`. |
| `batch_total` | integer nullable | Expected number of batches for the site/export set. |
| `batch_label` | text nullable | Human-readable batch label, e.g. `1-3`. |
| `imported_at` | text not null | UTC ISO timestamp of import. |

## `documents`

Canonical document-name metadata.

| Column | Type | Description |
|---|---|---|
| `id` | integer primary key | Document row id. |
| `document_name` | text not null unique | Normalized document name such as `Albers.txt`. |

This table is useful for browsing and grouping, but it is not used to decide whether annotations apply to an external document.

## `document_hashes`

Canonical content hashes.

| Column | Type | Description |
|---|---|---|
| `id` | integer primary key | Hash row id. |
| `text_hash` | text not null unique | SHA-256 hash of complete CAS document text. |

This table intentionally has no `document_id`, `export_id`, site, or source-path columns. The same document content can appear in several sites/exports, but it should have exactly one row here.

## `document_texts`

Optional full document text storage. It is populated only when `build-annotation-store --store-document-text` is used.

| Column | Type | Description |
|---|---|---|
| `id` | integer primary key | Document text row id. |
| `document_hash_id` | integer not null unique | References `document_hashes.id`. |
| `text` | text not null | Complete CAS document text. |

By default this table is empty; `document_hashes` is still populated.

## `annotation_views`

One row per imported CAS view of a document.

| Column | Type | Description |
|---|---|---|
| `id` | integer primary key | View row id. |
| `export_id` | integer not null | References the export ZIP in `exports`. |
| `document_id` | integer not null | References normalized document-name metadata in `documents`. |
| `document_hash_id` | integer nullable | References exact document content in `document_hashes`. |
| `document_text_id` | integer nullable | References optional raw text in `document_texts`. |
| `view_kind` | text not null | `annotation`, `curation`, or `flat`. |
| `annotator` | text not null | INCEpTION annotator/user or flat archive annotator. |
| `cas_path` | text not null | Member path inside the export ZIP. |

Unique key:

```sql
unique(export_id, document_id, view_kind, annotator, cas_path)
```

## `snomed_concepts`

Known SCTIDs encountered during import, enriched from the SNOMED HDF5 concept store.

| Column | Type | Description |
|---|---|---|
| `sctid` | text primary key | SNOMED CT concept id. |
| `fsn` | text nullable | Fully specified name. |
| `semantic_tag` | text nullable | Semantic tag resolved from HDF5. |
| `active` | integer nullable | `1` active, `0` inactive, `NULL` unknown. |

Unknown SCTIDs are retained in `annotations` with null metadata and are not necessarily present in this table.

`semantic_tag` can be null even when the build summary says `Unknown SCTIDs: 0`. The summary's unknown-SCTID counter only counts non-empty normalized SCTIDs that were not found in the HDF5 lookup. The summary therefore also prints the number of annotation occurrences where the annotation id itself is absent/empty/null-like and therefore `sctid` is null, e.g. `Unknown SCTIDs: 0 (17 missing/empty/null-like ids)`.

Semantic tag nullability rules:

- `sctid` is null when the annotation `id` feature is missing, empty, or a null-like string such as `null`, `none`, or `nan`; then `fsn`, `semantic_tag`, and `active` are null.
- `sctid` is non-null but not found in HDF5; then the SCTID appears in the unknown-SCTID set and `fsn`, `semantic_tag`, and `active` are null.
- The SCTID is found but its HDF5 `semantic_tag_id` does not resolve to an entry in `concepts/semantic_tags`; then `semantic_tag` is null, while other metadata may still be present.

## `annotations`

One row per annotation occurrence.

| Column | Type | Description |
|---|---|---|
| `id` | integer primary key | Annotation row id. |
| `view_id` | integer not null | References `annotation_views.id`. |
| `layer` | text not null | CAS annotation layer, default `gemtex.Concept`. |
| `begin_offset` | integer not null | Begin offset in the exact document text. |
| `end_offset` | integer not null | End offset in the exact document text. |
| `covered_text` | text nullable | Covered span text. |
| `sctid` | text nullable | Normalized SCTID, without `http://snomed.info/id/`. |
| `fsn` | text nullable | FSN copied from HDF5 at import time. |
| `semantic_tag` | text nullable | Semantic tag copied from HDF5 at import time. |
| `active` | integer nullable | Active flag copied from HDF5 at import time. |
| `raw_id` | text nullable | Original annotation id feature. |
| `literal` | text nullable | Optional annotation literal feature. |
| `annotation_hash` | text not null unique | Deterministic occurrence hash used for append/retry idempotence. |

# Convenience view

`annotation_occurrences` flattens the main joins for analysis:

```sql
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

# Common queries

Count unique document contents:

```sql
select count(*) from document_hashes;
```

Check duplicate content-hash rows should return zero:

```sql
select text_hash, count(*)
from document_hashes
group by text_hash
having count(*) > 1;
```

Find all provenance/views for a known document content hash:

```sql
select
  e.site,
  e.filename,
  e.batch_index,
  e.batch_total,
  d.document_name,
  av.view_kind,
  av.annotator,
  count(a.id) as annotations
from document_hashes dh
join annotation_views av on av.document_hash_id = dh.id
join exports e on e.id = av.export_id
join documents d on d.id = av.document_id
left join annotations a on a.view_id = av.id
where dh.text_hash = ?
group by e.site, e.filename, e.batch_index, e.batch_total, d.document_name, av.view_kind, av.annotator;
```

# Related concepts

- [Annotation-store workflow](/snomed-post-processing/workflows/annotation-store.md)
- [CLI commands](/snomed-post-processing/interfaces/cli.md)
- [INCEpTION CAS and ZIP](/snomed-post-processing/data/inception-cas-and-zip.md)
- [HDF5 policy store](/snomed-post-processing/data/hdf5-policy-store.md)
