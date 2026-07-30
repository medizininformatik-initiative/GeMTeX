# SNOMED Sanitization Design: Source-to-Target Mapping

## 1. Goal

Add a sanitization mode for SNOMED CT annotations where a critical code from a **source** SNOMED CT dump can be mapped to an acceptable code in a **target** SNOMED CT dump.

The target dump is the policy currently used by the project:

- whitelist: allowed concepts;
- blacklist: disallowed concepts.

The source dump represents the SNOMED CT version/universe in which the observed annotation code should be known.

The central question is:

> Given an observed source code that is not acceptable in the target, can we replace it with the nearest acceptable target ancestor?

## 2. Important Constraint

The source and target HDF5 files must remain **completely independent**.

Each HDF5 file should be usable on its own for:

1. the current check/report workflow;
2. the future sanitization workflow.

Therefore, a precomputed source-target crosswalk file is intentionally out of scope.

No file should contain mappings such as:

```text
source_code -> target_code
```

because that would couple two independently generated SNOMED dumps.

Instead, each HDF5 dump should contain enough local SNOMED structure to derive a mapping dynamically when paired with another HDF5 file.

## 3. Conceptual Model

Inputs:

```text
source.hdf5 = dump/version where the observed annotation code exists
target.hdf5 = dump/version/policy to sanitize into
```

For an observed code `C`:

```text
if C is allowed by target:
    keep C
else:
    use source hierarchy to find ancestors of C
    choose nearest ancestor that is allowed by target
```

So relationship data comes from the **source**, while acceptability comes from the **target**.

This is necessary because the critical code may not exist in the target at all. In that case, the target cannot provide parents or ancestors for the code.

## 4. Relationship to Current Check/Report Mode

Current behavior:

```text
observed code in target whitelist     -> OK
observed code not in target whitelist -> critical
observed code in target blacklist     -> critical
```

Sanitization behavior should extend this without breaking it:

```text
observed code in target whitelist and not target blacklist:
    keep original code

observed code not in target whitelist:
    try to map through source ancestors to nearest target-whitelisted code

observed code in target blacklist:
    policy-dependent; probably do not silently sanitize unless explicitly allowed
```

The same HDF5 files should still support pure reporting by reading only whitelist/blacklist datasets.

## 5. Why Ancestor-Based Sanitization

SNOMED CT codes do not encode hierarchy in the identifier itself. A code alone cannot reveal its parents, children, siblings, semantic tag, or replacement history.

Therefore, sanitization requires external relationship data.

The safest SNOMED-aware replacement is usually a **broader ancestor**, not a sibling or lexical match.

Example:

```text
Specific pneumonia subtype
→ Pneumonia
→ Disorder of respiratory system
→ Clinical finding
```

Replacing a specific code with an ancestor is a controlled generalization. Replacing it with a sibling could change meaning.

## 6. Proposed HDF5 Extension

Each HDF5 file should continue to contain the existing whitelist/blacklist structure:

```text
/whitelist/0/codes
/whitelist/0/fsn
/blacklist/0/codes
/blacklist/0/fsn
```

For sanitization, each dump should additionally contain compact concept relationship data.

A possible structure:

```text
/concepts/codes
/concepts/fsn
/concepts/semantic_tag
/concepts/active
/concepts/ancestors_index
/concepts/ancestors_codes
/concepts/ancestors_distance
```

The key requirement is that for any code known to the source dump, we can quickly retrieve:

```text
ancestor code + distance from observed code
```

## 7. Compact Ancestor/Distance Representation

A compact flat representation is preferable to one HDF5 group per concept.

### Example layout

```text
/concepts/codes
```

Array of concept codes. This defines the row order.

```text
/concepts/ancestors_index
```

Array of shape `(n_concepts, 2)` where each row stores:

```text
[start, length]
```

into the flat ancestor arrays.

```text
/concepts/ancestors_codes
```

Flat array containing all ancestor codes for all concepts.

```text
/concepts/ancestors_distance
```

Flat array containing the corresponding distance for each ancestor code.

### Example

For concept `C`:

```text
row = index_of(C in /concepts/codes)
start, length = /concepts/ancestors_index[row]
ancestor_codes = /concepts/ancestors_codes[start:start+length]
distances = /concepts/ancestors_distance[start:start+length]
```

Then candidates are:

```text
ancestor_codes ∩ target_whitelist - target_blacklist
```

The best candidate is the one with the lowest distance.

## 8. Sanitization Algorithm

