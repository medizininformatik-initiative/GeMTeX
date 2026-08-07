# SNOMED Postprocessing

SNOMED Postprocessing checks SNOMED CT annotations in INCEpTION/UIMA exports against an HDF5 policy file. The policy contains whitelist and blacklist views. The tool reports annotations that are either not whitelisted or explicitly blacklisted, and can also generate sanitization suggestions for outdated/inactive concepts.

The project can be used from the command line or through a Streamlit GUI.

## Main workflows

### 1. Policy check / critical document logging

Input:
- an INCEpTION project export ZIP, or an INCEpTION project fetched through the API
- a whitelist/blacklist HDF5 file

Supported CAS formats in the export are JSON CAS and XMI. Java serialized CAS (`.ser`) exports are not supported.

Output:
- `critical_documents_<date>.md`: markdown report with critical documents and findings
- `critical_documents_<date>.masked.md`: privacy-friendlier report with masked annotator/document names
- `critical_documents_<date>.json`: JSON dump of found concepts and offsets
- `critical_findings_<date>.json`: structured findings artifact used by the sanitization workflow

By default, findings are checked on the `gemtex.Concept` annotation layer. Faulty findings overlapping `webanno.custom.No_Human` are ignored for the critical-document count and reported separately. Both layer choices are configurable.

### 2. HDF5 policy creation

The HDF5 policy file can be created in two modes:

- **RF2 ZIP mode**: ingest a SNOMED CT RF2 release ZIP directly.
- **Snowstorm mode**: query concepts from a running Snowstorm instance.

The resulting HDF5 can contain:
- compact whitelist/blacklist policy views
- full concept metadata
- semantic tags
- historical associations
- optional ancestor data

Historical associations are needed for sanitization suggestions.

### 3. Sanitization suggestions

Input:
- a sanitization-ready HDF5 policy file
- a `critical_findings_*.json` file from the policy check

Output:
- a markdown report with replacement suggestions, mainly based on SNOMED CT historical associations
- optional BM25 fallback suggestions for unresolved whitelist findings

This step only creates suggestions. Applying reviewed suggestions back to CAS files is planned but not implemented yet.

## CLI usage

The installed console commands are:

```bash
log-critical-documents
create-concepts-dump
summarize-hdf5
suggest-sanitization
list-branches
```

Use `--help` on any command for the complete option list.

### Run a local policy check

```bash
uv run log-critical-documents \
  --lists-path /path/to/gemtex_snomedct_codes.hdf5 \
  /path/to/inception-export.zip
```

Non-interactive use, for example in Docker or CI:

```bash
uv run log-critical-documents \
  --forbid-prompt \
  --lists-path /path/to/gemtex_snomedct_codes.hdf5 \
  /path/to/inception-export.zip
```

### Run a policy check through the INCEpTION API

The INCEpTION user must have the `REMOTE` role. In this mode, `PROCESS_PATH` is a temporary export directory.

```bash
uv run log-critical-documents \
  --lists-path /path/to/gemtex_snomedct_codes.hdf5 \
  --ip INCEPTION_HOST \
  --port 8080 \
  --inception-username USER \
  --inception-password PASSWORD \
  --inception-project PROJECT_URL_SLUG \
  /path/to/temp/export-dir
```

### Configure checked and ignored annotation layers

```bash
uv run log-critical-documents \
  --lists-path /path/to/gemtex_snomedct_codes.hdf5 \
  --annotation-type gemtex.Concept \
  --annotation-type another.Layer \
  --ignore-overlap-type webanno.custom.No_Human \
  --ignore-overlap-mode overlap \
  /path/to/inception-export.zip
```

Supported ignore modes are `overlap`, `covered-by`, `contains`, and `exact`.

### Create an HDF5 policy from an RF2 ZIP

```bash
uv run create-concepts-dump \
  --zip /path/to/SnomedCT_Release_INT.zip \
  --output /path/to/gemtex_snomedct_codes.hdf5 \
  --policy-date YYYYMMDD \
  --include-ancestors \
  --dump-mode version
```

Create a blacklist policy by semantic tags or root codes:

```bash
uv run create-concepts-dump \
  --zip /path/to/SnomedCT_Release_INT.zip \
  --output /path/to/gemtex_snomedct_codes.hdf5 \
  --policy-date YYYYMMDD \
  --dump-mode semantic \
  --filter-list /path/to/blacklist_filter_tags.txt
```

### Create an HDF5 policy from Snowstorm

```bash
uv run create-concepts-dump \
  --ip SNOWSTORM_HOST \
  --port 8080 \
  --branch MAIN/YYYY-MM-DD \
  --dump-mode version
```

For semantic/blacklist dumps, provide one or more `--filter-list` values or a filter-list file.

### Inspect an HDF5 file

```bash
uv run summarize-hdf5 /path/to/gemtex_snomedct_codes.hdf5
uv run summarize-hdf5 --markdown /path/to/gemtex_snomedct_codes.hdf5
```

### Generate sanitization suggestions

```bash
uv run suggest-sanitization \
  --lists-path /path/to/gemtex_snomedct_codes.hdf5 \
  --critical-findings /path/to/critical_findings.json \
  --output /path/to/sanitization_suggestions.md
```

Optional BM25 fallback:

```bash
uv run suggest-sanitization \
  --lists-path /path/to/gemtex_snomedct_codes.hdf5 \
  --critical-findings /path/to/critical_findings.json \
  --output /path/to/sanitization_suggestions.md \
  --semantic-bm25-fallback
```

## GUI usage

Start the Streamlit app locally:

```bash
uv run streamlit run src/snomed_post_processing/gui/app.py
```

With Docker, the existing image can be started as described in the original project usage:

```bash
docker run --rm -p HOST_PORT:8501 \
  ghcr.io/medizininformatik-initiative/gemtex/snomed-postprocessing:1.2.5 \
  start-gui
```

The GUI has three tabs:

1. **Check whitelist/blacklist**  
   Upload an INCEpTION ZIP or fetch one through the INCEpTION API, upload the HDF5 policy file, optionally select annotators and annotation layers, then run the policy check. Reports and JSON artifacts can be downloaded.

2. **Sanitization suggestions**  
   Use the `CriticalFindings` JSON from the current session or upload one. Configure allowed historical association types and optional BM25 fallback, then download the suggestions report.

3. **Sanitization run**  
   Placeholder for applying reviewed suggestions back to CAS files. This workflow is currently disabled.

## Notes

- The policy check can take a while on large projects or large policy files.
- A default HDF5 path is attempted when `--lists-path` is omitted, but providing the policy file explicitly is recommended.
- Use masked markdown reports when sharing results outside a protected environment.
