---
type: Data Format
title: JSON artifact formats for findings, suggestions, and reviewed decisions
description: Exact JSON payload shapes used between critical finding detection, sanitization suggestion generation, GUI review, and write-back.
resource: /src/snomed_post_processing
status: stable
tags: [data-format, json, critical-findings, suggestions, decisions, sanitization]
generated: { by: pi-coding-agent/gpt-5.5, at: 2026-09-10T00:00:00Z }
sources:
  - id: critical-findings-json
    resource: /src/snomed_post_processing/findings_io/json_io.py
    title: Critical findings JSON IO
  - id: critical-findings-mapping
    resource: /src/snomed_post_processing/findings_io/mapping.py
    title: CriticalFinding JSON mapping
  - id: suggestions-json
    resource: /src/snomed_post_processing/sanitization/json_io.py
    title: Sanitization suggestions JSON IO
  - id: suggestion-models
    resource: /src/snomed_post_processing/sanitization/models.py
    title: Structured suggestion models and statuses
  - id: semantic-models
    resource: /src/snomed_post_processing/sanitization/semantic_models.py
    title: Semantic BM25 suggestion models
  - id: decisions-json
    resource: /src/snomed_post_processing/sanitization/decisions_json.py
    title: Reviewed sanitization decisions JSON IO
  - id: review-ui
    resource: /src/snomed_post_processing/gui/sanitization_run_tab.py
    title: GUI decision construction
---

# Purpose

Three JSON artifacts connect the sanitization workflow:

1. **Critical findings JSON** records annotation occurrences that violate a policy/release check.
2. **Sanitization suggestions JSON** records replacement evidence generated for those findings.
3. **Reviewed decisions JSON** records human-reviewed actions to apply during write-back.

All three payloads are top-level JSON objects with this shared envelope:

```json
{
  "schema": "...",
  "schema_version": 1,
  "created_at": "ISO-8601 timestamp",
  "metadata": {},
  "...": []
}
```

# Critical findings JSON

Schema:

```text
snomed-post-processing.critical-findings
```

Top-level list field:

```text
findings
```

Each finding has:

| Field | Meaning |
|---|---|
| `annotator` | INCEpTION annotator/user or view name. |
| `document` | Source document name. |
| `code` | Normalized SCTID, or `null` when absent. |
| `covered_text` | Text covered by the annotation span. |
| `offset` | Two-element `[begin, end]` character offset. |
| `list_type` | Policy side that produced the finding, e.g. whitelist/blacklist. |
| `reason` | Human-readable reason for flagging. |
| `layer` | Annotation layer, or `null`. |
| `fsn` | Source concept FSN, or `null`. |
| `ignored` | Whether the finding was suppressed by ignore-overlap logic. |
| `ignore_overlaps` | Matching ignore-overlap annotations. |

Each `ignore_overlaps[]` entry has:

```text
layer, offset, text
```

Ignored findings are informational and should not be sanitized automatically.

# Sanitization suggestions JSON

Schema:

```text
snomed-post-processing.sanitization-suggestions
```

Top-level list field:

```text
suggestions
```

Each suggestion has:

| Field | Meaning |
|---|---|
| `type` | Suggestion family: `structured` or `semantic_bm25`. |
| `finding` | Embedded critical finding object. |
| `status` | Sanitization outcome/status value. |
| `replacement_code` | Chosen single replacement SCTID, if one is proposed. |
| `replacement_fsn` | FSN of the proposed replacement, if any. |
| `association_type` | Evidence/relation label, e.g. `REPLACED_BY`, `SAME_AS`, ancestor label, or `BM25`. |
| `reason` | Human-readable explanation. |
| `candidate_count` | Count of candidate concepts considered/reported. |
| `candidates` | Replacement candidate records. |
| `context_candidates` | For BM25 suggestions, optional structured candidates shown as context; otherwise empty. |
| `score` | Only for `semantic_bm25` suggestions: BM25 score for the selected candidate. |

Current suggestion `type` values:

| Type | Meaning |
|---|---|
| `structured` | Evidence comes from structured SNOMED/policy data, such as historical associations or ancestor fallback. |
| `semantic_bm25` | Evidence comes from optional lexical BM25 fallback over SNOMED/SNOGIT terms. |

Current status values:

```text
historical_association_replacement
semantic_bm25_replacement
nearest_target_ancestor
nearest_historical_ancestor
ambiguous_replacement
ambiguous_ancestor
no_policy_acceptable_candidate
no_historical_association
blacklisted_no_auto_sanitization
no_replacement
```

