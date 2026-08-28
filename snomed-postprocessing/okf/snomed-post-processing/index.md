---
okf_version: "0.2"
type: Knowledge Bundle Index
title: SNOMED Post Processing application OKF bundle
description: Agent-readable map of the SNOMED Post Processing app, workflows, data formats, CLI, GUI, and migrated docs.
tags: [snomed-post-processing, inception, snomed, uima, hdf5, sanitization]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: source-tree
    resource: /src/snomed_post_processing
    title: Application source tree
    author: team:project-maintainers
  - id: docs-folder
    resource: /snomed-post-processing/source-docs/index.md
    title: Migrated original project documentation
    author: team:project-maintainers
  - id: okf-spec
    resource: /home/tec-nlp-prod/okf/okf/okf_spec.md
    title: Open Knowledge Format v0.2 specification
    author: team:okf
---

# SNOMED Post Processing OKF bundle

This bundle is the agent-readable knowledge layer for the Python app under [`/src/snomed_post_processing`](/src/snomed_post_processing). It also integrates every Markdown file from [imported source docs](/snomed-post-processing/source-former documentation folder/index.md) so that the project can later remove the former documentation folder without losing its documented knowledge.

## Fast orientation

- [Architecture overview](/snomed-post-processing/architecture/overview.md) - what the app does and how subsystems fit together.
- [Maintainer module map](/snomed-post-processing/modules/module-map.md) - source modules and responsibilities.
- [CLI commands](/snomed-post-processing/interfaces/cli.md) - command entry points and public workflows.
- [Streamlit GUI](/snomed-post-processing/interfaces/gui.md) - UI tabs, file sources, and deployment form.

## Main workflows

- [RF2/Snowstorm to HDF5 policy store](/snomed-post-processing/workflows/rf2-to-hdf5.md)
- [Critical-finding logging](/snomed-post-processing/workflows/critical-finding-logging.md)
- [Sanitization suggestion generation](/snomed-post-processing/workflows/sanitization-suggestions.md)
- [Reviewed decisions and local ZIP write-back](/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md)
- [One-step sanitized INCEpTION deployment](/snomed-post-processing/workflows/inception-deployment.md)
- [Processed SNOGIT cache and BM25 fallback](/snomed-post-processing/workflows/snogit-bm25.md)

## Data and formats

- [HDF5 policy store layout](/snomed-post-processing/data/hdf5-policy-store.md)
- [JSON artifacts](/snomed-post-processing/data/json-artifacts.md)
- [INCEpTION project ZIP and CAS handling](/snomed-post-processing/data/inception-cas-and-zip.md)

## Decisions and operational notes

- [Design decisions and invariants](/snomed-post-processing/decisions/design-decisions.md)
- [Follow-ups and validation](/snomed-post-processing/operations/follow-ups.md)

## Lossless imported docs

The following pages are OKF-wrapped copies of the original `former documentation folder/*.md` content:

- [Deploying sanitized documents back to INCEpTION](/snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/inception-sanitized-deployment-workflow.md)
- [Release-view follow-ups and documentation review](/snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/release-view-follow-ups-and-docs-review.md)
- [Release-view normalization and blacklist metadata](/snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/release-view-normalization-and-blacklist-metadata.md)
- [RF2 ZIP structure notes](/snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/rf2-release-zip-structure.md)
- [RF2 release ZIP to HDF5 ingestion](/snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/rf2-to-hdf5-ingestion-design.md)
- [SNOMED sanitization design](/snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/sanitization-revised-design.md)
- [Archived source-to-target sanitization design](/snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/sanitization-source-target-design-old.md)
- [Processed SNOGIT cache and BM25 candidates](/snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/snogit-bm25-candidates-design.md)
- [Maintainer map](/snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/snomed-postprocessing-working.md)
- [SNOMED CT usage in this project](/snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/snomed-usage-analysis.md)

## Related local OKF bundles

- [SNOMED background](/snomed/index.md)

INCEpTION and pycaprio knowledge needed for this app is summarized inside this bundle, especially in [INCEpTION project ZIP and CAS handling](/snomed-post-processing/data/inception-cas-and-zip.md) and [One-step sanitized INCEpTION deployment](/snomed-post-processing/workflows/inception-deployment.md).
