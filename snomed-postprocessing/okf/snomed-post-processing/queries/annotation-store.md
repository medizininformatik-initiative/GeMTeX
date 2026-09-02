---
type: Query Cookbook
title: Annotation-store reusable queries
description: Reusable SQL files and Python query-runner conventions for the annotation-store SQLite database.
resource: /queries/annotation-store
tags: [sqlite, queries, annotation-store, reporting]
status: draft
generated: { by: pi-coding-agent/gpt-5, at: 2026-09-02T00:00:00Z }
sources:
  - id: runner
    resource: /queries/run_sql.py
    title: Python SQLite query runner
  - id: semantic-tag-counts
    resource: /queries/annotation-store/semantic_tag_counts.sql
    title: Semantic tag counts query
  - id: top-sctids
    resource: /queries/annotation-store/top_sctids.sql
    title: Top SCTIDs query
  - id: texts-for-st
    resource: /queries/annotation-store/texts_for_st.sql
    title: Covered-text bins by semantic tag query
  - id: fsn-for-text
    resource: /queries/annotation-store/fsn_for_text.sql
    title: FSN counts by covered text query
  - id: text-variants-for-text
    resource: /queries/annotation-store/text_variants_for_text.sql
    title: Covered-text variants for text search query
  - id: schema
    resource: /okf/snomed-post-processing/data/annotation-store-sqlite.md
    title: Annotation store SQLite schema
---

# Annotation-store reusable queries

Reusable analysis queries live under:

```text
queries/annotation-store/
```

They are intended to run against SQLite databases created by `build-annotation-store`.

# Query runner

Use the Python stdlib SQLite wrapper instead of `uvx sqlite3`:

```bash
uv run python queries/run_sql.py \
  gemtex_semantic_snomed_annotations.sqlite \
  queries/annotation-store/semantic_tag_counts.sql
```

`uvx sqlite3` is not expected to work because `sqlite3` is a system binary / Python stdlib module, not a PyPI tool package.

Supported output formats:

```bash
uv run python queries/run_sql.py --format table DB.sqlite query.sql
uv run python queries/run_sql.py --format json DB.sqlite query.sql
uv run python queries/run_sql.py --format csv DB.sqlite query.sql > result.csv
```

By default the runner prints a small metadata block containing the query path, row count, limit parameter `n` when present, and effective parameters. For table output this metadata is printed above the table on stdout. For JSON and CSV output it is printed to stderr so stdout remains valid JSON/CSV. Suppress it with `--no-info`.

In table output, SQL `NULL` values are rendered as:

```text
<null>
```

# Parameters

SQL files can use SQLite named parameters:

```sql
limit :n
```

Pass values with repeatable `--param` options:

```bash
uv run python queries/run_sql.py \
  --param n=20 \
  DB.sqlite \
  queries/annotation-store/top_sctids.sql
```

The runner lightly coerces parameter values:

| Text | Bound value |
|---|---|
| `20` | integer |
| `3.14` | float |
| `true`, `yes`, `on` | boolean true |
| `false`, `no`, `off` | boolean false |
| `null`, `none` | SQL NULL |
| other values | string |

# Parameter defaults

SQL files can define default named parameters in comments:

```sql
-- @param n=50
```

CLI values override defaults.

Multiple defaults are allowed:

```sql
-- @param semantic_tag=
-- @param semantic_tag_part=
-- @param partial_binning=false
-- @param n=20
```

# Python post-processing directives

The query runner can apply optional post-processing requested by SQL comments.

## Sort by parameter

A SQL file can request Python-side sorting with:

```sql
-- @sort_by order
```

The named parameter contains either a known alias or a comma-separated column list. Prefix a column with `-` for descending order:

```bash
--param order=count
--param order=semantic_tag
--param order=semantic_tag,covered_text_bin
--param order=-annotation_count,semantic_tag
```

