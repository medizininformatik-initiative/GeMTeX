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

## 14. CLI Shape Idea

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
