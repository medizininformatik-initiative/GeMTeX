---
type: Workflow
title: One-step sanitized INCEpTION deployment
description: Conservative shell-project plus flattened CAS upload workflow for deploying reviewed sanitization decisions to INCEpTION.
resource: /src/snomed_post_processing/pipelines/inception_apply_upload.py
tags: [workflow, inception, deployment, pycaprio, jsoncas, xmi]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: deployment-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/inception-sanitized-deployment-workflow.md
    title: Deploying sanitized documents back to INCEpTION
  - id: apply-upload
    resource: /src/snomed_post_processing/pipelines/inception_apply_upload.py
    title: One-step deployment pipeline
  - id: deployment-code
    resource: /src/snomed_post_processing/pipelines/inception_deployment.py
    title: INCEpTION deployment implementation
---

# Preferred strategy

Use a bare-bones full INCEpTION project ZIP only to initialize schema/layers, then upload sanitized JSONCAS/XMI content through the INCEpTION remote API/pycaprio.

```text
original project ZIP + reviewed decisions JSON
        |
schema shell ZIP
        |
flattened sanitized repaired CAS upload artifacts
        |
dry-run report OR pycaprio remote deployment
```

This avoids generating Java-serialized `.ser` CAS files from Python.

# Public one-step command

Dry-run/offline preparation:

```bash
uv run apply-decisions-to-inception \
  --source-project original-project.zip \
  --decisions reviewed-sanitization-decisions.json \
  --output-dir sanitized-inception-output
```

Real remote apply:

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

Remote writes require explicit `--apply`; otherwise the deployment step validates inputs and writes reports only.

# One-step output layout

```text
<output-dir>/
  <source-name>-sanitized-shell.zip
  inception-upload-artifacts/
    *.json / *.xmi
    inception-upload-artifacts-report.json
  inception-sanitized-deployment-report.json
  inception-apply-decisions-upload-report.json
```

# Shell project

`build_inception_shell_project` derives a shell ZIP from the original project export. It:

- rewrites project name/slug/description;
- preserves layer definitions from `exportedproject.json`;
- ensures `webanno.custom.ManualReview` exists;
- clears source and annotation document metadata by default;
- clears curated/curation metadata to avoid stale curation records;
- omits annotation/curation content folders and `.ser` files;
- may retain support files such as `TypeSystem.xml` and `project.properties`.

# Flattened upload artifacts

`build_inception_upload_artifacts` extracts real annotation/curation JSONCAS/XMI members from the original project, skips `INITIAL_CAS.*` and `.ser`, applies decisions with `sanitize_cas_bytes`, repairs CAS for remote upload by default, and writes one file per original document/annotator CAS.

Flattened remote naming:

```text
<original-document-stem>__ann-<annotator>.json|.xmi
<original-document-stem>__curation.json|.xmi
```

The original multi-annotator structure is intentionally flattened: annotator identity is encoded in document names and deployment metadata, not remote annotation ownership.

# Deployment apply behavior

`deploy_inception_sanitized_project` validates the shell and artifact report. With `apply=True`, it:

1. creates a pycaprio client;
2. imports the shell ZIP as a new project;
3. creates each flattened source document from the CAS bytes;
4. uploads corresponding annotations for `annotation_user`;
5. writes a deployment report.

Compatibility handling accounts for pycaprio version differences:

- installed `Pycaprio` may not accept a `verify` constructor parameter;
- installed `create_document(...)` may not accept `filename`.

# CAS remote-upload repair

INCEpTION remote upload is stricter than full project import. Persisted artifacts are repaired by default to satisfy CasDoctor/editor constraints:

- add `de.tudarmstadt.ukp.clarin.webanno.api.type.CASMetadata` when missing;
- remove `de.tudarmstadt.ukp.dkpro.core.api.metadata.type.DocumentMetaData` to avoid unreachable instances;
- trim sentence boundaries to avoid leading/trailing whitespace;
- remove whitespace-only sentence spans;
- avoid overlapping sentence spans;
- ensure project/custom annotations are inside sentence coverage;
- ensure every non-whitespace text region is covered by exactly one non-overlapping sentence span.

Whitespace-only gaps may remain outside sentences.

# Deployment reports

Reports include dry-run/applied state, planned uploads, warnings/errors, shell/artifact paths, project IDs/names after apply, upload results, unmatched/skipped decisions, and remote-upload compatibility issue counts.

# Deferred preserve-annotators mode

Preserving annotators would require source documents, matching users, ownership, compatible initial CAS text/sentence/token offsets, and remote annotation upload per annotator. This is intentionally deferred until flattened mode is proven.

# Related concepts

- [INCEpTION ZIP and CAS handling](/snomed-post-processing/data/inception-cas-and-zip.md)
- [Reviewed decisions and write-back](/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md)
- [GUI deployment UI](/snomed-post-processing/interfaces/gui.md)
