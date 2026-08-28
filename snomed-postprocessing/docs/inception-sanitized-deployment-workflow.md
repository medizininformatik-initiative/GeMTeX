# Deploying sanitized documents back to INCEpTION

## Status

Planning document. Current preferred strategy: use a **bare-bones full project ZIP** to initialize a new sanitized INCEpTION project with the required schema/layers, then upload sanitized JSONCAS/XMI content through the remote API/pycaprio.

This replaces earlier ideas of direct `.ser` generation, relying on document import to create layers, or requiring manual `TypeSystem.xml` import as the main workflow.

## Background

INCEpTION full project import treats different parts of the ZIP differently:

```text
exportedproject.json
  -> project metadata
  -> source document metadata
  -> annotation document metadata
  -> layers/features/tagsets
  -> users/permissions metadata

annotation_ser/
curation_ser/
  -> authoritative annotation/curation CAS content
```

The sanitizer currently edits JSON/XMI CAS members, but INCEpTION full project import uses `.ser` CAS files for annotation/curation contents. We should not attempt to generate Java serialized `.ser` files from Python.

However, full project import creates project schema from `exportedproject.json`, not from `.ser` files. This gives us a practical deployment route:

```text
1. build/import a sanitized project shell ZIP carrying schema/layers
2. upload sanitized JSONCAS/XMI content later through INCEpTION remote API
3. let INCEpTION store the uploaded CAS internally
```

Relevant OKF notes:

- `okf/inception/project-archive-import.md`
- `okf/inception/project-metadata.md`
- `okf/inception/cas-storage-and-archive-contents.md`
- `okf/inception/users-and-permissions.md`
- `okf/inception/remote-annotation-upload.md`
- `okf/pycaprio/remote-project-api.md`
- `okf/pycaprio/remote-annotation-curation-api.md`
- `okf/pycaprio/formats-and-payloads.md`

## Preferred deployment strategy

Use full project ZIP import only for project initialization and schema transfer:

```text
original exported project ZIP
-> derive bare-bones sanitized project shell ZIP
-> import shell ZIP into INCEpTION
-> upload sanitized documents/annotations with pycaprio
```

The shell ZIP should create a new project with:

- sanitized project name/slug/description
- original relevant annotation layers/features
- added manual-review layer/features
- optional tagsets required by features
- optionally source-document metadata/files, depending on deployment mode
- optionally user/permission metadata, depending on deployment mode

The shell ZIP does **not** need to contain authoritative sanitized annotation contents in `.ser` form.

## Why this should solve the schema problem

INCEpTION schema import for full project ZIPs uses:

```java
LayerExporter.importData(...)
importLayers(aProject, aExProject)
aExProject.getLayers()
```

So layers/features are imported from `exportedproject.json`.

This means a custom-made `exportedproject.json` can carry our required layers, including:

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

The `.ser` files are not needed to create layers. They only matter for annotation/curation CAS content during full project import.

## Shell ZIP shape

A minimal shell ZIP should contain at least:

```text
exportedproject.json
```

Depending on the selected content-upload mode, it may also contain:

```text
source/<document-name>
```

and matching `source_documents` metadata in `exportedproject.json`.

It should usually omit:

```text
annotation_ser/
curation_ser/
annotation/
curation/
```

unless we intentionally want initial unsanitized CAS content imported before later overwrite. The preferred workflow is to avoid importing unsanitized annotation content at all.

## `annotation_documents` can likely be empty

The annotation-document importer loops over:

```java
aExProject.getAnnotationDocuments()
```

If the list is empty, it should create no annotation-document records. If the ZIP contains no `annotation_ser/*.ser` entries, annotation CAS content import should simply skip content import.

So for a schema-only project shell, this should be acceptable:

```json
"annotation_documents": []
```

For preserve-annotators mode, annotation documents can instead be created later by remote annotation upload.

## `source_documents` can likely be empty

If we plan to upload all sanitized content later as new source documents via pycaprio, then `source_documents` can likely be empty as well.

This gives a very small shell project:

```text
exportedproject.json with project metadata + schema/layers
no source docs
no annotation docs
no CAS content
```

This must be tested against INCEpTION import, but the code path suggests it should work.

## User and permission behavior on shell import

INCEpTION has two relevant user categories during project import.

### Project-bound users

Project-bound users listed in `exportedproject.json` are always attempted to be recreated.

If a project-bound username already exists in the target INCEpTION instance, creation is rejected and INCEpTION warns that annotations of this user may not be accessible.

Permissions for successfully created project-bound users are imported.

### Normal users

Normal/non-project users are created only if project import is called with:

```text
createMissingUsers = true
```

