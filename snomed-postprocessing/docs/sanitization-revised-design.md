# Revised SNOMED Sanitization Design: Finding-Based Replacement

## 1. Goal

Add an optional sanitization mode that suggests replacements only for SNOMED CT annotation codes that have already been flagged as faulty by the current whitelist/blacklist checks.

The current checking workflow remains authoritative and is now explicitly separated from sanitization:

```text
INCEpTION export
    ↓
load annotations
    ↓
run whitelist/blacklist checks
    ↓
produce reports + CriticalFindings JSON

CriticalFindings JSON + sanitization-ready HDF5
    ↓
produce separate sanitization suggestion report
```

Sanitization must not pre-process, normalize, or replace all codes before checking. Codes that pass the current checks are not touched.

## 2. Revised Core Principle

Previous source/target-oriented thinking assumed:

```text
source relationships + target policy = dynamic mapping
```

The revised implementation should primarily use:

```text
target release policy + target release history = post-hoc replacement suggestions
```

A single enriched HDF5 file for a specific target release can contain:

- the current whitelist;
- the current blacklist;
- active concept metadata for the target release;
- historical association data for inactive/deprecated concepts;
- optionally hierarchy/ancestor data for fallback generalization.

This avoids requiring a separate `source.hdf5` in the common case.

## 3. Runtime Workflow

### 3.1 Current checks

First run the existing logic exactly as today:

```text
observed code in whitelist     -> OK
observed code not in whitelist -> critical whitelist finding
observed code in blacklist     -> critical blacklist finding
```

The output of this phase should be structured as critical findings.

Example conceptual object:

```python
CriticalFinding(
    annotator="...",
    document="...",
    code="123456",
    covered_text="...",
    offset=(10, 20),
    list_type="whitelist",  # or "blacklist"
    reason="not_in_whitelist",
)
```

The checking command writes a versioned `critical_findings_*.json` artifact next to the normal reports under the processing/output directory. Sanitization is not run by the checking command.

### 3.2 Sanitization phase

Only critical findings loaded from the `CriticalFindings` JSON artifact are passed to the sanitization module.

```text
critical finding
    ↓
if sanitization enabled:
    try to find acceptable replacement
    ↓
attach suggestion to finding/report
```

Valid/non-critical codes are never passed to sanitization.

## 4. Role of SNOMED RF2 Full Releases

SNOMED RF2 Full releases are upstream preprocessing inputs, not the preferred runtime artifact.

They are used during HDF5 dump generation to derive target-release data such as:

- concept active/inactive state at the target release date from `sct2_Concept_*`;
- descriptions/FSNs at the target release date from `sct2_Description_*`;
- historical associations for inactive concepts from `der2_cRefset_Association*`;
- optionally hierarchy/ancestor data from active `is-a` rows in `sct2_Relationship_*`.

In the inspected International Edition package (`data/international.zip`, effective time `20260401`) these required files are present in both `Full` and `Snapshot` views. The package contains English (`-en`) descriptions/language refsets; other languages require matching extension packages.

At runtime, the application should usually read the enriched HDF5 file, not raw RF2 ZIPs.

Conceptual preprocessing:

```text
SNOMED RF2 Full release ZIP
    ↓ reconstruct target release state by latest row per component/member id at or before target date
    ↓ filter active rows after reconstruction
    ↓ extract historical associations
    ↓ create enriched target-release HDF5
```

For a Snapshot view, reconstruction is not needed, but inactive rows may still be present and should be filtered when active-only data is required.

Runtime:

```text
target-release.hdf5 + INCEpTION export
    ↓
critical findings
    ↓
sanitation suggestions
```

## 5. Enriched HDF5 Structure

The preferred compact HDF5 layout stores canonical concept metadata once and represents policies as views into that concept table:

```text
/concepts/codes
/concepts/fsn
/concepts/semantic_tag_id
/concepts/semantic_tags
/concepts/active
/policy_views/whitelist/0/concept_index
/policy_views/blacklist/0/concept_index
```

This minimizes repeated string datasets. The existing runtime-compatible policy structure can still be exported optionally during a transition period:

```text
/whitelist/0/codes
/whitelist/0/fsn
/blacklist/0/codes
/blacklist/0/fsn
```

Historical associations should be represented compactly. In RF2 these rows come from association refset files with columns like:

```text
id effectiveTime active moduleId refsetId referencedComponentId targetComponentId
```

The preferred compact HDF5 representation references `/concepts` by integer index:

```text
/historical_associations/source_index
/historical_associations/target_index
/historical_associations/association_type_id
/historical_associations/association_types
/historical_associations/effective_time
/historical_associations/active
/historical_associations/refset_id
```

Where:

- `source_code` is the inactive/deprecated observed concept;
- `target_code` is the associated replacement/related concept;
- `association_type` records the SNOMED association type, e.g. `SAME_AS`, `REPLACED_BY`, `POSSIBLY_EQUIVALENT_TO`;
- `effective_time` is the RF2 effective time of the association row;
- `active` indicates whether the association row is active in the reconstructed target release state.