For each observed annotation code `C`:

1. Check target policy:

```text
if C in target whitelist and C not in target blacklist:
    status = identity
    replacement = C
```

2. If not acceptable, check that `C` exists in source concepts:

```text
if C not in source /concepts/codes:
    status = missing_in_source
    replacement = None
```

3. Retrieve source ancestors and distances.

4. Select candidates:

```text
candidates = ancestors(C) ∩ target_whitelist
candidates = candidates - target_blacklist
```

5. Choose nearest candidate:

```text
min distance
```

6. If several candidates have the same minimum distance:

```text
status = ambiguous
```

or apply explicit tie-breakers.

7. If no candidate exists:

```text
status = no_mapping
replacement = None
```

## 9. Possible Status Values

Recommended statuses:

| Status | Meaning |
|---|---|
| `identity` | Original code is acceptable in target. |
| `nearest_target_ancestor` | Code was mapped to nearest acceptable target ancestor. |
| `missing_in_source` | Observed code is not present in source relationship data. |
| `no_mapping` | Source knows the code, but no acceptable target ancestor exists. |
| `ambiguous` | Multiple equally near acceptable ancestors exist. |
| `blacklisted` | Code or candidate is blacklisted by target policy. |
| `inactive` | Source marks concept inactive; historical handling may be needed. |

## 10. Tie-Breaking Policy

SNOMED CT allows multiple inheritance, so multiple nearest ancestors may exist.

Possible tie-breakers, in decreasing safety:

1. mark as ambiguous and require manual decision;
2. prefer candidate with same semantic tag as source concept;
3. prefer candidate that is not a very broad root concept;
4. prefer candidate with more descendants in target/source, if descendant counts are available;
5. deterministic lexical/numeric ordering only as a final fallback.

For first implementation, ambiguity should probably be reported rather than silently resolved.

## 11. Blacklist Interaction

Blacklist should override whitelist-like generalization.

Recommended first policy:

```text
if observed code is target-blacklisted:
    do not automatically sanitize unless explicit option allows it
```

For ancestor candidates:

```text
candidate must not be in target blacklist
```

This avoids replacing a disallowed code with another concept that is also disallowed.

## 12. Inactive Concepts

Inactive concept handling is separate from ancestor sanitization.

If the source dump stores inactive concepts and historical associations, a future enhancement could resolve:

- `SAME AS`
- `REPLACED BY`
- `POSSIBLY EQUIVALENT TO`
- `MOVED TO`

before ancestor mapping.

Initial implementation may simply report:

```text
status = inactive
```

unless active/inactive information is not available.

## 13. Independence Requirement Revisited

The same HDF5 file should be valid as either:

```text
source.hdf5
```

or:

```text
target.hdf5
```

depending on invocation.

Therefore, each dump should contain:

1. policy lists, if available:
   - whitelist;
   - blacklist;
2. concept metadata:
   - codes;
   - FSNs;
   - optional semantic tags;
   - optional active flags;
3. hierarchy data:
   - compact ancestors and distances.

No dump should assume knowledge of another dump.

## 14. Intentional Redundancy Between Lists and `/concepts`

In a full version dump, the following datasets may contain the same codes and FSNs:

```text
/whitelist/0/codes
/whitelist/0/fsn
/concepts/codes
/concepts/fsn
```

This redundancy is intentional for now.

The groups represent different layers:

```text
/whitelist, /blacklist = policy/list layer
/concepts             = reusable SNOMED reference/hierarchy layer
```

The current check/report workflow reads whitelist and blacklist groups as policy lists. Future sanitization and local reuse workflows read `/concepts` as a self-contained concept universe with hierarchy information.

Keeping both layers separate has advantages:

- existing check/report behavior remains backward compatible;
- `/concepts` can be used independently of a particular policy list;
- future files can contain a full `/concepts` universe with smaller whitelist/blacklist subsets;
- source and target HDF5 files remain independently usable.

More compact alternatives are possible, for example storing whitelist/blacklist as indices into `/concepts/codes`, but that would complicate readers and schema compatibility. Unless file size becomes a serious issue, the duplicated code/FSN storage is acceptable.

## 15. CLI Shape Idea

Possible future command:

```bash
uv run sanitize-critical-documents \
  --source-lists-path /path/to/source.hdf5 \
  --target-lists-path /path/to/target.hdf5 \
  /path/to/inception-export.zip
```

Or as an option on the existing command:

