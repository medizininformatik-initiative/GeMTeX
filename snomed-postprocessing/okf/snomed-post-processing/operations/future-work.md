---
type: Design Note
title: Future work
description: Deferred enhancements for annotation-store identity, INCEpTION document status handling, and policy-check performance.
tags: [future-work, annotation-store, inception, site-identity, curation, policy-check, performance, threading]
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
  - id: policy-analysis-code
    resource: /src/snomed_post_processing/uima_processing/analysis.py
    title: Serial per-document policy analysis
  - id: policy-report-code
    resource: /src/snomed_post_processing/uima_processing/report_creation.py
    title: HDF5 policy loading and report coordination
  - id: nicegui-policy-code
    resource: /src/snomed_post_processing/gui/nicegui/policy_ui.py
    title: NiceGUI policy-check worker and progress bridge
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

## Improve tab 1 inclusion-list policy-check performance

NiceGUI currently runs the complete policy check through `run.io_bound`. This keeps the event loop responsive but does not parallelize the calculation itself. CAS extraction in `process_inception_zip`, document iteration in `analyze_documents`, and the inclusion/exclusion passes remain serial. Inclusion checking currently performs `np.isin` for each document against the complete inclusion-list array.

### Measure and optimize before adding concurrency

Add non-sensitive phase timings for CAS/SQLite extraction, inclusion-list analysis, exclusion-list analysis, and report generation. Record only durations and counts; do not log document names, annotators, covered text, or other clinical content.

Benchmark algorithmic improvements before threading. Repeating `np.isin(document_codes, complete_policy_array)` for every document may perform avoidable work. Compare the current implementation with:

- one batched or bounded-chunk membership operation across documents; and
- `np.searchsorted` against a verified sorted policy-code array.

A simpler lookup improvement may outperform threads while retaining lower memory use and deterministic behavior.

### Bounded document-level threading

If inclusion analysis remains a material bottleneck, extract a pure per-document calculation from `analyze_documents`. It should accept immutable document annotations and already-loaded NumPy policy arrays, then return findings, ignored findings, counts, an optional sanitized error, and the document's original sequence number. Worker functions must not mutate a shared findings list, report stream, spinner, progress object, or JSON progress file.

Use a bounded `ThreadPoolExecutor` for the analysis phase only. Start conservatively, for example with no more than four workers, and retain a serial backend default such as `max_workers=1`. The coordinator should:

1. enumerate jobs in the existing annotator/document order;
2. submit independent document calculations;
3. update progress as futures finish;
4. collect results by sequence number; and
5. merge findings and render reports in the original order.

This preserves stable artifacts even when workers complete out of order. Run inclusion and exclusion passes separately so their current ordering is retained. Initially parallelize only the measured bottleneck rather than changing CAS extraction, HDF5 loading, and both policy passes at once.

### Thread-safety and architecture constraints

Do not share an open `h5py.File` or `zipfile.ZipFile` between worker threads. Load required policy arrays in the coordinator and treat them as read-only. Keep CAS/ZIP extraction serial in the first increment; concurrent access to ZIP readers, type systems, and CASSIS objects needs separate evidence and design.

Progress-file writes must remain coordinator-owned. Existing source-stamp, page-revision, stale-result, and page-close guards must continue to govern publication of the final result. Exceptions should be reduced to fixed or sanitized user-facing messages without clinical content.

NumPy operations may release the GIL, so threads can improve some workloads, but membership checks may instead be memory-bandwidth-bound. If profiling shows Python/CASSIS parsing dominates, evaluate process-based parallelism separately. On Windows, process startup, pickling, array copying, and type-system reconstruction may outweigh the benefit; use document chunks or shared/read-only data only after measurement.

### Validation requirements

Serial and parallel modes must produce equivalent results for:

- exact findings, fields, and ordering;
- actionable and ignored counts;
- inclusion-list and exclusion-list passes;
- multiple documents and annotators;
- ZIP and SQLite annotation sources;
- malformed or skipped documents;
- monotonic progress updates;
- repeated-run determinism; and
- source changes, cancellation, stale workers, and closed pages.

Benchmark realistic datasets for wall-clock time, peak memory, and scaling at one, two, and four workers. Add a GUI worker-count control only after evidence shows a useful trade-off. GUI-specific defaults must not silently change CLI or API defaults.
