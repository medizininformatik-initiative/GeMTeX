# RF2 Release ZIP to HDF5 Ingestion Design

## 1. Goal

SNOMED CT RF2 release ZIPs are large. HDF5 dumps for this project should therefore be generated without fully extracting the ZIP and without loading complete RF2 files into memory.

The goal is a streaming/chunked ingestion pipeline:

```text
SNOMED RF2 release ZIP
    ↓ stream selected RF2 TSV files directly from ZIP
    ↓ reconstruct target release state if using Full files
    ↓ filter to data needed by this project
    ↓ write compact HDF5 datasets
```

Runtime analysis should use the generated HDF5 files, not raw RF2 ZIPs.

## 2. General Approach

Use Python's `zipfile` module to read RF2 `.txt` members directly from the ZIP archive:

```python
import csv
import zipfile
from io import TextIOWrapper

with zipfile.ZipFile("SnomedCT_Full.zip") as zf:
    with zf.open(".../Full/Terminology/sct2_Concept_Full_INT_20250131.txt") as raw:
        text = TextIOWrapper(raw, encoding="utf-8")
        reader = csv.DictReader(text, delimiter="\t")
        for row in reader:
            ...
```

This avoids extracting multi-GB contents to disk.

## 3. Relevant RF2 Files

The ingestion code should discover relevant files by filename/path patterns.

### Basic concept policy/list generation

Usually requires:

```text
*/Snapshot/Terminology/sct2_Concept_Snapshot_*.txt
*/Snapshot/Terminology/sct2_Description_Snapshot-*.txt
```

or their `Full` equivalents if reconstructing a specific release date:

```text
*/Full/Terminology/sct2_Concept_Full_*.txt
*/Full/Terminology/sct2_Description_Full-*.txt
```

### Hierarchy / ancestor support

Requires relationship data:

```text
*/Snapshot/Terminology/sct2_Relationship_Snapshot_*.txt
*/Full/Terminology/sct2_Relationship_Full_*.txt
```

For inferred hierarchy, use the regular relationship file and filter to active `is-a` relationships:

```text
typeId = 116680003
```

### Historical replacement support

Requires historical association reference sets, usually under `Refset/Content` or similar RF2 refset folders:

```text
*/Snapshot/Refset/Content/*AssociationSnapshot*.txt
*/Full/Refset/Content/*AssociationFull*.txt
```

Exact filenames vary by edition/release, so matching should be pattern-based and validated by columns.

## 4. Snapshot vs Full

### Snapshot input

Snapshot files already represent the component/member state at one release date. They can still contain inactive rows, so active-only outputs must explicitly filter `active == 1`.

Ingestion can process them directly:

```text
read row
    ↓
if active and relevant
    ↓
write/collect for HDF5
```

### Full input

Full files contain historical rows. To reconstruct release state at target date `T`:

```text
for each component/member id:
    keep latest row where effectiveTime <= T
```

This applies to:

- concepts;
- descriptions;
- relationships;
- historical association refset rows.

Important: for `Full` files, do not filter out inactive rows before reconstructing the latest row per id. An inactive row may be the latest state and may supersede an older active row. Date filtering can happen while streaming; active filtering should happen after latest-row reconstruction.

The algorithm should stream rows and keep only the latest relevant row per component.

Pseudo-code:

```python
latest = {}

for row in rf2_rows:
    component_id = row["id"]
    effective_time = row["effectiveTime"]

    if effective_time > target_release_date:
        continue

    previous = latest.get(component_id)
    if previous is None or effective_time > previous["effectiveTime"]:
        latest[component_id] = compact_row(row)
```

After streaming, `latest.values()` is the reconstructed snapshot for that RF2 component type.

## 5. Memory Strategy

Do not store full RF2 rows if not needed. Store compact structures with only project-relevant fields.

### Concepts

Minimal state:

```python
concepts = {
    concept_id: {
        "effectiveTime": "20250131",
        "active": "1",
        "moduleId": "...",
        "definitionStatusId": "...",
    }
}
```

For many tasks, only this is needed:

```text
concept_id -> active
```

### Descriptions

Filter early where safe:

- language code, e.g. `en` in the International Edition; other languages such as German require an appropriate extension/package;
- FSNs only if only FSNs are needed;
- synonyms only if search/indexing requires them.

For `Snapshot` files, active descriptions can be filtered directly with `active == 1`. For `Full` files, reconstruct the latest row per description id first, then filter to active rows. Do not discard inactive `Full` rows before reconstruction.

Useful fields:

```text
id
effectiveTime
active
conceptId
languageCode
typeId
term
```

Known description type IDs:

```text
900000000000003001 = fully specified name
900000000000013009 = synonym
900000000000550004 = definition
```