Known aliases include `count`, `semantic_tag`, `covered_text`, `covered_text_bin`, `semantic_tag_covered_text`, `sctid`, and `fsn`. Unknown columns in a sort specification are ignored.

## Partial binning

Shorthand:

```sql
-- @partial_bin covered_text_bin
```

Default semantics:

| Setting | Default |
|---|---|
| enable parameter | `partial_binning` |
| variants column | `covered_text_variants` |
| count column | `annotation_count` |
| group columns | all result columns except bin/variants/count |
| match mode | `boundary` |

Boundary match mode bins longer strings under shorter contained strings only when the shorter string appears at word-like boundaries. This is intended to avoid overly broad merges where a short token merely appears inside an unrelated longer word, while still allowing common separator/punctuation cases such as hyphenated forms, whitespace-separated forms, or symbols after a token.

Full directive form is available for unusual result shapes:

```sql
-- @partial_bin column=covered_text_bin group_by=semantic_tag,site variants_column=covered_text_variants count_column=annotation_count match=boundary
```

The older permissive substring mode can be requested explicitly, but should be used carefully:

```sql
-- @partial_bin column=covered_text_bin match=substring
```

## Post limit

When Python-side post-processing may change counts/order, use post-limit instead of SQL `limit`:

```sql
-- @post_limit n
```

This applies the `n` limit after Python post-processing.

# Available queries

## `semantic_tag_counts.sql`

Counts annotation occurrences by semantic tag:

```bash
uv run python queries/run_sql.py \
  DB.sqlite \
  queries/annotation-store/semantic_tag_counts.sql
```

Parameters:

| Parameter | Default | Required | Description |
|---|---:|---:|---|
| `order` | `count` | no | Sort mode. Use `count` for annotation count descending or `semantic_tag` for alphabetical semantic-tag order. Custom column lists such as `semantic_tag,-annotation_count` are also accepted. |

Main columns:

- `semantic_tag`
- `annotation_count`

## `top_sctids.sql`

Reports the most frequent SCTIDs, with default `n=50`:

```bash
uv run python queries/run_sql.py \
  DB.sqlite \
  queries/annotation-store/top_sctids.sql
```

Override the limit:

```bash
uv run python queries/run_sql.py \
  --param n=20 \
  DB.sqlite \
  queries/annotation-store/top_sctids.sql
```

Parameters:

| Parameter | Default | Required | Description |
|---|---:|---:|---|
| `n` | `50` | no | Maximum number of SCTID rows to return. |

Main columns:

- `sctid`
- `semantic_tag`
- `fsn`
- `annotation_count`

## `texts_for_st.sql`

Reports covered-text bins for a semantic tag. It supports either exact semantic-tag lookup or partial semantic-tag lookup.

Exact semantic tag:

```bash
uv run python queries/run_sql.py \
  --param semantic_tag="medicinal product" \
  DB.sqlite \
  queries/annotation-store/texts_for_st.sql
```

Partial semantic-tag lookup:

```bash
uv run python queries/run_sql.py \
  --param semantic_tag_part=medicinal \
  DB.sqlite \
  queries/annotation-store/texts_for_st.sql
```

Enable Python-side partial covered-text binning:

```bash
uv run python queries/run_sql.py \
  --param semantic_tag="medicinal product" \
  --param partial_binning=true \
  DB.sqlite \
  queries/annotation-store/texts_for_st.sql
```

Parameters:

| Parameter | Default | Required | Description |
|---|---:|---:|---|
| `semantic_tag` | empty string | no | Exact case-insensitive semantic-tag filter. If non-empty, this takes precedence over `semantic_tag_part`. |
| `semantic_tag_part` | empty string | no | Case-insensitive substring filter used when `semantic_tag` is empty. |
| `partial_binning` | `false` | no | When true, applies Python-side boundary-aware containment binning to `covered_text_bin`. |
| `bin_by_sctid` | `false` | no | When true, keeps covered-text bins separated by SCTID/FSN. When false, `sctid` and `fsn` output columns are null and bins are across the selected semantic tag(s). |
| `order` | `count` | no | Sort mode. Use `count`, `semantic_tag`, `covered_text`, `semantic_tag_covered_text`, `sctid`, `fsn`, or a custom column list such as `semantic_tag,covered_text_bin,-annotation_count`. |
| `n` | `20` | no | Maximum number of rows after optional Python post-processing. |

