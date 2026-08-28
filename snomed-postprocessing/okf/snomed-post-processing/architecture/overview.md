---
type: Architecture Overview
title: SNOMED Post Processing architecture
description: High-level architecture and data flow of the SNOMED Post Processing application.
resource: /src/snomed_post_processing
tags: [architecture, snomed-post-processing, inception, snomed, hdf5, uima]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: source-tree
    resource: /src/snomed_post_processing
    title: Application source tree
  - id: maintainer-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/snomed-postprocessing-working.md
    title: SNOMED Postprocessing maintainer map
  - id: usage-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/snomed-usage-analysis.md
    title: SNOMED CT usage in this project
---

# Purpose

SNOMED Post Processing validates and sanitizes SNOMED CT concept annotations in INCEpTION/UIMA projects. It is not a full SNOMED reasoning engine during document processing. It precomputes SNOMED-derived policy data into HDF5, then performs fast exact SCTID checks and conservative replacement suggestion workflows.

# Main data flow

```text
SNOMED RF2 ZIP or Snowstorm
        |
create-concepts-dump
        |
sanitization-ready HDF5 policy store
        |
INCEpTION project ZIP / remote export
        |
log-critical-documents or GUI check
        |
CriticalFindings JSON + Markdown reports
        |
suggest-sanitization or GUI suggestions
        |
SanitizationSuggestions Markdown + JSON
        |
human review decisions JSON
        |
local sanitized ZIP OR one-step INCEpTION deployment
```

The original INCEpTION project ZIP is never modified in place.

# Core architectural boundaries

| Boundary | Responsibility | Main code |
|---|---|---|
| CLI | Console scripts and option validation | `/src/snomed_post_processing/cli/app.py`, `/src/snomed_post_processing/cli/options.py` |
| GUI | Streamlit app and tabs | `/src/snomed_post_processing/gui/` |
| RF2 ingestion | Materialize SNOMED release/policy HDF5 | `/src/snomed_post_processing/release_ingestion/`, `/src/snomed_post_processing/pipelines/hdf5_dump_creation.py` |
| HDF5 policy access | Centralized layout and target-view gates | `/src/snomed_post_processing/hdf5_handling/policy.py` |
| UIMA/INCEpTION IO | Read project ZIP members and CAS payloads | `/src/snomed_post_processing/uima_processing/io.py`, `/src/snomed_post_processing/uima_processing/project.py` |
| Finding analysis | Exact policy checking of extracted annotations | `/src/snomed_post_processing/uima_processing/analysis.py` |
| Sanitization resolver | Historical association, ancestor, and BM25 suggestions | `/src/snomed_post_processing/sanitization/` |
| Write-back/deployment pipelines | Apply decisions, shell project, upload artifacts, remote deploy | `/src/snomed_post_processing/pipelines/` |

# Key safety principles

- Exact policy mode remains authoritative: active + whitelist - blacklist.
- Release mode allows active concepts by default and only enforces blacklist exclusions when explicitly configured.
- Suggestions are evidence for review, not automatic correction.
- Reviewed decisions are applied to the original project ZIP, not an already sanitized ZIP.
- Real INCEpTION writes are dry-run by default and require explicit `--apply`.
- `.ser` CAS generation is intentionally avoided.

# Related concepts

- [Module map](/snomed-post-processing/modules/module-map.md)
- [HDF5 policy store](/snomed-post-processing/data/hdf5-policy-store.md)
- [Sanitization suggestions](/snomed-post-processing/workflows/sanitization-suggestions.md)
- [INCEpTION deployment](/snomed-post-processing/workflows/inception-deployment.md)
