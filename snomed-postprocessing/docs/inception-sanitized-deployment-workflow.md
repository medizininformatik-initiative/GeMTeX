# Deploying sanitized annotations back to INCEpTION

## Status

Planning document.

## Background

The current sanitizer can write a sanitized project ZIP by modifying exported JSON/XMI CAS members. However, INCEpTION full project import does not use those JSON/XMI convenience files as authoritative annotation contents. It imports internal serialized CAS files from:

```text
annotation_ser/
curation_ser/
```

Generating those `.ser` files directly from Python is not practical. A better deployment path is to upload sanitized JSONCAS/XMI through INCEpTION's remote API and let INCEpTION import and store the CAS internally.

Relevant OKF notes:

- `okf/inception/cas-storage-and-archive-contents.md`
- `okf/inception/remote-annotation-upload.md`
- `okf/pycaprio/sanitization-workflow-implications.md`
- `okf/pycaprio/remote-project-api.md`

## Recommended deployment strategy

Implement deployment as a workflow separate from sanitized ZIP creation:

```text
sanitize locally -> upload sanitized JSONCAS/XMI via INCEpTION remote API -> INCEpTION stores internal CAS
```

Initial target:

```text
existing INCEpTION project with existing users and schema
```

Later optional target:

```text
import project ZIP first, then upload sanitized annotations
```

## Proposed CLI workflow

Example command:

```bash
snomed-post-processing deploy-sanitized-to-inception \
  --inception-url http://localhost:8080 \
  --username remote-user \
  --password '...' \
  --project-id 123 \
  --decisions decisions.json \
  --source-project original.zip \
  --format jsoncas \
  --dry-run
```

To actually upload changes:

```bash
snomed-post-processing deploy-sanitized-to-inception \
  --inception-url http://localhost:8080 \
  --username remote-user \
  --password '...' \
  --project-id 123 \
  --decisions decisions.json \
  --source-project original.zip \
  --format jsoncas \
  --apply
```

## Proposed implementation architecture

### 1. Deployment pipeline module

Add a pipeline module, e.g.:

```text
src/snomed_post_processing/pipelines/inception_deploy.py
```

Responsibilities:

- connect to INCEpTION
- resolve project
- list remote documents and annotations
- group decisions by document/annotator
- download remote annotation CAS
- call sanitizer CAS-transform logic
- upload sanitized CAS
- write deployment report

### 2. In-memory CAS sanitizer function

Refactor existing ZIP sanitizer logic from:

```text
src/snomed_post_processing/pipelines/sanitization_run.py
```

so deployment can reuse the exact same decision semantics without writing a ZIP.

Candidate function:

```python
def sanitize_cas_bytes(
    cas_bytes: bytes,
    decisions: Sequence[SanitizationDecision],
    *,
    document: str,
    annotator: str,
    cas_format: str = "jsoncas",
    manual_review_layer: str = "webanno.custom.ManualReview",
) -> bytes:
    ...
```

The deployment workflow must not duplicate replacement/deletion/manual-edit logic.

Decision precedence remains:

```text
manual_edit > delete > apply > keep unchanged
```

### 3. INCEpTION client layer

Use `pycaprio` where possible, or a small internal wrapper around pycaprio/direct requests.

Useful pycaprio calls:

```python
client.api.projects()
client.api.project(project)
client.api.documents(project)
client.api.annotations(project, document)
client.api.annotation(project, document, user_name, annotation_format="jsoncas")
client.api.create_annotation(project, document, user_name, content, annotation_format="jsoncas", annotation_state=state)
client.api.curation(project, document, curation_format="jsoncas")
client.api.create_curation(project, document, content, curation_format="jsoncas")
```

pycaprio caveat: `import_project(...)` currently does not expose INCEpTION import parameters:

```text
createMissingUsers
importPermissions
```

If we later support project import as part of deployment, we may need either:

- a small pycaprio extension, or
- direct `requests` calls for project import.

## Matching model

Deployment should match reviewed decisions to remote annotation CASes by:

```text
document
annotator
```

This mirrors current sanitizer grouping behavior.

Inside each CAS, matching remains conservative by the existing annotation identity fields, e.g.:

```text
layer
offset
source_code
covered_text
```

## Annotation deployment flow

For each `(document, annotator)` with decisions:

1. Find matching remote source document.
2. Find matching remote annotation for that annotator.
3. Download annotation CAS as JSONCAS or XMI.
4. Sanitize CAS in memory.
5. Upload modified CAS back using create/update annotation endpoint.
6. Preserve previous annotation state where possible.
7. Record result in deployment report.

