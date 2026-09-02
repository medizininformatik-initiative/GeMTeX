---
type: Update Log
title: SNOMED Post Processing OKF bundle log
description: Chronological update history for this OKF bundle.
tags: [log, okf, snomed-post-processing]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
---

# Bundle update log

## 2026-09-02

- **Addition**: Documented the annotation-store workflow and SQLite schema, including content-hash-based applicability checks.
- **Update**: Added `build-annotation-store` and `check-annotation-store-document` to CLI/module OKF pages.
- **Schema note**: `document_hashes` is canonical by `text_hash` only; provenance remains on `annotation_views -> exports`.
- **Queries**: Added query-cookbook OKF pages for `queries/run_sql.py` and reusable annotation-store SQL files.

## 2026-08-28

- **Creation**: Added initial OKF bundle under `okf/snomed-post-processing/`.
- **Migration**: Imported every former documentation Markdown file as an OKF-wrapped page under `source-former documentation folder/`.
- **Curation**: Added agent-oriented concept pages for architecture, module map, CLI, GUI, HDF5 layout, JSON artifacts, INCEpTION CAS/ZIP handling, RF2 ingestion, critical-finding logging, suggestion generation, reviewed decision write-back, INCEpTION deployment, SNOGIT/BM25, design decisions, and follow-ups.
- **Safety**: Did not delete the former documentation folder.