Created missing users are disabled and have no password.

pycaprio currently does not expose these project-import flags:

```text
createMissingUsers
importPermissions
```

So if we need those flags, we should use direct `requests` for project import or extend our pycaprio wrapper.

### Practical implication

For the first implementation, avoid depending on recreated original users unless necessary.

This favors a first milestone where sanitized outputs are uploaded as separate source documents, with original annotator identity encoded into the document name.

## Deployment mode selected for first implementation

Use **flattened sanitized documents** as the first serious implementation target.

Remote structure:

```text
Boeck__ann-shams.xmi
Boeck__ann-abdelwaha.xmi
Boeck__curation.xmi
```

Workflow:

1. Build a sanitized schema-shell ZIP from the original project export.
2. Import the shell ZIP into INCEpTION to create the sanitized project.
3. Generate sanitized CAS bytes locally for each original document/annotator pair.
4. Upload each sanitized CAS as a new source document with a unique name.
5. Record mapping from original `(document, annotator)` to remote document name/ID.

Pros:

- creates a clean separate sanitized project
- avoids `.ser` generation
- avoids needing original annotator users
- avoids annotation-document ownership complexity
- avoids duplicate document-name conflicts by generated naming
- still allows inspection of sanitized documents in INCEpTION

Trade-off:

- original multi-annotator structure is flattened into source documents
- annotator identity is represented in document names and deployment metadata, not INCEpTION annotator ownership

## Future mode: preserve annotators

Preserving annotators remains useful, but is not the first implementation target.

Remote structure:

```text
Document: Boeck.txt.xmi
  Annotation by shams
  Annotation by abdelwaha
  Curation by CURATION_USER
```

This mode would require:

- source documents in the target project
- corresponding annotator users to exist
- compatible initial CAS text/sentence/token offsets
- remote annotation upload per annotator

It should be deferred until after the shell-ZIP + flattened-documents workflow is proven.

## Proposed CLI workflow

### Step 1: create/import project shell

```bash
snomed-post-processing deploy-sanitized-to-inception \
  --inception-url http://localhost:8080 \
  --username remote-user \
  --password '...' \
  --source-project original-project.zip \
  --decisions decisions.json \
  --create-shell-project \
  --project-name "Original project (sanitized)" \
  --project-slug original-project-sanitized \
  --mode flattened-documents \
  --dry-run
```

Apply:

```bash
snomed-post-processing deploy-sanitized-to-inception \
  --inception-url http://localhost:8080 \
  --username remote-user \
  --password '...' \
  --source-project original-project.zip \
  --decisions decisions.json \
  --create-shell-project \
  --project-name "Original project (sanitized)" \
  --project-slug original-project-sanitized \
  --mode flattened-documents \
  --apply
```

The command should:

1. generate the shell ZIP
2. import it as a new project
3. upload sanitized documents
4. write a deployment report

### Step 2 alternative: prebuild shell ZIP

For debugging or manual workflows:

```bash
snomed-post-processing build-inception-shell-project \
  --source-project original-project.zip \
  --output-project-shell sanitized-shell.zip \
  --project-name "Original project (sanitized)" \
  --project-slug original-project-sanitized
```

Then:

```bash
snomed-post-processing deploy-sanitized-to-inception \
  --inception-url http://localhost:8080 \
  --username remote-user \
  --password '...' \
  --project-shell sanitized-shell.zip \
  --decisions decisions.json \
  --source-project original-project.zip \
  --mode flattened-documents \
  --apply
```

## Proposed implementation architecture

### 1. Shell project builder

Add a module/function that derives a project shell ZIP from an original exported project ZIP.

Candidate location:

```text
src/snomed_post_processing/pipelines/inception_shell_project.py
```

Responsibilities:

- read original `exportedproject.json`
- rewrite project identity:
  - `name`
  - `slug`
  - `description`
- preserve/export layer definitions
- add/ensure `webanno.custom.ManualReview` layer and features
- preserve needed tagsets
- optionally clear source documents
- clear annotation documents for flattened mode
- omit annotation/curation CAS content folders
- write shell ZIP

### 2. Deployment pipeline

Candidate location:

```text
src/snomed_post_processing/pipelines/inception_deploy.py
```

Responsibilities:

- authenticate to INCEpTION
- import shell ZIP
- discover created project ID
- generate sanitized CAS bytes locally
- upload sanitized CASes as source documents
- write deployment report

### 3. In-memory CAS sanitizer function

Refactor existing ZIP sanitizer logic from:

```text
src/snomed_post_processing/pipelines/sanitization_run.py
```

so deployment can reuse the same decision semantics without writing a full sanitized ZIP.

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

Decision precedence remains:

