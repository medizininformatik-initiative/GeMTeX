# SNOMED Postprocessing — maintainer map

This file is a compact code map for maintainers. User-facing usage belongs in `README_alt.md`; design details belong in the focused docs under `docs/`.

## Entry points

| Command / UI | Module | Purpose |
|---|---|---|
| `log-critical-documents` | `snomed_post_processing.cli.app` | Check INCEpTION/UIMA annotations against policy views and write critical reports. |
| `create-concepts-dump` | `snomed_post_processing.cli.app` | Build/update SNOMED HDF5 files from RF2 ZIPs or Snowstorm. |
| `summarize-hdf5` | `snomed_post_processing.cli.app` | Inspect HDF5 metadata and policy views. |
| `suggest-sanitization` | `snomed_post_processing.cli.app` | Generate replacement suggestions from `CriticalFindings` JSON. |
| `build-snogit-cache` | `snomed_post_processing.cli.app` | Build a processed SNOGIT cache HDF5 for BM25 evidence. |
| Streamlit GUI | `snomed_post_processing.gui.app` | Browser UI for check, suggestion, review/apply workflows. |

## Core workflow modules

| Area | Main modules |
|---|---|
| Critical finding JSON | `findings_io/json_io.py`, `findings_io/mapping.py` |
| INCEpTION ZIP/CAS reading | `uima_processing/io.py`, `uima_processing/project.py`, `uima_processing/extraction.py` |
| Report generation | `uima_processing/report_creation.py`, `gui/report_generation.py` |
| RF2 ingestion | `release_ingestion/readers.py`, `release_ingestion/hdf5_writer.py` |
| HDF5 policy/layout helpers | `hdf5_handling/policy.py`, `hdf5_handling/metadata.py`, `hdf5_handling/dump.py` |
| Sanitization resolver | `sanitization/resolver.py`, `sanitization/models.py`, `sanitization/report.py` |
| BM25/SNOGIT fallback | `sanitization/bm25_index.py`, `sanitization/semantic_bm25.py`, `sanitization/snogit_sidecar.py` |
| Review/apply decisions | `sanitization/decisions_json.py`, `pipelines/sanitization_run.py` |
| Streamlit GUI tabs | `gui/policy_tab.py`, `gui/sanitization_check_tab.py`, `gui/sanitization_run_tab.py` |

## Data flow

```text
INCEpTION ZIP + SNOMED HDF5
        |
log-critical-documents / GUI check
        |
CriticalFindings JSON
        |
suggest-sanitization / GUI suggestions
        |
SanitizationSuggestions Markdown + JSON
        |
review decisions JSON
        |
sanitization run -> copied sanitized INCEpTION ZIP
```

The original project ZIP is never modified in place. `.ser` files are excluded from sanitized exports.

## Target-view gates

Policy mode remains authoritative for the current GeMTeX policy workflow:

```text
active AND whitelisted AND not blacklisted
```

Release mode is for normalization against the selected SNOMED release:

```text
active, plus optional embedded/custom blacklist exclusions
```

The helper layer in `hdf5_handling/policy.py` centralizes candidate validity so historical, ancestor, BM25, and SNOGIT paths use the same gates.

## File input patterns

The GUI should use the shared file source selector for large or server-side files:

```text
Upload
Data directory
Server path
```

This applies to INCEpTION ZIPs, HDF5 files, CriticalFindings JSON, processed SNOGIT caches, SNOGIT ZIPs, and custom blacklist rule files.

## Related docs

- User guide: `README_alt.md`
- RF2 ingestion: `docs/rf2-to-hdf5-ingestion-design.md`
- Sanitization: `docs/sanitization-revised-design.md`
- Release view / blacklist modes: `docs/release-view-normalization-and-blacklist-metadata.md`
- SNOGIT/BM25: `docs/snogit-bm25-candidates-design.md`
- Follow-ups/docs review: `docs/release-view-follow-ups-and-docs-review.md`
