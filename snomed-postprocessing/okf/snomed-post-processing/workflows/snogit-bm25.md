---
type: Workflow
title: Processed SNOGIT cache and BM25 fallback
description: Optional lexical fallback evidence for sanitization suggestions using SNOMED FSNs and processed SNOGIT terms.
resource: /src/snomed_post_processing/sanitization/snogit_sidecar.py
tags: [workflow, snogit, bm25, sanitization, hdf5]
status: stable
generated: { by: pi-coding-agent/gpt-5, at: 2026-08-28T15:03:31Z }
sources:
  - id: snogit-doc
    resource: /snomed-post-processing/source-/snomed-post-processing/source-former documentation folder/snogit-bm25-candidates-design.md
    title: Processed SNOGIT cache and BM25 sanitization candidates
  - id: bm25-code
    resource: /src/snomed_post_processing/sanitization/semantic_bm25.py
    title: Semantic BM25 resolver
  - id: snogit-code
    resource: /src/snomed_post_processing/sanitization/snogit_sidecar.py
    title: SNOGIT sidecar/cache implementation
---

# Purpose

Semantic BM25 is an optional fallback for sanitization suggestions when historical associations and ancestor fallback do not produce a clear replacement. It ranks lexical similarity between annotation text/source FSN and candidate terms.

SNOGIT provides optional interface-term evidence but is never authoritative:

```text
SNOMED FSN BM25 + optional processed SNOGIT cache
        -> candidate evidence
        -> selected target-view gates
        -> review suggestion
```

# Terminology

Use the user-facing term **processed SNOGIT cache** for the reusable HDF5 built from a raw SNOGIT ZIP or a single raw SNOGIT `.dat` file. The implementation module is named `snogit_sidecar.py`.

`suggest-sanitization` consumes a processed cache only. It does not parse raw SNOGIT ZIPs/`.dat` files and does not create a cache.

# Cache creation

```bash
uv run build-snogit-cache \
  --hdf5 concepts.hdf5 \
  --snogit-source SNOGIT.zip \
  --output processed_snogit_cache.hdf5
```

`--snogit-source` accepts either a SNOGIT release ZIP or a single SNOGIT `.dat` file. `--snogit-zip` remains accepted as a backwards-compatible alias. Default member selection for ZIP inputs uses the newest general `SNOGIT_*.dat` member in the ZIP. Raw `.dat` inputs are used directly.

Override ZIP inputs with explicit members:

```bash
uv run build-snogit-cache \
  --hdf5 concepts.hdf5 \
  --snogit-source SNOGIT.zip \
  --output processed_snogit_cache.hdf5 \
  --snogit-member path/in/zip/SNOGIT_20240131.dat \
  --snogit-member path/in/zip/SNOGIT_ELGA_20240131.dat
```

Supported member classes:

| Class | Default? |
|---|---:|
| general `SNOGIT_*.dat` | newest selected by default |
| `SNOGIT_ELGA_*.dat` | explicit selection only |
| `SNOMED_latin_*.dat` | explicit selection only |

# Runtime use

```bash
uv run suggest-sanitization \
  --lists-path concepts.hdf5 \
  --critical-findings critical_findings.json \
  --output sanitization_suggestions.md \
  --semantic-bm25-fallback \
  --use-snogit-cache processed_snogit_cache.hdf5
```

Without `--use-snogit-cache`, semantic BM25 still ranks SNOMED FSNs from the main HDF5.

# FSN text matching and semantic-tag boost

BM25 indexes known FSNs without their trailing semantic-tag suffix, e.g. `Pain (left side) (finding)` becomes `Pain (left side)` for matching. The source-FSN portion of the query is cleaned the same way. Tag words therefore do not contribute to FSN BM25 retrieval, document lengths or lexical overlap. Full FSNs, matched-term display and semantic-tag metadata are preserved. Annotation covered text, clinical parentheses and SNOGIT interface terms retain their existing tokenization; processed SNOGIT caches do not need rebuilding for this FSN-only change.

Matching source/candidate FSN tags still produce a separate score multiplier: `1 + semantic_tag_boost_percent / 100`, default **10%** (`1.10`). GUI **Advanced suggestion settings → Matching semantic-tag boost (%)** and CLI `--bm25-semantic-tag-boost-percent` accept 0–100; **0 disables the boost**. It applies to matching-tag FSN-channel scores without changing lexical overlap; SNOGIT raw scores remain unboosted, as before. The existing engine `use_semantic_tag_boost=False` switch also disables it.

GUI suggestion JSON settings record `bm25_semantic_tag_boost_percent` and `bm25_fsn_semantic_tags_excluded=true`. Regenerate suggestions after this scoring change or editing the boost; reassess BM25 score and automatic-acceptance thresholds rather than comparing old and new scores directly. No HDF5/FSN rewrite is performed.

# Configurable FSN postfix exclusions