### Relationships

For parent hierarchy, filter aggressively after choosing the correct release state:

```text
active == 1
typeId == 116680003  # is-a
```

For `Snapshot`, this can be applied directly. For `Full`, first reconstruct the latest row per relationship id at the target date, then filter to active `is-a` relationships.

Compact parent map:

```python
parents[sourceId].add(destinationId)
```

Only active reconstructed relationships should contribute to the target-release hierarchy.

### Historical associations

Historical association rows are typically much smaller than relationship data. In the inspected International Edition package they are present as:

```text
Refset/Content/der2_cRefset_AssociationFull_INT_<date>.txt
Refset/Content/der2_cRefset_AssociationSnapshot_INT_<date>.txt
```

with columns:

```text
id effectiveTime active moduleId refsetId referencedComponentId targetComponentId
```

Store compact rows such as:

```text
source_code = referencedComponentId
target_code = targetComponentId
association_type = decoded refsetId
effective_time = effectiveTime
active = active
```

## 6. Historical Association Type Mapping

Historical association refsets encode relationship type via `refsetId`.

Common association types include:

```text
SAME_AS
REPLACED_BY
POSSIBLY_EQUIVALENT_TO
WAS_A
MOVED_TO
MOVED_FROM
ALTERNATIVE
```

The ingestion code should map known SNOMED refset IDs to stable internal labels.

Example conceptual mapping:

```python
ASSOCIATION_REFSET_IDS = {
    "900000000000527005": "SAME_AS",
    "900000000000526001": "REPLACED_BY",
    "900000000000523009": "POSSIBLY_EQUIVALENT_TO",
    "900000000000528000": "WAS_A",
    "900000000000525002": "MOVED_TO",
    "900000000000524003": "MOVED_FROM",
    "900000000000530003": "ALTERNATIVE",
}
```

Exact IDs should be verified against the SNOMED edition being processed.

## 7. HDF5 Output Structure

The compact RF2-derived HDF5 layout stores canonical concept metadata once and represents policies as integer views into `/concepts`.

Canonical concept metadata:

```text
/concepts/codes
/concepts/fsn
/concepts/semantic_tag_id
/concepts/semantic_tags
/concepts/active
```

Historical associations are also index-based:

```text
/historical_associations/source_index
/historical_associations/target_index
/historical_associations/association_type_id
/historical_associations/association_types
/historical_associations/effective_time
/historical_associations/active
/historical_associations/refset_id
```

Policy views:

```text
/policy_views/whitelist/0/concept_index
/policy_views/whitelist/0/root_codes
/policy_views/whitelist/0/filter_tags
/policy_views/blacklist/0/concept_index
/policy_views/blacklist/0/root_codes
/policy_views/blacklist/0/filter_tags
```

This avoids duplicating large string datasets under whitelist/blacklist groups. `log-critical-documents` can read these compact policy views directly by resolving `concept_index` through `/concepts/codes` and `/concepts/fsn`.

The existing legacy structure can still be written optionally for backward compatibility with older code:

```text
/whitelist/0/codes
/whitelist/0/fsn
/blacklist/0/codes
/blacklist/0/fsn
```

Optional hierarchy/ancestor support:

```text
/concepts/ancestors_index
/concepts/ancestors_codes
/concepts/ancestors_distance
```

## 8. Ancestor Computation

Ancestor computation can be expensive for large SNOMED hierarchies.

It should be optional and disabled by default unless a workflow explicitly requires ancestor-based fallback.

Recommended default for revised sanitization:

```text
include historical associations
skip full ancestor closure
```

If enabled, compute ancestor closure from the active `is-a` parent map:

```text
concept -> parent -> grandparent -> ...
```

Store compact flat arrays:

```text
/concepts/ancestors_index      # per concept: [start, length]
/concepts/ancestors_codes      # flat ancestor code array
/concepts/ancestors_distance   # flat distance array
```

This supports nearest-whitelisted-ancestor fallback without one HDF5 group per concept.

## 9. Implementation Modules

The first implementation is provided as a compact module:

```text
src/snomed_post_processing/rf2/__init__.py
```

It currently supports Snapshot-based ingestion from RF2 ZIP files and writes enriched HDF5 data under:

```text
/concepts
/historical_associations
/policy_views
```

The module exposes:

```python
discover_snapshot_members(zip_path, language="en")
write_snapshot_hdf5_from_rf2_zip(
    zip_path,
    output_path,
    language="en",
    include_associations=True,
    include_ancestors=False,
    whitelist_root_codes=None,
    blacklist_filter_tags=None,
    write_legacy_policy_groups=False,
    force_overwrite=False,
)
```

