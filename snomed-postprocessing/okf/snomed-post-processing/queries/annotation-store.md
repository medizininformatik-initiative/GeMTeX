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

Main columns:

- `semantic_tag`
- `covered_text_bin`: lowercase bin key;
- `covered_text_variants`: distinct original covered texts in the bin;
- `annotation_count`: total occurrences in the bin.

Partial binning is intentionally conservative. It handles textual containment, not synonymy or alias resolution. Non-containment relationships require concept-aware grouping, an alias table, or review-oriented fuzzy matching.

# Related concepts

- [Annotation store SQLite schema](/snomed-post-processing/data/annotation-store-sqlite.md)
- [Build and query annotation store](/snomed-post-processing/workflows/annotation-store.md)
- [CLI commands](/snomed-post-processing/interfaces/cli.md)