```bash
uv run log-critical-documents \
  --lists-path /path/to/target.hdf5 \
  --sanitize \
  --source-lists-path /path/to/source.hdf5 \
  /path/to/inception-export.zip
```

The second option may be preferable because sanitization is an extension of critical-code reporting.

## 15. Output Idea

Reports could include additional columns:

| Original Code | Covered Text | Offset | Status | Replacement Code | Replacement FSN | Distance |
|---|---|---:|---|---|---|---:|
| `123` | example | `(10, 20)` | `nearest_target_ancestor` | `456` | `Broader concept (finding)` | `2` |
| `789` | example | `(30, 40)` | `no_mapping` |  |  |  |

The JSON dump should preserve both original and replacement information.

## 16. Summary

The preferred design is:

```text
source relationships + target policy = dynamic sanitization mapping
```

No precomputed crosswalk should be stored because source and target HDF5 files must remain independent.

The best HDF5 extension is a compact ancestor/distance representation that lets any dump act as a source for hierarchy lookup while still supporting the current whitelist/blacklist reporting workflow.

Implementation note: dump generation supports an optional `--memoize-ancestors` flag for computing this extension. It is disabled by default to keep the initial behavior simple, but can be enabled for large hierarchies where repeated ancestor traversal becomes expensive.

When adding a second list type to an HDF5 file that already has `/concepts`, dump generation skips parent-map collection during Snowstorm traversal unless `--force-overwrite-concepts` is used. This avoids unnecessary memory/CPU overhead for rebuilding the extension, though the Snowstorm traversal is still needed until an optional local `--reuse-concepts` mode exists.

Overwrite semantics are intentionally separated:

```text
--force-overwrite          overwrites only the selected /whitelist or /blacklist group
--force-overwrite-concepts rebuilds the /concepts hierarchy extension
```

This makes it safe to repair/recreate an invalid `/blacklist` without deleting the existing `/whitelist` or rebuilding `/concepts`.

## 17. Future Local List Generation: `--reuse-concepts`

A useful follow-up improvement is an optional local-only mode for `create-concepts-dump`:

```bash
uv run create-concepts-dump \
  --dump-mode semantic \
  --filter-list config/blacklist_filter_tags.txt \
  --reuse-concepts \
  --branch MAIN/2024-04-01
```

The intended workflow is:

```bash
# First run: expensive Snowstorm traversal, writes whitelist and /concepts.
uv run create-concepts-dump \
  --dump-mode version \
  --branch MAIN/2024-04-01

# Second run: local-only blacklist derivation from existing /concepts.
uv run create-concepts-dump \
  --dump-mode semantic \
  --filter-list config/blacklist_filter_tags.txt \
  --reuse-concepts \
  --branch MAIN/2024-04-01
```

### Goal

`--reuse-concepts` should derive the requested whitelist/blacklist list from the existing HDF5 `/concepts` extension without querying Snowstorm again.

This is especially useful when creating one HDF5 file containing both:

```text
/whitelist/0/...
/blacklist/0/...
/concepts/...
```

### Strict behavior

`--reuse-concepts` should be explicit and local-only.

If reuse is impossible, the command should fail with a clear error instead of silently falling back to Snowstorm traversal.

It should fail if:

- the HDF5 file does not exist;
- `/concepts` is missing;
- required `/concepts` datasets are missing;
- an explicit numeric filter code is not present in `/concepts/codes`;
- the requested local operation cannot be represented from the available data.

### Required `/concepts` datasets

The local mode needs:

```text
/concepts/codes
/concepts/fsn
/concepts/ancestors_index
/concepts/ancestors_codes
/concepts/ancestors_distance
```

For semantic-tag-only filtering, only `codes` and `fsn` are strictly required.

For explicit numeric root-code filters, ancestor arrays are required.

### Local semantic-tag filtering

Semantic tags can be derived from FSNs in `/concepts/fsn`.

Example:

```text
Pneumonia (disorder)
```

matches semantic tag:

```text
disorder
```

The local implementation should reuse the same flexible semantic-tag matching behavior as the Snowstorm-backed path, including case-insensitive matching and flexible whitespace.

For positive filtering:

```text
selected = concepts whose FSN semantic tag matches one of the filter tags
```

For negative filtering:

```text
selected = all concepts - matching concepts
```

### Local explicit-root-code filtering

The current semantic dump mode also allows numeric concept IDs in the filter list. A numeric filter means:

```text
include this concept and its descendants
```

Because `/concepts` stores ancestors, descendants can be derived locally by scanning ancestor arrays.

