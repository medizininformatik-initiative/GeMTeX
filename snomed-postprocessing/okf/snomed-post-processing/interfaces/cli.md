---
type: CLI Surface
title: Command-line interface
description: Public console scripts, command intent, and important safety/default semantics.
resource: /src/snomed_post_processing/cli/app.py
tags: [cli, click, workflows]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: pyproject
    resource: /pyproject.toml
    title: Console script declarations
  - id: cli-app
    resource: /src/snomed_post_processing/cli/app.py
    title: Click command implementations
  - id: docs
    resource: /snomed-post-processing/source-docs/index.md
    title: Migrated original project docs
---

# Console scripts

`pyproject.toml` exposes these commands:

| Command | Function | Use |
|---|---|---|
| `log-critical-documents` | `cli.app:log_documents` | Check annotations and write critical reports/artifacts. |
| `create-concepts-dump` | `cli.app:create_concept_id_dump` | Create SNOMED HDF5 from RF2 ZIP or Snowstorm. |
| `summarize-hdf5` | `cli.app:summarize_hdf5` | Print HDF5 metadata summary. |
| `build-snogit-cache` | `cli.app:build_snogit_cache_cli` | Create processed SNOGIT cache for BM25 evidence. |
| `suggest-sanitization` | `cli.app:suggest_sanitization_cli` | Generate Markdown/JSON sanitization suggestions. |
| `build-annotation-store` | `cli.app:build_annotation_store_cli` | Build a merged SQLite store of SNOMED annotation occurrences from INCEpTION export ZIPs. |
| `check-annotation-store-document` | `cli.app:check_annotation_store_document_cli` | Check whether an external plain-text document content hash exists in an annotation store. |
| `build-inception-shell-project` | `cli.app:build_inception_shell_project_cli` | Lower-level shell ZIP builder. |
| `build-inception-upload-artifacts` | `cli.app:build_inception_upload_artifacts_cli` | Lower-level repaired flattened CAS artifact builder. |
| `apply-decisions-to-inception` | `cli.app:apply_decisions_to_inception_cli` | Preferred one-step reviewed-decisions-to-INCEpTION workflow. |
| `deploy-inception-sanitized-project` | `cli.app:deploy_inception_sanitized_project_cli` | Lower-level deployment planner/applier. |
| `list-branches` | `cli.app:list_branches` | List Snowstorm branches. |
| `program-entry` | `cli.app:help_me` | Compatibility/help entry. |

# Common public workflows

## Build HDF5 from RF2

```bash
uv run create-concepts-dump \
  --zip SnomedCT_Release_INT.zip \
  --output concepts.hdf5 \
  --policy-date YYYYMMDD \
  --include-ancestors \
  --dump-mode version \
  ROOT_CODE
```

Use `--filter-list` in version mode to add an embedded blacklist. Use `--dump-mode semantic` to create/update a blacklist policy view.

## Generate suggestions

```bash
uv run suggest-sanitization \
  --lists-path concepts.hdf5 \
  --critical-findings critical_findings.json \
  --output sanitization_suggestions.md
```

Important options:

- `--target-view policy|release`
- `--enforce-embedded-blacklist` for release mode
- `--custom-blacklist PATH` for release mode
- `--activate-historical-ancestor-fallback`
- `--ancestor-max-distance N` where negative disables the absolute limit
- `--ancestor-max-relative-distance R` where negative disables the relative limit
- `--semantic-bm25-fallback`
- `--use-snogit-cache processed_snogit_cache.hdf5`
- `--blacklist-suggestions` only with BM25 fallback

## Build annotation store

```bash
uv run build-annotation-store \
  --input /path/to/inception-export-zips-or-directory \
  --snomed-hdf5 concepts.hdf5 \
  --output semantic_snomed_annotations.sqlite \
  --replace
```

The command imports annotation, curation, and flat CAS views into one SQLite file. It normalizes document names, infers site and batch metadata from names such as `berlin_XMI_1-3.zip`, enriches known SCTIDs with FSN/semantic tag/active status from `/concepts`, keeps unknown SCTIDs with null metadata, stores a SHA-256 hash of each complete CAS document text for reproducibility, and reports missing batches. Full CAS document text is only stored with `--store-document-text`; covered text is always stored per annotation occurrence.

Check an external plain-text document by content hash, without relying on document names:

```bash
uv run check-annotation-store-document \
  --store semantic_snomed_annotations.sqlite \
  --document /path/to/document.txt
```

A hash match means stored annotation offsets are applicable to that exact document text.

## One-step INCEpTION deployment

Dry-run/offline preparation:

```bash
uv run apply-decisions-to-inception \
  --source-project original-project.zip \
  --decisions reviewed-sanitization-decisions.json \
  --output-dir sanitized-inception-output
```

Real remote apply requires explicit `--apply` and connection settings:

```bash
uv run apply-decisions-to-inception \
  --source-project original-project.zip \
  --decisions reviewed-sanitization-decisions.json \
  --output-dir sanitized-inception-output \
  --inception-url http://localhost:8080 \
  --username USER \
  --password-env INCEPTION_PASSWORD \
  --annotation-user USER \
  --apply
```

# Safety defaults

- Deployment commands are dry-run by default.
- Passwords should be supplied through `--password-env` rather than `--password`.
- Source project ZIPs are not modified.
- INCEpTION remote project deletion/overwriting is not automated.

# Related concepts

- [RF2 to HDF5](/snomed-post-processing/workflows/rf2-to-hdf5.md)
- [Sanitization suggestions](/snomed-post-processing/workflows/sanitization-suggestions.md)
- [INCEpTION deployment](/snomed-post-processing/workflows/inception-deployment.md)