## Structured candidate records

A structured candidate has:

| Field | Meaning |
|---|---|
| `type` | Always `structured`. |
| `code` | Candidate SCTID. |
| `fsn` | Candidate FSN, or `null`. |
| `association_type` | SNOMED association type or ancestor fallback label. |
| `active` | Whether candidate is active. |
| `in_whitelist` | Whether candidate is in the whitelist policy view. |
| `in_blacklist` | Whether candidate is in the blacklist policy view. |
| `effective_time` | Association or fallback effective time, if known. |
| `refset_id` | Reference set ID for association evidence, if known. |

Common SNOMED historical association labels include:

```text
SAME_AS
REPLACED_BY
POSSIBLY_EQUIVALENT_TO
WAS_A
MOVED_TO
MOVED_FROM
ALTERNATIVE
PARTIALLY_EQUIVALENT_TO
POSSIBLY_REPLACED_BY
REFERS_TO
SIMILAR_TO
```

## Semantic BM25 candidate records

A BM25 candidate has:

| Field | Meaning |
|---|---|
| `type` | Always `semantic_bm25`. |
| `code` | Candidate SCTID. |
| `fsn` | Candidate FSN. |
| `score` | Overall BM25/ranking score. |
| `lexical_score` | Lexical score component. |
| `semantic_tag` | Candidate semantic tag, or `null`. |
| `active` | Whether candidate is active. |
| `in_whitelist` | Whether candidate is in the whitelist policy view. |
| `in_blacklist` | Whether candidate is in the blacklist policy view. |
| `source` | Candidate term source, e.g. `snomed_fsn` or SNOGIT-derived source. |
| `matched_term` | Term matched by BM25, if recorded. |
| `source_member` | Source member/provenance for the matched term, if recorded. |

BM25 candidates remain suggestion-only fallback evidence and cannot bypass selected target-view validity gates.

# Reviewed sanitization decisions JSON

Schema:

```text
snomed-post-processing.sanitization-decisions
```

Top-level list field:

```text
decisions
```

Each decision is a JSON object produced by the review UI or compatible tooling. Current GUI-produced fields are:

| Field | Meaning |
|---|---|
| `suggestion_index` | Zero-based index into the loaded suggestions list. |
| `action` | Reviewed action: `replace`, `delete`, `manual_edit`, or `none`. |
| `apply` | Boolean replacement flag; legacy-compatible with `action=replace`. |
| `delete_annotation` | Boolean deletion flag; legacy-compatible with `action=delete`. |
| `manual_edit` | Boolean manual-review marker flag; legacy-compatible with `action=manual_edit`. |
| `annotator` | Annotator/view to match. |
| `document` | Document to match. |
| `source_code` | Original SCTID to match. |
| `covered_text` | Covered text to match/check when available. |
| `offset` | Two-element `[begin, end]` span offset. |
| `layer` | Annotation layer to match. |
| `replacement_choice` | Human-readable selected choice label. |
| `replacement_code` | Replacement SCTID, or `null`. |
| `replacement_fsn` | Replacement FSN, or `null`. |
| `suggestion_status` | Display/status label copied from the suggestion row. |
| `review_note` | Suggestion rationale or reviewer-facing note. |
| `valid_choice` | Whether `replacement_choice` is valid for the suggestion row. |

Action precedence during write-back is:

```text
manual_edit > delete > apply > keep unchanged
```

Replacement is applied only when the decision is actionable, has a valid choice, and includes a replacement code. Delete removes the matched annotation. Manual edit keeps the original annotation and writes a manual-review marker.

# Metadata

`metadata` is intentionally flexible and workflow-specific. Current GUI/pipeline metadata may include paths to source suggestion artifacts, manual-review layer name, document counts, reviewed document names, HDF5/source settings, target view, and blacklist settings.

# Compatibility notes

- Readers validate `schema` and `schema_version`.
- Boolean fields in decisions are retained for compatibility with older review/apply code.
- Do not infer acceptance from a suggestion alone; only reviewed decisions select actions.
- `type=structured` identifies the evidence family, not a guarantee that a replacement was accepted.
- `semantic_bm25` is lexical fallback evidence, not official SNOMED CT reasoning.

# Related concepts

- [JSON artifacts](json-artifacts.md)
- [Critical-finding logging](/snomed-post-processing/workflows/critical-finding-logging.md)
- [Sanitization suggestion generation](/snomed-post-processing/workflows/sanitization-suggestions.md)
- [Reviewed decisions and write-back](/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md)