Optional hierarchy fallback data may use the previous compact ancestor representation:

```text
/concepts/ancestors_index
/concepts/ancestor_concept_index
/concepts/ancestor_distance
```

This is not required for the first historical-association-based implementation.

## 6. Replacement Policy

Replacement must be policy-driven and conservative.

### 6.1 Whitelist findings

For a whitelist finding:

```text
original code is not in target whitelist
```

Sanitization may try historical associations.

Recommended order:

1. `SAME_AS`
2. `REPLACED_BY`
3. optionally `POSSIBLY_EQUIVALENT_TO`
4. optionally ancestor fallback

A candidate replacement is acceptable only if:

```text
candidate is active
candidate in target whitelist
and candidate not in target blacklist
```

If no candidate satisfies the target policy, no replacement is suggested.

### 6.2 Blacklist findings

For blacklist findings:

```text
original code is in target blacklist
```

Do not automatically sanitize by default.

Blacklist violations usually encode intentional policy decisions. Replacing a blacklisted concept with a broader ancestor may hide an intentionally forbidden annotation.

Historical associations are primarily useful for whitelist findings, because retired/inactive concepts are normally absent from the active whitelist and are therefore flagged as `not_in_whitelist`, not as `blacklisted`. Blacklisted concepts in the RF2-derived policy views are usually active but policy-forbidden, so historical `SAME_AS`/`REPLACED_BY` associations are not expected to be the main replacement mechanism for them.

Initial behavior remains:

```text
status = blacklisted_no_auto_sanitization
replacement = None
```

An explicit option can enable suggestion-only blacklist sanitization via semantic BM25 fallback. This does not use historical associations as the primary mechanism and does not mutate source documents. Candidates must still satisfy the target policy:

```text
candidate active
candidate in whitelist
candidate not in blacklist
```

## 7. Sanitization Algorithm

For each `CriticalFinding`:

1. If finding has no real code, skip:

```text
status = no_replacement
replacement = None
```

2. If finding is a blacklist finding and blacklist sanitization is not enabled:

```text
status = blacklisted_no_auto_sanitization
replacement = None
```

If blacklist sanitization is enabled, skip historical-association lookup as the main path and use the BM25 fallback rules below.

3. If finding is a whitelist finding:

```text
look up active historical associations where source_code == finding.code
```

4. Filter associations according to allowed association types.

Default allowed association types:

```text
SAME_AS
REPLACED_BY
```

5. Filter candidate targets by target policy:

```text
candidate active
candidate in whitelist
candidate not in blacklist
```

6. If exactly one acceptable candidate remains:

```text
status = historical_association_replacement
replacement = candidate
```

7. If multiple acceptable candidates remain:

```text
status = ambiguous_replacement
replacement = None
candidates = [...]
```

or apply an explicit deterministic tie-breaker if configured.

8. If no acceptable historical candidate exists and semantic BM25 fallback is enabled, or if this is a blacklist finding with explicit blacklist suggestions enabled:

```text
rank active whitelist concepts that are not blacklisted by lexical BM25 similarity
return only candidates above strict score/overlap thresholds
```

BM25 fallback is suggestion-only and intended for manual review. It must not auto-apply replacements.

9. If no acceptable historical/BM25 candidate exists and ancestor fallback is enabled:

```text
find nearest ancestor in target whitelist and not in target blacklist
```

10. If no replacement exists:

```text
status = no_replacement
replacement = None
```

## 8. Status Values

Suggested statuses:

| Status | Meaning |
|---|---|
| `not_sanitized_not_critical` | Code was not critical and was not passed to sanitization. Usually not emitted. |
| `empty_or_missing_code` | Finding has no usable SNOMED code. |
| `blacklisted_no_auto_sanitization` | Blacklist finding; auto-sanitization disabled. |
| `historical_association_replacement` | Replacement found via allowed historical association. |
| `semantic_bm25_replacement` | Suggestion-only replacement found via policy-aware BM25 lexical similarity. |
| `ambiguous_replacement` | Multiple acceptable replacement candidates. |
| `no_policy_acceptable_candidate` | Historical candidates exist but none satisfy whitelist/blacklist policy. |
| `no_historical_association` | No association known for the faulty code. |
| `nearest_target_ancestor` | Optional fallback: mapped to nearest acceptable ancestor. |
| `ambiguous_ancestor` | Optional fallback found multiple equally near ancestors. |
| `no_replacement` | No usable replacement was found. |

## 9. Reporting

Sanitization suggestions are written to a separate Markdown report, not embedded into the existing critical-findings report. This keeps the reporting/checking output stable and makes replacement review an explicit second artifact.

Standalone Markdown columns:

| Original Code | Covered Text | Offset | Failure Type | Sanitization Status | Replacement Code | Replacement FSN |
|---|---|---:|---|---|---|---|
| `123` | example | `(10, 20)` | `not_in_whitelist` | `historical_association_replacement` | `456` | `Example concept (disorder)` |
| `789` | example | `(30, 40)` | `not_in_whitelist` | `no_replacement` |  |  |
| `999` | example | `(50, 60)` | `blacklisted` | `blacklisted_no_auto_sanitization` |  |  |

A future dedicated JSON sanitization report may preserve structured original and replacement information:

```json
{
  "original_code": "123",
  "covered_text": "example",
  "offset": [10, 20],
  "failure_type": "not_in_whitelist",
  "sanitization": {
    "status": "historical_association_replacement",
    "replacement_code": "456",
    "replacement_fsn": "Example concept (disorder)",
    "association_type": "REPLACED_BY",
    "candidates": []
  }
}
```

## 10. CLI Shape

Sanitization suggestions are a separate second command that consumes the `CriticalFindings` JSON artifact from the checking command.

Checking example:

```bash
uv run log-critical-documents \
  --lists-path target-release.hdf5 \
  /path/to/inception-export.zip
```

This writes the normal reports plus `critical_findings_*.json` next to them.

Sanitization example:

```bash
uv run suggest-sanitization \
  --lists-path target-release.hdf5 \
  --critical-findings /path/to/critical_findings_*.json \
  --output /path/to/sanitization_suggestions.md
```

Policy flags:

```bash
--association-type SAME_AS \
--association-type REPLACED_BY \
--activate-historical-ancestor-fallback \
--ancestor-max-distance 3 \
--semantic-bm25-fallback \
--blacklist-suggestions \
--bm25-min-score 1.5 \
--bm25-min-lexical-score 0.15 \
--bm25-max-candidates 5
```

The implementation keeps the default conservative:

```text
sanitize whitelist findings only
allow SAME_AS and REPLACED_BY
reject ambiguous replacements
no blacklist sanitization unless explicitly enabled
no BM25 fallback unless explicitly enabled
no ancestor fallback unless explicitly enabled
```

## 11. Relationship to Previous Source/Target Design

The previous source/target design is still useful for an advanced fallback scenario:

```text
observed code does not exist in target data
and has no useful historical association
but exists in an older source release
and should be generalized through the older source hierarchy
```

That requires:

```text
source relationships + target policy
```

However, this should be considered optional and secondary.

The revised primary implementation should use one enriched target-release HDF5:

```text
target whitelist/blacklist
+ target release historical associations
+ optional target hierarchy
```

This better matches the desired workflow: only codes already flagged by the current checks are candidates for replacement.

## 12. Implementation Phases

### Phase 1: Structured findings

Implemented. The analysis path now materializes whitelist/blacklist findings as structured `CriticalFinding` records first, and Markdown/JSON reporting is rendered from those records at the end of the run. This makes `CriticalFinding` the default bridge between policy checking and future sanitization.

A new module `snomed_post_processing.sanitization` implements the first conservative, suggestion-only resolver. It consumes `CriticalFinding` records and the compact HDF5 layout and returns `SanitizationSuggestion` objects without mutating documents.

### Phase 2: Historical association storage

Implemented. HDF5 dump generation can include compact historical associations derived from RF2 association refsets.

### Phase 3: Sanitization resolver

Implemented. The resolver consumes:

```text
CriticalFinding + enriched target HDF5
```

and returns structured `SanitizationSuggestion` results.

### Phase 4: Separate report integration

Implemented. CLI and Streamlit can generate a separate Markdown sanitization suggestion report. The existing critical-findings Markdown/masked Markdown/JSON outputs remain unchanged.

### Phase 5: Optional advanced fallback

Implemented for suggestion reporting. A dependency-free semantic BM25 module (`snomed_post_processing.sanitization.semantic_bm25`) can rank active, whitelisted, non-blacklisted concepts from the compact HDF5 layout as suggestion-only fallback candidates. CLI and Streamlit expose this as an opt-in fallback; accepted BM25 replacements are written to the existing standalone sanitization suggestion report with status `semantic_bm25_replacement`. Blacklist findings can be included explicitly via `--blacklist-suggestions` / the Streamlit checkbox, but remain disabled by default.

Ancestor fallback is also implemented as an opt-in resolver step for whitelist findings. With `--activate-historical-ancestor-fallback`, the resolver tries active ancestor arrays first and then compact stored inactive `is-a` edges under `/historical_is_a`. Historical fallback candidates are either the inactive edge's active parent or an active ancestor above that parent. Candidate ancestors must still be active, whitelisted, and not blacklisted; the default maximum distance is controlled by `--ancestor-max-distance 3`.

## 13. Summary

The revised design is finding-based and conservative:

```text
current checks first
faulty findings only
historical association replacement only if target-policy acceptable
blacklist sanitization disabled by default
```

RF2 Full releases are used upstream to build enriched target-release HDF5 files. Runtime analysis should remain fast and should not need raw SNOMED release ZIPs.
