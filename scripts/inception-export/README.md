# INCEpTION Export

Export an INCEpTION project into one ZIP per document/annotator pair.

Each output ZIP contains only:

- `TypeSystem.xml`
- one annotation `.xmi`

Output files are named:

```text
DOCUMENT_NAME-ANNOTATOR_NAME.zip
```

With anonymization enabled:

```text
DOCUMENT_NAME-annotator001.zip
```

## Setup

```bash
uv sync
```

## Usage

Interactive project and annotator selection is the default,
and so the minimal command is:

```bash
uv run ./inception-export.py \
  --host https://inception.example.org \
  --username USER
```

If `--password` is omitted, `INCEPTION_PASSWORD` is used if set; otherwise a password prompt is shown.

## Output directory

If `--output-dir` is omitted, files are written to:

```text
./out/PROJECT_NAME/
```

If `--output-dir` is given, files are written to:

```text
OUTPUT_DIR/PROJECT_NAME/
```

Example:

```bash
uv run ./inception-export.py \
  --host https://inception.example.org \
  --username USER \
  --output-dir ./exports
```

writes to:

```text
./exports/PROJECT_NAME/
```

## Non-interactive options

Select a project directly:

```bash
--project PROJECT_ID_OR_NAME
```

Include only specific annotators:

```bash
--include-annotator alice --include-annotator bob
```

Exclude annotators:

```bash
--exclude-annotator test_user
```

List projects:

```bash
--list-projects
```

List annotators for a selected project:

```bash
--project PROJECT_ID_OR_NAME --list-annotators
```

## Anonymization

```bash
uv run ./inception-export.py \
  --host https://inception.example.org \
  --username USER \
  --anonymize
```

The mapping is written to:

```text
OUTPUT_DIR/PROJECT_NAME/annotator-mapping.csv
```

or to a custom path via:

```bash
--mapping-file ./annotator-mapping.csv
```

## Other useful flags

```bash
--overwrite             # allow replacing existing output ZIPs
--keep-project-export   # keep the full downloaded project export ZIP
--verify-ssl true       # enables SSL verification
--zip-like-xmi-name     # use the same name for the XMI file as the ZIP (else only document name)
```