Main columns:

- `semantic_tag`
- `sctid`: populated only when `bin_by_sctid=true`;
- `fsn`: populated only when `bin_by_sctid=true`;
- `covered_text_bin`: lowercase bin key;
- `covered_text_variants`: distinct original covered texts in the bin;
- `annotation_count`: total occurrences in the bin.

Partial binning is intentionally conservative. It handles textual containment, not synonymy or alias resolution. Non-containment relationships require concept-aware grouping, an alias table, or review-oriented fuzzy matching.

## `fsn_for_text.sql`

Reports FSN/SCTID counts for a covered text. It supports either exact covered-text lookup or partial covered-text lookup. This is the preferred concept-oriented view for answering “what was this text annotated as?”.

Exact covered text:

```bash
uv run python queries/run_sql.py \
  --param covered_text="ASS" \
  DB.sqlite \
  queries/annotation-store/fsn_for_text.sql
```

Partial covered-text lookup:

```bash
uv run python queries/run_sql.py \
  --param covered_text_part=ass \
  DB.sqlite \
  queries/annotation-store/fsn_for_text.sql
```

Parameters:

| Parameter | Default | Required | Description |
|---|---:|---:|---|
| `covered_text` | empty string | no | Exact case-insensitive covered-text filter. If non-empty, this takes precedence over `covered_text_part`. |
| `covered_text_part` | empty string | no | Case-insensitive substring filter used when `covered_text` is empty. |
| `order` | `count` | no | Sort mode. Use `count`, `fsn`, `semantic_tag`, `sctid`, or a custom column list such as `fsn,-annotation_count`. |
| `n` | `20` | no | Maximum number of rows after Python-side sorting. |

Main columns:

- `sctid`;
- `fsn`;
- `semantic_tag`;
- `annotation_count`: total occurrences matching the selected covered text.

## `text_variants_for_text.sql`

Reports actual covered-text variants matching a covered-text search, grouped by lowercase covered text and semantic tag. This is useful after `fsn_for_text.sql` shows that a searched text spans multiple semantic tags or FSNs.

Partial covered-text lookup:

```bash
uv run python queries/run_sql.py \
  --param covered_text_part=folfox \
  DB.sqlite \
  queries/annotation-store/text_variants_for_text.sql
```

Exact covered-text lookup:

```bash
uv run python queries/run_sql.py \
  --param covered_text="FOLFOX" \
  DB.sqlite \
  queries/annotation-store/text_variants_for_text.sql
```

Parameters:

| Parameter | Default | Required | Description |
|---|---:|---:|---|
| `covered_text` | empty string | no | Exact case-insensitive covered-text filter. If non-empty, this takes precedence over `covered_text_part`. |
| `covered_text_part` | empty string | no | Case-insensitive substring filter used when `covered_text` is empty. |
| `order` | `count` | no | Sort mode. Use `count`, `semantic_tag`, `covered_text`, or a custom column list. |
| `n` | `50` | no | Maximum number of rows after Python-side sorting. |

Main columns:

- `covered_text_bin`: lowercase covered-text bin;
- `covered_text_variants`: distinct original covered texts in the bin;
- `semantic_tag`;
- `annotation_count`.

# Related concepts

- [Annotation store SQLite schema](/snomed-post-processing/data/annotation-store-sqlite.md)
- [Build and query annotation store](/snomed-post-processing/workflows/annotation-store.md)
- [CLI commands](/snomed-post-processing/interfaces/cli.md)