For root code `R`, concept `C` is a descendant of `R` when:

```text
R in ancestors(C)
```

The descendant set is therefore:

```text
{R} ∪ {C | R appears in ancestors(C)}
```

This is local and avoids Snowstorm traversal, but it is still an O(number of concepts × average ancestor count) scan. That should be acceptable as a first implementation and can later be optimized with a reverse index if needed.

### Combining filters

The existing filter parsing should be preserved:

```text
numeric entries     -> explicit root concept filters
non-numeric entries -> semantic tag filters
```

For `FilterMode.POSITIVE`:

```text
selected = semantic_tag_matches ∪ descendants_of_numeric_roots
```

For `FilterMode.NEGATIVE`:

```text
selected = all_concepts - semantic_tag_matches - descendants_of_numeric_roots
```

### Writing output

After deriving selected codes locally, the command can reuse the existing HDF5 writer:

```python
dump_codes_to_hdf5(
    fi_path=hdf5_path,
    codes=selected_codes,
    id_to_fsn_dict=local_code_to_fsn,
    list_type=ListDumpType.BLACKLIST or ListDumpType.WHITELIST,
    parent_map=None,
)
```

In `--reuse-concepts` mode, `parent_map` should not be passed. The existing `/concepts` extension should be treated as authoritative and left untouched.

### Interaction with `--force-overwrite`

In local reuse mode, `--force-overwrite` should only affect the requested list group, e.g. `/blacklist` or `/whitelist`.

It should not rebuild or delete `/concepts`. Rebuilding `/concepts` should require the separate `--force-overwrite-concepts` flag.

### Applicability by dump mode

#### `--dump-mode semantic`

Primary target.

This can derive blacklists locally from:

- semantic tags in FSNs;
- explicit numeric root concept IDs using ancestor arrays.

#### `--dump-mode version`

Possible but less important.

A local version dump could derive a whitelist from all `/concepts/codes`, but this depends on trusting that `/concepts` was generated from the intended root and branch. If `/concepts` was created from a narrow or non-recursive traversal, the resulting whitelist would be partial.

Therefore, local version reuse should either be documented as "use all existing concepts" or deferred until there is a clearer use case.

### Important caveat

`--reuse-concepts` can only derive from the concepts already present in `/concepts`.

If `/concepts` was generated with:

```bash
--not-recursive
```

or from a narrow root code, the local result will be correspondingly incomplete.

### Suggested implementation phases

1. Implement local semantic-tag filtering.
2. Implement local numeric root-code descendant filtering by scanning ancestor arrays.
3. Optionally support local `--dump-mode version` by using all `/concepts/codes`.
4. Optionally optimize descendant lookups with a reverse ancestor-to-descendant index if local scans become too slow.

## 18. BM25-Based Sanitization Without a Target Hierarchy

A BM25-based approach can be useful when no usable target hierarchy/version is available, but it should be treated as a lexical fallback, not as SNOMED-safe relationship mapping.

BM25 can answer:

```text
Which allowed concept label looks lexically similar to this source concept/text?
```

It cannot answer:

```text
Is this candidate an ancestor, replacement, sibling, or clinically safe generalization?
```

Therefore BM25 mode should initially produce suggestions, not silent automatic replacements.

### Candidate corpus

The candidate corpus should be restricted to safe replacement candidates, for example:

```text
/whitelist/0/codes + /whitelist/0/fsn
```

or a curated safe replacement catalog.

Blacklist concepts must be excluded from candidates.

### Query text

For each critical annotation, the query can be built from available fields:

- source FSN, if known;
- preferred term, if available in future resources;
- synonyms, if available in future resources;
- covered text from the annotation;
- semantic tag as metadata/filter, not necessarily as free text.

FSNs should usually be split into:

```text
main term:    Pneumonia
semantic tag: disorder
```

The main term should be indexed/searched lexically. The semantic tag should usually be used as a filter or compatibility check.

### Ranking safeguards

A BM25 suggestion should only be accepted automatically, if ever, when strict safeguards pass:

```text
candidate is whitelisted
candidate is not blacklisted
candidate semantic tag is identical or explicitly compatible
BM25 score >= configured threshold
top candidate is clearly better than second candidate
```

Useful ambiguity checks:

```text
top_score - second_score >= margin
```

or:

```text
top_score / second_score >= ratio
```

If the top candidates are too close, the status should be ambiguous.

### Specificity caveat

BM25 tends to prefer lexical similarity, not safe generalization.

