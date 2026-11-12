---
type: Data Format
title: INCEpTION project ZIP and CAS handling
description: How the app reads INCEpTION project archives, CAS members, source/annotation metadata, and remote-upload-compatible CAS.
resource: /src/snomed_post_processing/uima_processing/io.py
tags: [data-format, inception, uima, cas, jsoncas, xmi, zip]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: deployment-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/inception-sanitized-deployment-workflow.md
    title: Deploying sanitized documents back to INCEpTION
  - id: io-code
    resource: /src/snomed_post_processing/uima_processing/io.py
    title: UIMA ZIP/CAS IO helpers
  - id: deployment-code
    resource: /src/snomed_post_processing/pipelines/inception_deployment.py
    title: Remote upload CAS repair implementation
---

# INCEpTION full project archive model

INCEpTION full project ZIPs treat metadata and CAS content differently:

```text
exportedproject.json
  -> project metadata
  -> source document metadata
  -> annotation document metadata
  -> layers/features/tagsets
  -> users/permissions metadata

annotation_ser/
curation_ser/
  -> authoritative annotation/curation CAS content during full import
```

The app edits JSONCAS/XMI CAS members but does not generate Java serialized `.ser` files from Python.

# Readable CAS members

The UIMA IO helpers support JSONCAS, XMI, nested CAS ZIPs, and discovery of `.ser`. For actual Python sanitization/write-back/upload, JSONCAS and XMI are preferred.

Ignored ZIP members include directories, macOS resource forks, `.DS_Store`, top-level `TypeSystem.xml`, and `exportedproject.json` during CAS iteration. `INITIAL_CAS.*` members are skipped for flat archive/upload artifact generation.

If non-`.ser` CAS files exist, they are preferred over `.ser` files.

# Document/annotator discovery

When `exportedproject.json` has `source_documents`, the app searches matching paths under:

```text
curation/<document>/
annotation/<document>/
curation_ser/<document>/
annotation_ser/<document>/
```

When metadata is absent/empty, the app falls back to flat archive layout and derives document/annotator names from paths.

# Shell project deployment strategy

For sanitized INCEpTION deployment, full project import is used only to transfer project schema/layers. The shell ZIP usually contains `exportedproject.json` and support files, but omits source documents, annotation documents, annotation CAS, curation CAS, and `.ser` content.

# Remote-upload CAS compatibility

Remote upload through pycaprio/INCEpTION triggers stricter CasDoctor/editor checks than plain archive manipulation. The app repairs JSONCAS/XMI artifacts by default before persisting/uploading them.

Repair invariants:

```text
Every non-whitespace text region is inside exactly one non-overlapping Sentence span.
Whitespace-only gaps may remain outside sentences.
Project/custom annotations must start/end inside sentence coverage.
CASMetadata must be present.
DocumentMetaData is removed.
Sentence spans must not overlap or start/end with whitespace.
```

Relevant INCEpTION issues addressed by repair:

```text
CAS contains no CASMetadata. Cannot check concurrent access.
starts and ends outside any sentence
DocumentMetaData unreachable instances
Sentence overlaps with previous sentence
Sentence ends with whitespace
Unable to load annotations: Start position of range [...] is not part of any visible row.
```

# Synthetic offline workflow fixture

`test/projects/synthetic-annotator-scope/` contains an artificial project ZIP with Alice/JSONCAS and Bob/XMI across three documents, a tiny synthetic HDF5 policy, generated findings/suggestions, default rule JSON, staged decisions, expected counts, and a GUI walkthrough in its `README.md`. No clinical CAS or real release data is copied from the structural ZIP template.

Both annotators produce ten findings total, four Number/Date rule decisions and two additional historical automatic selections. Negative controls remain manual: ambiguous historical targets, an exclusion-list finding and an unknown code. Date is included and absent from findings but still matches its rule; its target requires a policy override. Alice-only processing yields five findings, two rules, one automatic selection, three local ID changes and three upload artifacts; Bob CAS remains unchanged locally and is omitted from artifacts.

`test/create_synthetic_annotator_dataset.py` rebuilds the seven generated assets into a new directory (refuses overwrite). `test/test_synthetic_annotator_dataset.py` verifies real checker/resolver/conditions, GUI interactions for both scopes, feature preservation, local write-back and offline upload preparation. This fixture is not validated as a native INCEpTION full-project restore or live upload. See the fixture README for exact settings; BM25/SNOGIT and ancestor fallback are disabled for deterministic historical automation.

# Related concepts

- [INCEpTION deployment](/snomed-post-processing/workflows/inception-deployment.md)
- [Reviewed decisions and write-back](/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md)