Both GUI frontends provide a row-based advanced editor: Exclude checkbox + literal Postfix, addable/removable custom rows, `action` selected by default, and unchecked presets `unit of product usage`, `dosing instruction fragment`, `dosing instruction imperative`. All-unchecked disables postfix stripping. Streamlit keeps changes within its explicit settings form; NiceGUI input changes invalidate generation without starting it. See the [user guide](../../../docs/user-guide.md#fsn-postfix-exclusions). These are classification-like candidates for lexical cleanup, not assertions that the suffixes carry no meaning. Clinically distinguishing suffixes such as `non-surgical`, `open`, `closed`, `normal` are not presets.

The read-only local HDF5 scan (`gemtex_snomedct_codes_release20260401_policy20240401.hdf5`, 509,891 concept rows) found respectively 324, 58, 35, 25 active matches for those four postfixes, all tagged qualifier value. Across all postfixes, 13,194 concepts (3,679 active) had a whitespace-surrounded ASCII hyphen after existing semantic-tag cleanup. These are local active-concept counts, not selected target-view candidate counts. Verified example FSNs/SCTIDs are in the user-guide table.

`semantic_text._fsn_text` removes the trailing semantic tag using current logic, splits at the last whitespace-surrounded ASCII hyphen, compares the entire postfix case-insensitively against selected literals, and strips only if the retained first part is nonempty. Unspaced/internal hyphens and unknown postfixes are preserved. `normalize_fsn_postfixes` validates literal strings and canonicalizes case/outer whitespace/duplicates. `SemanticBm25Resolver(excluded_fsn_postfixes=...)` applies the same cleanup to indexed FSNs, lexical overlap and source-FSN query text, leaving annotation text, SNOGIT, full display/evidence FSNs, SCTIDs, tags and tag boosting unchanged. GUI generation forwards the selection and records `settings.bm25_excluded_fsn_postfixes`. Stripping may collapse concept distinctions and alter scores/ranks: regenerate suggestions explicitly; no cache/HDF5 rewrite. Standalone resolver/API and CLI defaults remain empty; GUI `SuggestionSettings` and the Streamlit editor default to `action`. Synthetic backend, installed-SDK NiceGUI and Streamlit AppTest checks cover boundaries, disabled/custom settings, propagation/metadata and unchanged source evidence. Streamlit edited-row forwarding uses a mock because AppTest lacks a cell-edit API; actual browser editing was not verified.

# Candidate gates and safeguards

BM25/SNOGIT candidates use the selected target view:

| Target view | Gate |
|---|---|
| policy | active AND whitelisted AND not blacklisted |
| release | active, plus optional embedded/custom blacklist exclusions |

All modes reject the unchanged source concept and SNOMED CT root. SNOGIT evidence must not bypass HDF5 validity gates.

Runtime safeguards include:

```text
max_postings_per_token
max_candidate_rows
max_hits
bm25_min_score
bm25_min_lexical_score
bm25_max_candidates
```

Repeated normalized query texts are cached during one resolver run.

## Meaning of SNOGIT retrieval limits

User-facing reference: [user guide — SNOGIT retrieval limits](../../../docs/user-guide.md#snogit-retrieval-limits), linked from the main README addendum.

| Recorded warning | Stage and budget | Behaviour when exceeded |
|---|---|---|
| `SNOGIT postings limit` | Per query token, before scoring; `max_postings_per_token=250_000`. | Skip the entire token if its postings list contains more than 250,000 term rows. Do not truncate its postings list. |
| `SNOGIT candidate-row limit` | Union of accepted term-row IDs across tokens, before scoring; `max_candidate_rows=100_000`. | Skip the entire token if adding its rows would exceed 100,000 distinct rows. Process tokens from rarest to most common. |
| `SNOGIT hit limit` | Returned scored term rows; generation sets `max_hits=max(max_candidates * 20, 50)`. The standalone search default is 50. | Return the highest-scoring hits and boundary ties, subject to the tie safety cap; flag when scored hits remain omitted. |

A skipped token adds neither rows nor BM25 score contributions, even for rows already accepted through another token. Postings/candidate-row guards can therefore change ranking as well as coverage. Hit limiting happens after scoring. The first two budgets are internal search parameters, not GUI controls; changing the requested final candidate count changes the hit budget only.

Term rows/hits are not distinct SCTIDs or project annotations. Several SNOGIT term entries can map to one concept. Returned hits still undergo target/score gates and evidence merging by SCTID; the final candidate maximum is a separate tie-aware cutoff. For example, requesting five final candidates requests 100 SNOGIT term hits, not 100 distinct targets, and does not guarantee five eligible final candidates.

Boundary-hit tie expansion is bounded by `max(max_hits, 2_000)`. Cutting that group additionally records `SNOGIT tied-hit limit (N)` with the actual cap; it can coexist with the ordinary hit-limit warning. Comparisons use full-precision scores, not rounded display values.

A warning indicates incomplete evidence, not necessarily an incorrect displayed candidate. Automatic BM25 acceptance is blocked by any recorded retrieval limit; manual review remains possible. Saved artifacts cannot recover omitted hits, and regeneration with unchanged inputs/budgets may repeat the warning. Increasing the final candidate count cannot repair postings/candidate-row omissions; increasing internal budgets costs memory/runtime and does not establish clinical confidence. SNOGIT guards affect its evidence channel, not the separate SNOMED FSN search.

# Cutoff ties and retrieval coverage

The requested candidate maximum is a **soft cutoff**: keep the entire score-tie group at its boundary, after policy/release filtering and target-code deduplication. Ties use full-precision `math.isclose` semantics (`rel_tol=1e-9`, `abs_tol=1e-9`), not rounded displayed scores. A first-place tie remains ambiguous even when the requested maximum is one; there is no preferred replacement code.

SNOGIT hit retrieval also retains boundary ties before merging evidence. Existing postings/candidate-row guards remain. Safety caps bound expanded groups to 2,000 SNOGIT term hits and 2,000 final candidates (or the explicitly requested count if larger). Reached postings, candidate-row, hit or tie caps are recorded in `SemanticBm25Suggestion.retrieval_limits`, preserved in suggestion JSON, and shown in the overview, review and Markdown report. Counts then describe saved/retrieved candidates, not complete totals. Cached queries retain their own coverage flags.

In Review & apply, large first-place ties (more than five distinct targets) have a collapsed searchable candidate browser before the document's manual-choice form. The scrolling, single-row-selectable table shows SCTID, full FSN and high-precision scores. Search matches SCTID/FSN; selection is stored as SCTID, mapped against the rendered snapshot, not a later filtered row index. **Use selected candidate** stages it in the compact dropdown; the existing **Save choices** action commits it. Small tied sets retain the dropdown but begin with no replacement selected. Browser search/selection runs in a fragment outside the form, avoiding unrelated reruns; Use refreshes the form. No CAS files change here.

A warning distinguishes complete saved tie groups from partial retrieval. Any recorded retrieval limit prevents automatic BM25 acceptance, while manual choices remain available. Exclusion-list source findings remain manual regardless. Regenerate suggestions to use tie-aware retention; old files cannot reveal candidates that were never saved. No new HDF5 schema or cache rebuild is required.

# Optional automatic review acceptance

Tab 3's **Automatic conditions** form has an opt-in BM25 heuristic (off initially). It only selects inclusion-list source findings, never exclusion-list findings. Scores must come from a single known source/channel and the same index member. Mixed FSN/SNOGIT candidates are not compared, and a SNOGIT channel without a known member remains manual. Deduplication is by target code, retaining its best score, after validating the full saved candidate set.

For at least three distinct targets sorted by score, `first_gap = s1 - s2` and `largest_later_gap = max(s2-s3, ..., s[n-1]-sn)`. Both `D = first_gap / (first_gap + largest_later_gap) >= 2/3` and `M = first_gap / s1 >= 0.20` must pass (configurable). With three targets this reduces to the original three-score formula. Tied first place, missing/non-finite/negative scores, or fewer than three distinct targets remain manual. Equal runner-up scores alone do not imply a tied first place.

The calculation uses all candidates saved in the suggestion, so retrieval limits affect the result. It uses saved ranking scores, including any configured semantic-tag boost; keep retrieval, query and scoring settings consistent during calibration. Existing generation score/lexical/target-view gates still apply. Thresholds are unvalidated heuristics, not probabilities or clinical confidence. Metrics are visible in the assessment table and saved with automatic decision provenance. Historical OR BM25 selection shares the same manual-choice protection and session-only Undo; CAS changes still require explicit export/upload. See [review/write-back](/snomed-post-processing/workflows/reviewed-decisions-and-writeback.md).

# Processed cache compatibility

The cache stores a fingerprint of the main HDF5 so stale or mismatching caches can be rejected. Compatibility metadata includes release date, policy/view date, RF2 view, concept count, policy candidate count, concept-code hash, and policy-candidate hash.

# HDF5 cache layout

```text
/metadata/...
/terms/concept_index
/terms/term
/terms/source_member
/terms/length
/index/vocab
/index/postings_start
/index/postings_length
/index/postings_doc
/index/postings_tf
/index/idf
/index/avg_doc_len
```

# Output evidence

Suggestion candidates may include:

```text
source = snomed_fsn | snogit
matched_term
source_member
matched_query_tokens
```

These fields explain why a candidate was suggested; they do not change acceptance rules.

# Known follow-up

Short/generic one-token annotations may produce noisy matches. If real data confirms this, consider stricter lexical overlap, minimum token counts, semantic-tag compatibility, or stronger score margins.