Example:

```text
query: Bacterial pneumonia
```

BM25 may rank both of these highly:

```text
Pneumonia
Viral pneumonia
```

Only `Pneumonia` is a plausible generalization. `Viral pneumonia` is a sibling-like or related concept and may be clinically wrong.

Without hierarchy, a possible heuristic is to prefer broader-looking terms by penalizing extra qualifiers, but this remains heuristic and should be used carefully.

Possible status values:

| Status | Meaning |
|---|---|
| `bm25_suggested` | Candidate found and safeguards passed. |
| `bm25_ambiguous` | Multiple candidates are too close. |
| `bm25_no_candidate` | No candidate was found. |
| `bm25_score_too_low` | Best candidate did not meet threshold. |
| `bm25_semantic_tag_mismatch` | Best lexical candidate failed semantic compatibility. |

## 19. BM25 Handling for Non-Whitelisted Codes

For codes that are not on the whitelist, BM25 can be a fallback after hierarchy-based sanitization fails or when no target hierarchy exists.

Recommended order:

```text
if code is target-whitelisted and not target-blacklisted:
    keep original code
elif source/target hierarchy mapping is available:
    try nearest target-whitelisted ancestor
elif BM25 fallback is enabled:
    search safe whitelist candidates lexically
else:
    mark as unsanitizable
```

For this case, BM25 is somewhat defensible because absence from the whitelist may mean:

- the code is too specific;
- the source and target versions differ;
- the code is missing from the target resources;
- a broader allowed replacement may exist.

Even then, the first implementation should report BM25 results as suggestions unless the safeguards are deliberately configured for automatic replacement.

Suggested report columns:

| Original Code | Covered Text | Status | Suggested Code | Suggested FSN | BM25 Score | Reason |
|---|---|---|---|---|---:|---|
| `123` | example | `bm25_suggested` | `456` | `Broader concept (finding)` | `12.4` | `top candidate passed threshold and margin` |

## 20. BM25 Handling for Blacklisted Codes

Blacklisted codes should be handled more conservatively than merely non-whitelisted codes.

A non-whitelisted code may be absent for technical or versioning reasons. A blacklisted code is explicitly disallowed by policy.

Therefore the default policy should be:

```text
if code is blacklisted:
    do not auto-replace by BM25
```

Instead, one of the following should happen:

- remove the annotation/code;
- require manual review;
- apply an explicit configured replacement;
- optionally provide BM25 suggestions for review only.

### Why BM25 is risky for blacklisted codes

Example:

```text
blacklisted: Viral pneumonia
```

BM25 might suggest:

```text
Bacterial pneumonia
Pneumonia
Respiratory infection
```

Depending on the blacklist intent, some or all of these may still be unsafe.

Another example:

```text
blacklisted: Occupation
```

BM25 might suggest:

```text
Employment status
Occupational history
```

These are lexically close but may preserve the same privacy-sensitive information.

### Preferred blacklist policy

Blacklisted concepts should be governed by explicit policy:

```text
remove
replace_with_configured_code
manual_review
suggest_only
```

Possible configuration shape:

```json
{
  "blacklist_replacements": {
    "224930009": {
      "action": "remove"
    },
    "123456789": {
      "action": "replace",
      "replacement": "404684003"
    }
  },
  "blacklist_tag_policy": {
    "occupation": "remove",
    "geographic location": "remove",
    "situation": "manual_review"
  }
}
```

### BM25 as review assistance only

If BM25 is enabled for blacklisted codes, it should produce review suggestions with stricter safeguards:

```text
candidate must be whitelisted
candidate must not be blacklisted
candidate must not belong to the same forbidden semantic category
candidate must pass a higher score threshold
candidate must have a clear margin over the next candidate
```

Suggested statuses:

| Status | Meaning |
|---|---|
| `blacklisted_remove` | Policy says to remove. |
| `blacklisted_manual_review` | Human decision required. |
| `blacklisted_explicit_replacement` | Policy gives a replacement. |
| `blacklisted_bm25_suggestion` | BM25 candidate is shown for review only. |
| `blacklisted_no_safe_replacement` | No acceptable replacement found. |

Recommended decision flow:

```text
if code is blacklisted:
    if explicit replacement configured:
        replace
    elif explicit remove configured:
        remove
    elif BM25 review suggestions enabled:
        show top-k safe candidates
    else:
        manual_review
```

This keeps blacklist handling policy-driven and avoids treating lexical similarity as evidence of safe sanitization.
