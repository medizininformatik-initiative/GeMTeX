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
| `build-snogit-cache` | `cli.app:build_snogit_cache_cli` | Create processed SNOGIT cache for BM25 evidence from a SNOGIT ZIP or single `.dat` file. |
| `suggest-sanitization` | `cli.app:suggest_sanitization_cli` | Generate Markdown/JSON sanitization suggestions. |
| `build-inception-shell-project` | `cli.app:build_inception_shell_project_cli` | Lower-level shell ZIP builder. |
| `build-inception-upload-artifacts` | `cli.app:build_inception_upload_artifacts_cli` | Lower-level repaired flattened CAS artifact builder. |
| `apply-decisions-to-inception` | `cli.app:apply_decisions_to_inception_cli` | Preferred one-step reviewed-decisions-to-INCEpTION workflow. |
| `deploy-inception-sanitized-project` | `cli.app:deploy_inception_sanitized_project_cli` | Lower-level deployment planner/applier. |
| `list-branches` | `cli.app:list_branches` | List Snowstorm branches. |
| `program-entry` | `cli.app:help_me` | Compatibility/help entry. |

# Common public workflows

## Check annotated documents

`log-critical-documents` checks configured annotation layers and normalizes a configured annotation ID feature to a plain SCTID. Use `--id-feature` for workflows that use a feature other than `id`; use `--id-prefix` to match workflows that store IDs with a different URI/string prefix. The default prefix is `http://snomed.info/id/`, and an empty value supports plain SCTIDs. See [Annotation layer requirements](/snomed-post-processing/data/annotation-layer-requirements.md).

### Interactive annotator selection

`inception/io.py:prompt_for_names` uses the existing Click dependency (PyInquirer removed). Zero/one annotator returns `None` without prompting; otherwise **Include all?** defaults to no. Yes returns `None` (all); no displays sorted original annotator names numbered from 1. Enter comma-separated numbers such as `1,3`; whitespace is accepted and duplicate numbers are deduplicated in input order. Selected original names are returned unchanged, with lowercase filtering still performed by the existing pipeline. Empty, malformed or out-of-range selections retry instead of falling back to all. EOF/Ctrl+C raises `click.Abort` and stops before processing. `--forbid-prompt` still bypasses selection and processes all annotators; Docker's existing non-interactive behavior is unchanged.

The PyInquirer dependency and orphaned prompt-toolkit/regex/wcwidth packages are removed from `uv.lock`; Pygments remains needed by pytest. Other retained package versions remain unchanged. Removing PyInquirer cleared its confirmed Python 3.11 import blocker. Before runtime configuration migration, 50 focused Python 3.9 regression tests and 10 prompt tests under the installed Python 3.11 interpreter passed; the latter reuse pure-Python sources only, not a fully migrated environment.

The project now targets Python 3.11.x (`requires-python = "~=3.11.0"`, `.python-version` = `3.11`, Docker base `python3.11-bookworm-slim`). The initial 62-package migration lock preserved retained versions. Enabling the optional `nicegui` extra subsequently expanded the cross-platform lock to 100 packages (99 installed on Windows) and updated certifi/idna/Pygments only; offline lock and installed dependency checks pass. Python-3.9-only dependencies exceptiongroup/tomli/zipp were pruned by resolution. The shared `.venv-py311` is installed under Python 3.11.13 with both frontends via `uv sync --locked --extra nicegui`. Dependency consistency, core/native imports and all 11 CLI help entry points pass. After optional NiceGUI integration and launcher tests, the full suite reports 280 passed, 3 existing GUI-default failures and 2 warnings; the same three failures were reproduced in the retained Python 3.9 environment. See the migration validation section in `operations/follow-ups.md`. The existing 3.9 `.venv` is untouched. Use `UV_PROJECT_ENVIRONMENT=.venv-py311` to avoid replacing it through automatic uv sync, and keep `--extra nicegui` on uv run/sync commands to retain that optional frontend. No live INCEpTION calls or Docker build were performed.

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
- `--bm25-semantic-tag-boost-percent P` (default 10, range 0–100; 0 disables the matching-FSN-tag score bonus). FSN tags are excluded from lexical matching, not from stored/displayed labels.
- `--use-snogit-cache processed_snogit_cache.hdf5`
- `--blacklist-suggestions` only with BM25 fallback

## One-step INCEpTION deployment

Dry-run/offline preparation:

```bash
uv run apply-decisions-to-inception \
  --source-project original-project.zip \
  --decisions reviewed-sanitization-decisions.json \
  --output-dir sanitized-inception-output
```

Use `--id-feature` and `--id-prefix` here as well when reviewed decisions should match/write IDs using a non-default annotation ID feature or prefix.

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
