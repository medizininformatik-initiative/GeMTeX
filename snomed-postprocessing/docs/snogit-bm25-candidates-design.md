# Optional SNOGIT terms for BM25 sanitization candidates

## Motivation

The current semantic BM25 fallback indexes policy-acceptable SNOMED concepts using the
concept FSN stored in the selected HDF5. This is conservative, but German annotation
spans often match interface terminology better than formal FSNs.

SNOGIT should be optional and suggestion-only. It must never make policy checks less
strict; it only adds additional lexical evidence/candidates to the existing BM25 fallback.

## Consulted legacy and release material

Legacy code inspected from git history:

- `legacy/bm25_matching.py` at commit `baa929144a39fbcd9f414627287e2264dbd3fd38`

Relevant legacy design points:

- `SnogitTerm(concept_id, german_term, term_id, english_term)`
- headerless tab-separated SNOGIT input support
- default columns: `concept_id`, `term_id`, `english_term`, `german_term`
- BM25 index over normalized German SNOGIT terms
- SNOGIT hits are grouped by `concept_id` and resolved back to SNOMED concept metadata
- output records preserve source-specific scores/ranks and matched terms

Important legacy limitation:

- The legacy script loaded all SNOGIT rows into Python lists and built a full in-memory
  Python BM25 index over all SNOGIT terms.
- That is not safe for the current Streamlit/runtime workflow with ~10M+ filtered SNOGIT
  terms, because it creates millions of Python token lists, `Counter` objects, and postings.

Actual local SNOGIT archive inspected:

- `data/SNOGIT-release.zip`

Observed files:

| File | Observed format | Notes |
| --- | --- | --- |
| `release/SNOGIT_ELGA_20260220.dat` | 4 tab-separated columns | `concept_id`, `term_id`, English FSN, German term |
| `release/SNOGIT_ELGA_20260611.dat` | 4 tab-separated columns | same as above; ELGA release notes describe this format |
| `release/SNOGIT_20260712.dat` | 4 tab-separated columns | same as above |
| `release/SNOMED_LATIN_FULL_20260713.dat` | 3 tab-separated columns | `concept_id`, English FSN, Latin/German-ish term; some blank rows |

Release notes state SNOGIT fields are:

1. SNOMED CT Concept ID
2. Internal term ID, with creation-date suffix
3. English Fully Specified Name
4. German term

SNOMED Latin release notes state fields are:

1. SNOMED CT Concept ID
2. English Fully Specified Name
3. German term / Latin term

Empirical concept coverage comparison showed that `SNOGIT_ELGA_*.dat` and general
`SNOGIT_*.dat` overlap heavily but are not strict subsets of one another. Therefore the
cache must record exact selected ZIP member(s), not only a coarse source kind.

## Terminology

Use user-facing term:

```text
processed SNOGIT cache
```

Avoid user-facing term `sidecar` where possible. Internally, existing names may still use
`sidecar` until a broader rename is worthwhile.

## Workflow decision

Do not require SNOGIT during every HDF5 creation. Do not embed full SNOGIT terms into the
main SNOMED/policy HDF5.

Use an optional HDF5 processed SNOGIT cache:

1. Build the processed SNOGIT cache as its own explicit preprocessing step from:
   - a selected main SNOMED/policy HDF5 file, and
   - a raw `SNOGIT-release.zip` or selected SNOGIT `.dat` member(s).
2. During sanitization suggestion generation, use only a prebuilt compatible processed
   SNOGIT cache.
3. Do not silently build a large SNOGIT cache as part of the CLI suggestion command.
4. In the GUI, creating a cache from ZIP is allowed as a convenience, but it is still a
   separate phase: after cache creation, the user can download/select the cache and then
   explicitly start suggestion generation with that cache.

This keeps SNOGIT optional, avoids coupling every main HDF5 iteration to a large SNOGIT
preprocessing step, and prevents a user from accidentally starting a long SNOGIT build
inside an otherwise normal sanitization suggestion run.

## Source member defaults

Default source selection:

