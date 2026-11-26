---
type: Design Note
title: Future work
description: Deferred enhancements for annotation-store identity and INCEpTION document status handling.
tags: [future-work, annotation-store, inception, site-identity, curation]
status: draft
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: sql-store-input
    resource: /docs/sql-store-as-input.md
    title: SQLite annotation-store input limitation
  - id: inception-zip-code
    resource: /src/snomed_post_processing/uima_processing/io.py
    title: INCEpTION ZIP metadata and CAS discovery
  - id: inception-project-code
    resource: /src/snomed_post_processing/uima_processing/project.py
    title: INCEpTION project processing
---

# Future work

These items are intentionally documented but are not part of the current implementation.

## Make annotation-store document identity site-aware

The SQLite annotation-store adapter currently identifies a document by:

```text
(document name, trimmed/lowercased annotator name)
```

If the same pair occurs across sites in the selected scope, processing fails explicitly; records are not merged or overwritten. Selecting a single export can avoid the collision.

For combined-site processing, make identity site-aware, for example `(site, document name)`, and carry that distinction through findings, document context, review, generated artifacts, and any write-back or deployment paths. The same annotator name should then be allowed at different sites without conflating annotations.

## Respect INCEpTION document curation status

An INCEpTION project ZIP can expose document status in `exportedproject.json`, such as `ANNOTATION_FINISHED` or `CURATION_FINISHED`. The ZIP reader currently uses the source document name to locate CAS members and does not retain or interpret the status. Processing also considers matching annotation and curation CAS paths without filtering on that status.

If needed later, expose document status in the project model and add an explicit, opt-in filter or processing mode for curated, non-curated, or otherwise status-selected documents. The default behavior should remain unchanged unless a clear compatibility policy is defined for annotation CAS versus curation CAS.
