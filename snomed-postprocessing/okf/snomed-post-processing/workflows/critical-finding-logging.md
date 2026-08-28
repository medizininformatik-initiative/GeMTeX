---
type: Workflow
title: Critical-finding logging
description: How annotated INCEpTION/UIMA projects are checked against SNOMED policy views.
resource: /src/snomed_post_processing/pipelines/document_logging.py
tags: [workflow, critical-findings, uima, inception, policy-check]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: analysis
    resource: /src/snomed_post_processing/uima_processing/analysis.py
    title: UIMA policy analysis implementation
  - id: extraction
    resource: /src/snomed_post_processing/uima_processing/extraction.py
    title: Annotation extraction implementation
  - id: maintainer-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/snomed-postprocessing-working.md
    title: Maintainer map
---

# Goal

Identify SNOMED-coded annotations that violate a whitelist or blacklist policy and materialize them as structured `CriticalFinding` records plus human-readable reports.

# Inputs

- INCEpTION project ZIP, flat CAS archive, or remote INCEpTION project export.
- HDF5 policy file containing whitelist/blacklist policy data.
- Annotation layer names, defaulting to Concept-like layers such as `gemtex.Concept` and `webanno.custom.Concept` in current CLI options.
- Optional ignore-overlap layer settings to suppress findings covered by designated annotations.

# Annotation extraction

UIMA CAS annotations are loaded from JSONCAS/XMI/nested ZIP members. `.ser` files may be recognized for discovery, but Python editing/upload workflows prefer JSONCAS/XMI and avoid direct `.ser` generation.

SNOMED IDs are expected in an annotation feature named `id`, often shaped like:

```text
http://snomed.info/id/<SCTID>
```

The app normalizes this to the plain SCTID string for policy checks.

Each extracted annotation can carry:

- code;
- covered text;
- offset begin/end;
- annotation layer;
- ignore-overlap status and overlap details.

# Policy analysis

`uima_processing.analysis.analyze_documents` performs exact-ID checks:

| Check | Critical when |
|---|---|
| Whitelist | code is not in whitelist policy array. |
| Blacklist | code is in blacklist policy array. |

Ignored findings can still be recorded as informational findings with `ignored=True`, but ignored findings are not sanitized automatically.

# CriticalFinding shape

`CriticalFinding` records include:

```text
annotator
document
code
covered_text
offset
list_type
reason
layer
fsn
ignored
ignore_overlaps
```

They are serialized via `/src/snomed_post_processing/findings_io/json_io.py` and mapped with `/src/snomed_post_processing/findings_io/mapping.py`.

# Output

The logging pipeline writes Markdown reports and can write a `CriticalFindings` JSON artifact consumed by [sanitization suggestion generation](/snomed-post-processing/workflows/sanitization-suggestions.md).

# Related concepts

- [INCEpTION ZIP and CAS handling](/snomed-post-processing/data/inception-cas-and-zip.md)
- [JSON artifacts](/snomed-post-processing/data/json-artifacts.md)
- [HDF5 policy store](/snomed-post-processing/data/hdf5-policy-store.md)