```text
manual_edit > delete > apply > keep unchanged
```

### 4. INCEpTION client layer

Use pycaprio where possible.

Useful pycaprio calls:

```python
client.api.import_project(project_shell_zip)
client.api.create_document(project, document_name, content, document_format="jsoncas", document_state=...)
client.api.projects()
client.api.documents(project)
```

If pycaprio import lacks required import flags, use direct `requests` for:

```text
POST /api/aero/v1/projects/import
```

with optional parameters:

```text
createMissingUsers
importPermissions
```

For flattened mode, these flags should usually not be necessary.

## Document naming in flattened mode

Generated remote source-document names must be unique and valid for INCEpTION.

Suggested naming scheme:

```text
<original-document-stem>__ann-<annotator><extension>
<original-document-stem>__curation<extension>
```

Examples:

```text
Boeck__ann-shams.xmi
Boeck__ann-abdelwaha.xmi
Boeck__curation.xmi
```

The deployment report must record the mapping:

```json
{
  "source_document": "Boeck.txt.xmi",
  "source_annotator": "shams",
  "remote_document_name": "Boeck__ann-shams.xmi",
  "remote_document_id": 789
}
```

## Preflight / dry-run mode

Default behavior should be dry-run. Uploading should require explicit `--apply`.

Preflight checks:

- INCEpTION URL reachable
- authentication succeeds
- shell ZIP can be generated
- shell ZIP contains `exportedproject.json`
- shell `exportedproject.json` contains required layers/features
- project slug does not already exist, unless user explicitly chooses another policy
- decisions can be loaded and grouped
- sanitized CASes can be generated in memory
- generated document names are valid
- generated document names are unique
- no generated document names conflict with existing remote documents if deploying into an existing shell project
- optional project import can be performed

Preflight summary example:

```text
mode: flattened-documents
project shell: generated
project name: Original project (sanitized)
project slug: original-project-sanitized
schema layers: 7
manual-review layer: present
source documents to upload: 18
name conflicts: 0
replacements: 42
deletions: 7
manual-edit markers: 3
unmatched decisions: 0
```

## Safety defaults

Deployment should be conservative:

- default to `--dry-run`
- require explicit `--apply`
- never delete remote projects
- never overwrite/import over an existing project automatically
- fail on slug conflict by default
- do not print passwords/tokens
- write shell ZIP to a visible path or retain it in a report/artifact directory
- write a deployment report JSON

## Deployment report

Write a machine-readable report, e.g.:

```json
{
  "dry_run": false,
  "mode": "flattened-documents",
  "project_shell_zip": "sanitized-shell.zip",
  "project_id": 123,
  "project_name": "Original project (sanitized)",
  "project_slug": "original-project-sanitized",
  "format": "jsoncas",
  "actions": {
    "replace": 42,
    "delete": 7,
    "manual_edit": 3,
    "keep_unchanged": 15
  },
  "uploads": [
    {
      "source_document": "Boeck.txt.xmi",
      "source_annotator": "shams",
      "remote_document_name": "Boeck__ann-shams.xmi",
      "remote_document_id": 789,
      "changed_annotation_count": 4,
      "uploaded": true
    }
  ],
  "unmatched_decisions": [],
  "errors": []
}
```

## Implementation stages

### Stage A: prove shell ZIP import

Create tests/fixtures for a stripped shell ZIP:

- project metadata changed
- layers preserved
- `ManualReview` layer added
- `annotation_documents` empty
- no `annotation_ser` entries
- optionally no `source_documents`

Manually import into INCEpTION and verify:

- project is created
- layers/features appear in Settings > Layers
- no unsanitized annotation content is imported

### Stage B: in-memory sanitizer extraction

Refactor sanitizer logic so it can sanitize one CAS and return JSONCAS/XMI bytes without writing a full project ZIP.

### Stage C: flattened document upload

Implement shell import + sanitized source-document upload via pycaprio.

This is the first complete deployment workflow.

### Stage D: GUI integration

Add GUI controls for:

- INCEpTION URL
- username/password
- project name/slug
- shell ZIP generation/download
- dry-run
- apply
- deployment report download

### Stage E: preserve-annotators mode later

Only after flattened mode works, evaluate preserving annotator ownership using remote annotation upload.

This will require solving user handling and source-document compatibility.

## Non-goals for the first implementation

Do not attempt direct `.ser` generation.

Do not rely on JSONCAS/XMI document import to create layers automatically.

Do not require manual `TypeSystem.xml` import as the main path, because shell ZIP import should carry schema through `exportedproject.json`.

Do not implement a custom INCEpTION plugin/API unless the shell-ZIP route fails or proves insufficient.
