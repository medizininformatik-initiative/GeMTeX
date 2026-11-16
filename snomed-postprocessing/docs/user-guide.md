# User guide: interpreting results and warnings

This companion to the [README](../README.md) collects detailed explanations without
expanding the main setup and workflow instructions.

## Contents

- [SNOGIT retrieval limits](#snogit-retrieval-limits)
  - [What the three limits mean](#what-the-three-limits-mean)
  - [Term rows, hits and final candidates](#term-rows-hits-and-final-candidates)
  - [What to do when a limit is reported](#what-to-do-when-a-limit-is-reported)

## SNOGIT retrieval limits

SNOGIT supplies additional lexical evidence for BM25 suggestions. These search
limits bound processing time and memory; they are **not clinical confidence
thresholds** and do not relax inclusion/exclusion-list or active-target checks.

The search has several stages:

```text
Query tokens
  → collect matching SNOGIT term rows (postings and candidate-row limits)
  → score the accepted rows with BM25
  → retain top term hits (hit limit, with boundary ties)
  → apply target/score gates and merge evidence by SCTID
  → retain final suggestion candidates (a separate, tie-aware limit)
```

### What the three limits mean

| Warning | What is limited | Current default and behaviour |
|---|---|---|
| **SNOGIT postings limit** | Matches for one query token. A posting identifies an indexed term row containing that token. | If the token occurs in more than **250,000 term rows**, skip the entire token, rather than taking its first 250,000 matches. |
| **SNOGIT candidate-row limit** | The combined pool of distinct term rows accepted across query tokens. | If adding a token would expand that pool beyond **100,000 rows**, skip that entire token. Tokens are processed from rarest to most common, so more selective tokens are considered first. |
| **SNOGIT hit limit** | The scored term matches returned from SNOGIT, before final target filtering and SCTID deduplication. | Suggestion generation requests **`max(20 × requested candidate count, 50)` hits**. Lower-scoring hits are omitted; score ties at the boundary are retained subject to a safety cap. |

The first two limits apply **before scoring**. A skipped token contributes neither
new matching rows nor score contributions to rows already accepted through other
tokens. Consequently, these limits can affect both coverage and ranking. The hit
limit applies **after scoring** and trims the returned results.

The postings and candidate-row defaults are internal search safeguards, not
separate GUI controls. The requested final candidate count influences the hit
budget, but does not change either of those two safeguards. The low-level SNOGIT
search function itself defaults to 50 hits; the generation pipeline supplies the
larger budget shown above.

Boundary ties use full-precision scores, not rounded display values. Tie expansion
is capped at **`max(requested SNOGIT hit budget, 2,000)` term hits**. If that cap
cuts a tie group, an additional **SNOGIT tied-hit limit (N)** warning records the
actual cap. A hit-limit warning may appear alongside it.

### Term rows, hits and final candidates

These counts are different:

- A **term row** is an indexed SNOGIT term entry, not a project annotation or a
  unique SNOMED CT concept. Multiple terms can refer to the same SCTID.
- A **hit** is a term row returned with a BM25 score.
- A **final candidate** is a distinct target SCTID remaining after target/score
  checks and evidence merging. SNOMED FSN evidence may also contribute.

For example, requesting **5 final candidates** gives SNOGIT a budget of **100 term
hits**, potentially more when boundary ties are retained. Several hits may share
an SCTID, and some may fail target or score checks, so this does not guarantee
five final candidates. The final candidate limit separately retains cutoff ties,
subject to its own safety cap.

### What to do when a limit is reported

A warning means **retrieval was incomplete**, not necessarily that a displayed
candidate is wrong. Saved counts describe the retrieved/saved evidence, not the
complete number of possible matches.

- Review the available candidates and their evidence manually; do not interpret
  the first displayed match as a guaranteed best match over the complete index.
- Any recorded retrieval limit blocks the automatic BM25-acceptance heuristic.
  Manual choices remain available. This does not introduce automatic acceptance
  into frontends where that workflow is not connected.
- Loading a saved artifact cannot recover omitted matches. Regenerating with the
  same inputs and limits may produce the same warning; more complete retrieval
  requires investigating the limiting search stage first.
- Changing the requested candidate count can increase the hit budget, but does
  not fix postings/candidate-row omissions. Increasing internal safeguards can
  increase memory use and runtime and is not a confidence improvement.

These SNOGIT limits concern its evidence channel, not the separate SNOMED FSN
search. A limit on either channel still means the combined evidence is incomplete.

Implementation references: [SNOGIT search](../src/snomed_post_processing/sanitization/snogit_sidecar.py)
and [BM25 generation/merging](../src/snomed_post_processing/sanitization/semantic_bm25.py).