A future refactor can split it into the originally proposed package structure:

```text
src/snomed_post_processing/rf2/
    __init__.py
    zip_reader.py          # discover and stream RF2 files from ZIP
    snapshot_builder.py    # reconstruct target release state from Full files
    associations.py        # decode historical associations
    hdf5_writer.py         # write compact HDF5 datasets
```

Responsibilities:

### `zip_reader.py`

- open RF2 ZIPs;
- find matching Concept/Description/Relationship/Association files;
- stream rows as dictionaries;
- validate required columns.

### `snapshot_builder.py`

- handle Snapshot vs Full semantics;
- reconstruct latest row per component at release date;
- apply early filtering.

### `associations.py`

- map association `refsetId` values to stable labels;
- filter active historical associations;
- expose source-to-target candidate lookup structures.

### `hdf5_writer.py`

- write existing whitelist/blacklist datasets;
- write concept metadata;
- write historical associations;
- optionally write ancestor arrays.

## 10. CLI Shape

The existing `create-concepts-dump` command now has two mutually exclusive input modes:

```text
Snowstorm mode: provide both --ip and --port
RF2 ZIP mode:   provide --zip
```

RF2 ZIP example creating both compact whitelist and blacklist policy views in one HDF5:

```bash
uv run create-concepts-dump \
  --zip data/international.zip \
  --output data/gemtex_snomedct_codes_20260401.hdf5 \
  --dump-mode version \
  --filter-list config/blacklist_filter_tags.txt \
  138875005
```

In RF2 ZIP mode with `--dump-mode version`, `ROOT_CODE` creates the whitelist policy view and an optional `--filter-list` creates the blacklist policy view. The filter list follows the Snowstorm-style split:

- numeric entries are treated as root concept codes and expand to the active root concept plus all active descendants via RF2 `is-a` relationships;
- non-numeric entries are treated as semantic tags extracted from FSNs.

`--dump-mode semantic` can still be used when only a blacklist policy view should be generated.

When adding a blacklist to an HDF5 file that already contains `/concepts`, the existing concept table is reused. `--force-overwrite` applies to the selected policy view (`/policy_views/whitelist` or `/policy_views/blacklist`) and optional legacy policy group only. Rebuilding `/concepts` requires `--force-overwrite-concepts`.

Policy views store date metadata:

```text
/policy_views/<whitelist|blacklist>/0.attrs["policy_date"]
/policy_views/<whitelist|blacklist>/0.attrs["release_date"]
/policy_views/<whitelist|blacklist>/0.attrs["rf2_view"]
```

In current RF2 Snapshot mode, `policy_date` must equal the Snapshot `release_date`, because Snapshot files only represent one release state. To use a recent RF2 package to generate policy views for an earlier date, the ingestion must use RF2 Full reconstruction: latest row per component/member at or before the requested policy date, then active filtering. Snapshot mode rejects mismatching earlier policy dates rather than silently creating a misleading policy view.

Snowstorm mode still uses explicit server settings:

```bash
uv run create-concepts-dump \
  --ip localhost \
  --port 8080 \
  --branch MAIN/2024-04-01 \
  138875005
```

Optional flags:

```bash
--rf2-view snapshot|full
--language en
--include-history
--include-ancestors
--fsn-only
```

The International Edition package inspected here contains English (`-en`) terminology and language refsets. German (`de`) input would require a German extension/package.

For revised sanitization, the important first feature is:

```text
--include-history
```

For compact policy-list generation, add explicit policy inputs such as whitelist root codes and blacklist semantic tags. Legacy list groups should be optional because `/policy_views` is more compact:

```text
--whitelist-root-code 138875005
--blacklist-filter-tag attribute
--blacklist-root-code 123456789
--write-legacy-policy-groups
```

Ancestor closure can be added later:

```text
--include-ancestors
```

## 11. Error Handling and Validation

The ingestion should fail clearly if required files or columns cannot be found.

Examples:

- no Concept RF2 file found;
- no Description RF2 file found;
- multiple ambiguous matching files found;
- required columns missing;
- `--release-date` missing for Full reconstruction;
- historical associations requested but no association file found.

For large files, progress logging should report:

- rows read;
- rows skipped by date;
- rows skipped by inactive status;
- rows kept;
- number of concepts/descriptions/associations written.

## 12. Summary

SNOMED release ingestion should be streaming and selective:

```text
read directly from ZIP
filter early
keep only compact latest rows
write HDF5 arrays
make expensive ancestor closure optional
```

For the revised sanitization design, RF2 Full releases are used upstream to create enriched target-release HDF5 files containing historical associations. Runtime checking and sanitization should operate on those HDF5 files, not on raw RF2 release ZIPs.