```text
newest general release/SNOGIT_*.dat member
```

For the current archive this is:

```text
release/SNOGIT_20260712.dat
```

Default excludes:

```text
SNOGIT_ELGA_*.dat
SNOMED_LATIN_*.dat
```

Advanced override should be a multiselect of ZIP `.dat` members. If multiple members are
selected, combine them and deduplicate by `(concept_index, normalized_term)`.

## Processed SNOGIT cache HDF5 layout

### Schema and compatibility metadata

The cache stores `concept_index`, so it must be tied to the exact main HDF5 concept array
and policy candidate view it was built against.

```text
/schema attrs:
  name = snomed-post-processing.snogit-cache
  version = 2

/metadata attrs:
  created_at
  main_hdf5_file_name
  main_hdf5_release_date
  main_hdf5_policy_date
  main_hdf5_rf2_view
  main_hdf5_concept_count
  main_hdf5_policy_candidate_count
  main_hdf5_concept_codes_hash
  main_hdf5_policy_candidate_hash
  snogit_zip_file_name
  source_selection
  rows_read
  rows_kept
  rows_written
  rows_skipped_unknown_concept
  rows_skipped_policy
  rows_skipped_empty_term
  duplicate_rows

/metadata/source_members   UTF-8 string[M]
/metadata/source_kinds     UTF-8 string[M]
```

Compatibility must be checked before runtime use. A cache with a mismatching concept code
hash or policy candidate hash must not be used with `concept_index` references.

### Term table

Minimal term storage:

```text
/terms/concept_index       int64[N]
/terms/term                UTF-8 string[N]
/terms/length              int16 or int32[N]
```

`/terms/length` is the tokenized document length for BM25.

Per-row SNOGIT `term_id` and English FSN are intentionally omitted for compactness. The
candidate FSN shown to users should come from the selected main SNOMED HDF5.

## Embedded HDF5 inverted index

The first implementation stored only term rows, then built a Python BM25 index over all
SNOGIT terms at runtime. This is not scalable for ~10M+ rows and can crash the Streamlit
process.

The cache should instead include an HDF5-backed inverted index and use NumPy-vectorized
BM25 retrieval.

### Layout

```text
/index attrs:
  k1 = 1.5
  b = 0.75
  document_count = N
  average_document_length = ...
  tokenizer = snomed_post_processing.sanitization.semantic_text._tokenize

/index/vocab/token             UTF-8 string[V]
/index/vocab/postings_start    int64[V]
/index/vocab/postings_length   int64[V]

/index/postings/term_row       int64[P]
/index/postings/token_count    int16 or int32[P]
```

Where:

- `N` = processed SNOGIT term rows
- `V` = unique tokens
- `P` = total `(token, term_row)` postings after per-term token counting

The postings arrays are conceptually a sparse term-document matrix in compressed sparse
row form by token:

```text
token -> contiguous postings slice -> term rows containing token
```

### Runtime retrieval

For each unresolved finding:

1. Tokenize query text.
2. Resolve query tokens to vocab rows, e.g. via binary search over sorted `/index/vocab/token`.
3. Read only matching postings slices from HDF5.
4. Optionally skip or cap overly common tokens.
5. Compute BM25 contributions with NumPy.
6. Aggregate scores by `term_row`.
7. Keep top term rows.
8. Map `term_row -> concept_index -> SNOMED concept`.
9. Collapse duplicate concepts, keeping best SNOGIT evidence per concept.

Vectorized BM25 contribution:

```python
rows = term_row[start:end]
tf = token_count[start:end]
dl = term_lengths[rows]

contrib = idf * (tf * (k1 + 1.0)) / (
    tf + k1 * (1.0 - b + b * dl / avgdl)
)
```

Then aggregate per row, for example with `np.bincount` or sorted unique candidate rows.
For memory safety, prefer candidate-local aggregation rather than allocating a dense
`N`-length score vector for every query when candidate rows are sparse.

### Common-token safeguards

Some query tokens may have huge posting lists, e.g. generic clinical words. Add runtime
limits:

```text
max_postings_per_token
max_candidate_rows_per_query
max_snogit_hits_per_finding
```

Behavior options for too-common tokens:

- skip overly common tokens when more selective query tokens are available
- cap postings with a warning
- return no SNOGIT candidates with a clear reason if limits would be exceeded

The UI should warn instead of letting Streamlit crash.

## Integration with existing BM25 resolver

Current SNOMED FSN BM25 can remain in-memory because the document count is small enough
for the main HDF5 concept set.

SNOGIT path should differ:

```text
SNOMED FSNs -> existing Python BM25Index
SNOGIT cache -> HDF5 inverted index + NumPy scoring
```

Candidate concept policy gates still apply in policy mode:

```text
active
AND whitelisted
AND not blacklisted
AND not the source concept
AND not SNOMED root
```

SNOGIT must only add candidates; it must not change policy validation.

## Candidate output with source evidence

`SemanticBm25Candidate` should preserve optional SNOGIT evidence:

```python
source: str = "snomed_fsn"       # or "snogit"
matched_term: str | None = None
source_member: str | None = None
```

Review UI rationale example:

```text
rank #1 · BM25 13.42 · lexical 0.67 · SNOGIT: ausstrahlender Thoraxschmerz
```

JSON schema remains backward-compatible by making these fields optional.

## CLI behavior

### Dedicated cache build command

The CLI should expose a dedicated endpoint/command for cache creation. Suggestion
generation should not build a processed SNOGIT cache implicitly.

Proposed command shape:

```text
build-snogit-cache \
  --hdf5 data/gemtex_snomedct_codes_release20260401_policy20240401.hdf5 \
  --snogit-zip data/SNOGIT-release.zip \
  --output data/snogit_cache_release20260401_policy20240401.hdf5 \
  --snogit-member release/SNOGIT_20260712.dat
```

`--snogit-member` should be repeatable. If omitted, the command selects the newest general
`SNOGIT_*.dat` member, excluding `SNOGIT_ELGA_*.dat` and `SNOMED_LATIN_*.dat`.

Suggested options:

```text
--hdf5 PATH                         main SNOMED/policy HDF5 used for concept_index mapping and policy filtering
--snogit-zip PATH                   raw SNOGIT release ZIP
--output PATH                       processed SNOGIT cache HDF5 to write
--snogit-member MEMBER              repeatable; explicit ZIP member selection
--include-elga                      optional convenience for newest ELGA member
--include-latin                     optional convenience for newest Latin member
--overwrite                         allow replacing an existing output cache
--compression gzip|lzf|none         HDF5 compression choice
--compression-level INT             gzip level, if applicable
```

The command should report:

```text
selected members
rows read/kept/written
unknown concepts skipped
policy-ineligible rows skipped
duplicate terms skipped
vocab size
postings count
cache compatibility hashes
output file size
```

Current internal/legacy names may still expose `sidecar` names until renamed, but user
help text should say `processed SNOGIT cache`.

### Suggestion command

Suggestion generation should accept only a prebuilt cache:

```text
suggest-sanitization \
  --semantic-bm25-fallback \
  --use-snogit-cache data/snogit_cache_release20260401_policy20240401.hdf5
```

`--use-snogit-cache PATH` is a single argument that both enables SNOGIT/interface-term
evidence and provides the processed SNOGIT cache path.

Suggestion generation should query using the HDF5 inverted index and must not build a full
in-memory Python BM25 index over SNOGIT terms.

## GUI behavior

The GUI should separate two phases:

```text
1. Create/select processed SNOGIT cache
2. Generate sanitization suggestions using the selected cache
```

Creating a cache from ZIP must not automatically continue into suggestion generation.
After cache creation, the UI should show the created cache path/download button and require
the user to explicitly start the suggestion step with that cache.

In the existing advanced suggestion settings popover:

- Checkbox:

```text
Use SNOGIT/interface terms for BM25 candidates
```

- Processed cache input:

```text
Processed SNOGIT cache HDF5
```

