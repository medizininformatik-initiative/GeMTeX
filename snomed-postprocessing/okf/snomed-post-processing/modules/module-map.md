---
type: Python Package
title: Maintainer module map
description: Source module map for the SNOMED Post Processing Python package.
resource: /src/snomed_post_processing
tags: [python, modules, maintainer-map]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: maintainer-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/snomed-postprocessing-working.md
    title: SNOMED Postprocessing maintainer map
  - id: source-tree
    resource: /src/snomed_post_processing
    title: Application source tree
---

# Entry points

Console scripts are declared in `/pyproject.toml` and implemented in `/src/snomed_post_processing/cli/app.py`.

| Command/UI | Purpose |
|---|---|
| `log-critical-documents` | Check INCEpTION/UIMA annotations against whitelist/blacklist policy views and write reports plus CriticalFindings JSON. |
| `create-concepts-dump` | Build/update SNOMED HDF5 files from RF2 ZIPs or Snowstorm. |
| `summarize-hdf5` | Inspect HDF5 metadata and policy views. |
| `suggest-sanitization` | Generate sanitization suggestions from CriticalFindings JSON. |
| `build-snogit-cache` | Build processed SNOGIT cache HDF5 for BM25/interface-term evidence. |
| `build-inception-shell-project` | Build schema-shell ZIP for sanitized INCEpTION deployment. |
| `build-inception-upload-artifacts` | Build flattened sanitized JSONCAS/XMI upload artifacts. |
| `apply-decisions-to-inception` | One-step shell + repaired artifacts + dry-run/apply deployment workflow. |
| `deploy-inception-sanitized-project` | Lower-level deployment planner/applier for an existing shell and artifact dir. |
| Streamlit GUI | Browser workflow for policy creation, checking, suggestion review/apply, and INCEpTION deployment. |

# Package areas

| Package/module | Responsibility |
|---|---|
| `cli/` | Click commands, reusable option decorators, logging setup, custom Click parameter types. |
| `gui/` | Streamlit app tabs, file source selectors, report downloads, review state, deployment form. |
| `findings_io/` | CriticalFindings JSON serialization/deserialization and mapping helpers. |
| `hdf5_handling/` | HDF5 policy layout readers, candidate validity gates, metadata summaries, compact ancestor dump helpers. |
| `release_ingestion/` | RF2 member discovery, RF2 row readers, materialized HDF5 writer. |
| `snomed/` | Pydantic/domain models and enums for SNOMED/Snowstorm concepts and dump modes. |
| `snowstorm/` | Snowstorm endpoint construction, branch listing, traversal and response mapping. |
| `uima_processing/` | INCEpTION ZIP/CAS loading, annotation extraction, policy analysis, reports. |
| `sanitization/` | Suggestion models, resolver, JSON/Markdown reports, BM25, semantic text handling, SNOGIT cache. |
| `pipelines/` | End-to-end reusable workflow functions behind CLI/GUI. |
| `inception/` | INCEpTION remote project export helpers and annotator prompting. |
| `utils/` | Small text helpers. |

# Most important implementation modules

- `/src/snomed_post_processing/hdf5_handling/policy.py` centralizes the compact HDF5 schema and candidate validity rules. Prefer this module over raw HDF5 path access.
- `/src/snomed_post_processing/sanitization/resolver.py` implements historical association and ancestor fallback suggestion selection.
- `/src/snomed_post_processing/sanitization/semantic_bm25.py` and `/src/snomed_post_processing/sanitization/snogit_sidecar.py` implement lexical fallback evidence.
- `/src/snomed_post_processing/pipelines/sanitization_run.py` applies reviewed decisions to CAS members and local sanitized ZIPs.
- `/src/snomed_post_processing/pipelines/inception_apply_upload.py` is the main one-step deployment pipeline.
- `/src/snomed_post_processing/pipelines/inception_deployment.py` performs dry-run/apply remote deployment and CAS repair.

# Related concepts

- [CLI commands](/snomed-post-processing/interfaces/cli.md)
- [GUI](/snomed-post-processing/interfaces/gui.md)
- [Architecture overview](/snomed-post-processing/architecture/overview.md)