Remote upload endpoint behavior in INCEpTION:

```text
POST /api/aero/v1/projects/{projectId}/documents/{documentId}/annotations/{annotatorId}
```

INCEpTION imports the uploaded file into a CAS and writes it into internal CAS storage via `documentService.writeAnnotationCas(...)`.

## Curation deployment flow

Support curation as an explicit option, e.g.:

```bash
--include-curation
```

For curation documents:

1. Download curation CAS.
2. Apply decisions associated with curation pseudo-user, usually `CURATION_USER`.
3. Upload with `create_curation(...)`.

Curation must not be modified implicitly unless the user requests it.

## Preflight / dry-run mode

Default behavior should be dry-run only. Uploading should require explicit `--apply`.

Preflight checks:

- INCEpTION URL reachable
- authentication succeeds
- project exists
- remote documents can be listed
- target documents exist
- target annotator users/annotation documents exist
- annotation CASes can be downloaded
- decisions can be grouped by document/annotator
- CASes can be sanitized in memory
- no unmatched critical decisions unless allowed
- manual-review layer exists if manual-edit actions are present
- optional backup export can be created if requested

Preflight summary example:

```text
documents matched: 12
annotations to update: 18
replacements: 42
deletions: 7
manual-edit markers: 3
unmatched decisions: 0
missing documents: 0
missing annotators: 0
manual-review layer required: yes
manual-review layer available: yes
```

## Safety defaults

Deployment should be conservative:

- default to `--dry-run`
- require explicit `--apply` for uploads
- never delete remote projects
- never overwrite/import over a remote project automatically
- do not print passwords/tokens
- write a deployment report JSON
- offer optional project backup export before applying

Possible backup option:

```bash
--backup-project-export remote-backup.zip
```

## Manual-review layer handling

Manual-edit decisions add marker annotations on a configurable layer, default:

```text
webanno.custom.ManualReview
```

The first deployment implementation should require this layer to already exist in the target INCEpTION project when manual-edit decisions are present.

Reason: pycaprio does not currently expose annotation schema/layer creation APIs.

Preflight should fail if:

- manual-edit decisions exist, and
- the configured manual-review layer is missing remotely.

Later options:

1. document manual layer creation steps for INCEpTION users
2. import a schema-adjusted project ZIP first
3. use raw INCEpTION schema APIs if available
4. implement an INCEpTION-side plugin/importer

## Compatibility constraints

INCEpTION remote annotation upload validates compatibility with the source document.

The sanitized CAS must preserve:

- document text
- sentence offsets
- token offsets

The sanitizer must not modify source text or segmentation.

## Deployment report

Write a machine-readable report, e.g.:

```json
{
  "project_id": 123,
  "dry_run": true,
  "format": "jsoncas",
  "documents_matched": 12,
  "annotations_to_update": 18,
  "actions": {
    "replace": 42,
    "delete": 7,
    "manual_edit": 3,
    "keep_unchanged": 15
  },
  "unmatched_decisions": [],
  "missing_documents": [],
  "missing_annotators": [],
  "uploads": []
}
```

For apply mode, include per-upload status:

```json
{
  "document": "Boeck.txt.xmi",
  "annotator": "shams",
  "state_before": "IN_PROGRESS",
  "state_after": "IN_PROGRESS",
  "changed_annotation_count": 4,
  "uploaded": true
}
```

## Implementation stages

### Stage A: deploy to existing project

Implement deployment to an existing project with:

- existing users
- existing source documents
- existing annotation documents
- existing schema/layers

This is the smallest useful and safest version.

### Stage B: GUI support

Add GUI support after the CLI pipeline works.

Possible UI section:

```text
Deploy to INCEpTION
```

Inputs:

- INCEpTION URL
- username
- password/token
- project selector or project ID
- decisions JSON
- dry run button
- apply button
- report download

### Stage C: optional project import

Support:

```text
import sanitized-schema ZIP -> upload sanitized annotations
```

This requires handling project import options:

```text
createMissingUsers
importPermissions
```

Since pycaprio does not expose them today, use either a pycaprio extension or direct requests.

### Stage D: schema/layer automation

Investigate INCEpTION schema APIs for creating custom layers/features remotely.

If available, add automatic provisioning for:

```text
webanno.custom.ManualReview
```

with features:

```text
source_code
covered_text
suggestion_status
suggested_replacement
review_note
```

## Recommended first milestone

Implement:

```text
Deploy sanitized annotations to an existing INCEpTION project via remote JSONCAS upload
```

Do not attempt to generate `.ser` files.

Do not attempt project import or remote schema creation in the first milestone.
