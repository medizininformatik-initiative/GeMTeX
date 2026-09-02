---
type: Workflow
title: Build and query the annotation store
description: CLI workflow for importing SNOMED annotations from INCEpTION export ZIPs into SQLite and checking external documents by content hash.
resource: /src/snomed_post_processing/pipelines/annotation_store.py
tags: [workflow, annotation-store, sqlite, inception, snomed]
status: draft
generated: { by: pi-coding-agent/gpt-5, at: 2026-09-02T00:00:00Z }
sources:
  - id: cli
    resource: /src/snomed_post_processing/cli/app.py
    title: build-annotation-store and check-annotation-store-document commands
  - id: schema
    resource: /okf/snomed-post-processing/data/annotation-store-sqlite.md
    title: Annotation store SQLite schema
---

# Build and query the annotation store

The annotation-store workflow creates a single SQLite database from one or more INCEpTION export ZIPs. It is CLI-only and independent of the Streamlit GUI.

# Build command

```bash
uv run build-annotation-store \
  --input /path/to/inception-export-zips-or-directory \
  --snomed-hdf5 data/gemtex_snomedct_codes_release20260401_policy20240401.hdf5 \
  --output data/semantic_snomed_annotations.sqlite \
  --replace
```

The command accepts either individual ZIPs or directories containing ZIPs. Multiple `--input` values are allowed.

# Imported views

The importer includes:

- curation views, e.g. `curation/<document>/CURATION_USER.zip`;
- annotation views, e.g. `annotation/<document>/<annotator>.zip`;
- flat archive layouts, e.g. Essen exports.

UIMA Java serialized CAS files (`.ser`) are not supported by the Python CAS stack and are skipped/reported.

# Site and batch handling

Filenames such as `berlin_XMI_1-3.zip` are parsed as:

| Field | Example |
|---|---|
| site | `berlin` |
| batch_index | `1` |
| batch_total | `3` |

The database can contain incomplete batch sets. Missing batches are reported in the command summary and can be appended later with `--append`.

# Document identity and applicability

Applicability is based on exact document content hash, not document name.

The build command stores SHA-256 hashes of complete CAS document text in `document_hashes`. The normalized document name remains metadata only. To check an external text file:

```bash
uv run check-annotation-store-document \
  --store data/semantic_snomed_annotations.sqlite \
  --document /path/to/document.txt
```

If the computed SHA-256 hash matches a row in `document_hashes`, annotation offsets are applicable to that exact text content.

# Optional raw text storage

By default, complete document text is not stored. Only the hash and annotation covered text are stored.

To store full CAS document text:

```bash
uv run build-annotation-store \
  --input /path/to/inception-export-zips-or-directory \
  --snomed-hdf5 data/gemtex_snomedct_codes_release20260401_policy20240401.hdf5 \
  --output data/semantic_snomed_annotations_with_text.sqlite \
  --replace \
  --store-document-text
```

# SNOMED enrichment

For each annotation occurrence, the importer normalizes the annotation id to a bare SCTID and looks it up in the SNOMED HDF5 concept store. Known SCTIDs are enriched with:

- FSN;
- semantic tag;
- active flag.

Unknown SCTIDs are retained with null metadata.

# Main analysis view

Most downstream queries should use the flattened SQL view:

```sql
select * from annotation_occurrences;
```

See [Annotation store SQLite schema](/snomed-post-processing/data/annotation-store-sqlite.md) for table-level details and example queries.

# Related concepts

- [Annotation store SQLite schema](/snomed-post-processing/data/annotation-store-sqlite.md)
- [CLI commands](/snomed-post-processing/interfaces/cli.md)
- [INCEpTION CAS and ZIP](/snomed-post-processing/data/inception-cas-and-zip.md)