Help text must mention that this can come from a previous run.

- Because Streamlit default uploads are limited to 200 MB, also allow server-side paths:

```text
Or processed SNOGIT cache path on this server
Or SNOGIT release ZIP path on this server
```

The raw `SNOGIT-release.zip` is multi-GB, so server-side path input is preferred. The
Streamlit upload limit can be raised with `server.maxUploadSize`, but large browser
uploads are still not ideal.

Recommended UI behavior:

1. If a compatible processed SNOGIT cache is selected, enable suggestion generation with
   SNOGIT evidence.
2. If only a raw SNOGIT ZIP is selected, show a `Create processed SNOGIT cache` action.
3. During cache creation, use a dedicated `st.status` container for:
   - selected ZIP member discovery
   - parsing/filtering rows
   - writing term table
   - writing inverted index
   - validating compatibility metadata
4. After successful cache creation:
   - show the created cache location
   - expose a download button
   - store the created cache as the selected cache in session state if possible
   - do not automatically start suggestion generation
5. The user then starts suggestion generation explicitly, now using the processed cache.

If ZIP is used, advanced multiselect lists `.dat` members. Default selection is newest
general `SNOGIT_*.dat` only.

## Tests

Small fixture tests, not tests against the multi-GB archive:

1. Parser accepts 4-column SNOGIT rows.
2. Parser accepts 3-column Latin rows.
3. Unknown concept IDs are skipped when writing cache.
4. Default member selection chooses newest general `SNOGIT_*.dat`.
5. Multiple selected members combine and deduplicate by `(concept_index, normalized_term)`.
6. Cache compatibility check rejects mismatching main HDF5 hashes.
7. Dedicated `build-snogit-cache` CLI command writes a processed SNOGIT cache from main HDF5 + ZIP.
8. `suggest-sanitization --use-snogit-cache ...` enables SNOGIT evidence with one argument.
9. `suggest-sanitization --use-snogit-cache ...` does not parse raw ZIP or write a cache.
10. GUI state separates cache creation completion from suggestion generation start.
11. HDF5 inverted index contains expected vocab/postings arrays.
12. NumPy BM25 retrieval returns a SNOGIT-backed candidate without loading all terms.
13. Common-token limits prevent excessive postings loads.
14. Policy gates still exclude inactive, non-whitelisted, and blacklisted concepts.
15. Suggestions JSON preserves optional SNOGIT evidence fields.

## Recommended implementation order

1. Rename/refine user-facing terminology from sidecar to processed SNOGIT cache.
2. Add dedicated CLI `build-snogit-cache` endpoint around the existing cache builder.
3. Change `suggest-sanitization` so `--use-snogit-cache PATH` is the single opt-in for SNOGIT evidence and does not build from ZIP.
4. Split GUI SNOGIT handling into explicit cache creation/select phase and suggestion generation phase.
5. Extend cache builder to write `/terms/length` and `/index/...` inverted arrays.
6. Add cache metadata/schema version `2` while retaining compatibility/read errors for version `1`.
7. Implement HDF5 inverted-index query helper with NumPy vectorized BM25 scoring.
8. Change `SemanticBm25Resolver` so SNOGIT uses the HDF5 query helper instead of adding all SNOGIT rows to the Python BM25Index.
9. Add runtime safety limits and UI/CLI options for those limits.
10. Add tests for CLI separation, GUI phase separation, index layout, scoring, compatibility, and limit behavior.
11. Keep existing SNOMED FSN BM25 path unchanged.

## Important guardrails

- SNOGIT must only add candidate suggestions; it must not change policy validation.
- Candidate policy gates remain authoritative in policy mode.
- Blacklist findings should still require explicit BM25 opt-in.
- Do not build a full in-memory Python BM25 index over all SNOGIT terms.
- Do not parse raw multi-GB SNOGIT ZIP on every run; build/cache once and reuse.
- Store source metadata compactly; avoid duplicating concept FSNs/count-heavy resolved metadata beyond what is needed for reproducibility.
