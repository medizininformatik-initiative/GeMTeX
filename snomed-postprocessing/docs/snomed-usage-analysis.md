# SNOMED CT usage in this project

This note summarizes how SNOMED CT is used by the code under `src/`, with terminology context from the local OKF bundle.

Consulted OKF files:

- `okf/snomed/index.md`
- `okf/snomed/release-format-rf2.md`
- `okf/snomed/model/release-file-associations.md`
- `okf/snomed/implementation-notes.md`
- `okf/snomed/component-files/concept-file.md`
- `okf/snomed/component-files/description-file.md`
- `okf/snomed/component-files/relationship-file.md`
- `okf/snomed/model/metadata-hierarchy.md`

## Overall role

The project uses SNOMED CT mainly as a versioned terminology policy source for checking annotated clinical documents.

It is not a full SNOMED reasoning engine during document processing. Instead, it precomputes whitelist/blacklist policy data from SNOMED sources, stores that data in HDF5, and then performs fast concept-ID checks against INCEpTION/UIMA annotations.

The main SNOMED-related workflows are:

1. Build an HDF5 SNOMED policy file.
2. Extract SNOMED concept IDs from annotated CAS documents.
3. Check concept IDs against whitelist/blacklist policy views.
4. Generate sanitization suggestions using SNOMED historical associations.
5. Optionally use lexical BM25 fallback when historical associations are insufficient.

## Concept IDs in annotations

Annotations are read from UIMA CAS files in `src/snomed_post_processing/uima_processing/extraction.py`.

By default, the checked annotation layer is:

```text
gemtex.Concept
```

The code expects an annotation feature called `id`, commonly shaped like:

```text
http://snomed.info/id/<SCTID>
```

It strips the SNOMED URI prefix and keeps the plain SCTID. This is appropriate because SCTIDs are identifiers, not numeric quantities, so the project handles them primarily as strings.

For each relevant annotation, the extraction step records:

- SNOMED code
- covered text
- character offset
- annotation layer
- ignored-overlap status

## HDF5 as SNOMED policy store

The project stores SNOMED-derived knowledge in HDF5 files. The newer compact layout includes:

```text
/concepts/codes
/concepts/fsn
/concepts/active
/concepts/semantic_tags
/concepts/semantic_tag_id
/policy_views/whitelist/0/concept_index
/policy_views/blacklist/0/concept_index
/historical_associations/...
```

This maps well to the RF2 model described in the OKF:

- Concept File → concept IDs and active state
- Description File → FSNs
- Relationship File → `is a` hierarchy
- historical association reference sets → replacement/sanitization suggestions

The project correctly separates the full concept universe under `/concepts`, policy-specific subsets under `/policy_views`, and historical association data under `/historical_associations`.

## RF2 ingestion

RF2 ingestion is implemented mainly in:

- `src/snomed_post_processing/release_ingestion/readers.py`
- `src/snomed_post_processing/release_ingestion/hdf5_writer.py`

The OKF emphasizes that RF2 files are versioned row sets. In Full releases, the current state must be reconstructed by selecting the row with the greatest `effectiveTime` at or before the target date. The project implements this pattern using `policy_date` and reconstruction logic for Full releases.

The ingestion reads:

- concept active state
- Fully Specified Names (FSNs)
- active `is a` relationships
- historical associations

Important SNOMED metadata identifiers are used correctly:

```python
FSN_TYPE_ID = "900000000000003001"
IS_A_TYPE_ID = "116680003"
```

The default root code is:

```text
138875005
```

which is the SNOMED CT root concept.

## Hierarchy usage

The project uses the SNOMED `is a` hierarchy for policy construction and ancestor data.

In RF2 mode, hierarchy edges are derived from active Relationship File rows where:

```text
typeId = 116680003
```

In Snowstorm mode, the code recursively traverses child concepts below a selected root concept.

This supports workflows such as:

- whitelist all descendants of a root concept
- blacklist descendants of selected root concepts
- compute compact ancestor arrays for HDF5

The project does not substantially use SNOMED attribute relationships, relationship groups, or full description-logic definitions.

## Semantic tags

Semantic tags are extracted from FSNs by parsing the final parenthesized suffix, for example:

```text
Disease (disorder) -> disorder
Procedure (procedure) -> procedure
```

This is used for semantic-tag-based blacklist construction and filtering.

This is a practical policy mechanism, but it should not be confused with full SNOMED concept-model reasoning. Semantic tags are broad FSN categories, not complete formal semantics.

## Whitelist/blacklist checking

Document analysis is implemented in `src/snomed_post_processing/uima_processing/analysis.py`.

The policy check is deterministic:

- whitelist mode: a finding is critical if its code is not in the whitelist
- blacklist mode: a finding is critical if its code is in the blacklist

The project does not ask whether a code is semantically equivalent to an allowed code. It asks whether the exact SCTID is present in the configured policy view.

That makes the result conservative, auditable, and reproducible.

## Historical associations and sanitization suggestions

The most SNOMED-aware sanitization logic is in `src/snomed_post_processing/sanitization/resolver.py`.

SNOMED inactive concepts can have historical association reference set entries such as:

- `SAME_AS`
- `REPLACED_BY`
- `POSSIBLY_EQUIVALENT_TO`
- `WAS_A`
- `ALTERNATIVE`
- `POSSIBLY_REPLACED_BY`

The resolver uses these associations to suggest replacements:

1. Start from a critical finding.
2. Skip ignored findings.
3. Avoid automatic sanitization for blacklist findings by default.
4. For whitelist findings, find the source concept in `/concepts`.
5. Look up active historical associations.
6. Filter to allowed association types.
7. Check that target concepts are active, whitelisted, and not blacklisted.
8. Return a replacement only when there is a single acceptable target.

This aligns well with SNOMED CT’s official historical-association mechanism for inactive or changed concepts.

## BM25 fallback

The BM25 fallback is not official SNOMED reasoning. It is lexical matching over concept text.

The project treats it as suggestion-only fallback behavior, which is appropriate. Historical associations should be considered stronger evidence than BM25 suggestions.

## Strengths

- Good separation between SNOMED ingestion and document checking.
- Correct use of RF2 version-state reconstruction for Full releases.
- Correct use of key metadata SCTIDs: FSN type and `is a`.
- Practical HDF5 layout for fast local policy checks.
- Historical associations are used for sanitization suggestions.
- Exact SCTID policy checks are simple, auditable, and reproducible.
- Release and policy dates are represented, which matters for SNOMED versioning.

## Limitations

- Runtime checking is exact-ID based, not reasoning-based.
- Semantic tag filtering is based on FSN suffix parsing.
- SNOMED attribute relationships are not meaningfully used.
- Relationship groups and concept-model attributes are ignored.
- Language/dialect acceptability is not deeply modeled.
- Preferred terms are represented in some Snowstorm models, but RF2 ingestion focuses mainly on FSNs.
- Applying sanitization suggestions back into CAS files is not implemented yet.

## Bottom line

This project uses SNOMED CT as a SNOMED-derived policy validation and sanitization-support layer for annotated INCEpTION projects.

The strongest SNOMED integration points are:

1. RF2/Snowstorm policy generation
2. release-date-aware concept state handling
3. hierarchy-based whitelist/blacklist construction
4. FSN/semantic-tag extraction
5. historical-association-based replacement suggestions

That usage is appropriate for quality control of SNOMED-coded annotations, provided users understand that the runtime policy check is exact SCTID matching rather than full SNOMED reasoning.
