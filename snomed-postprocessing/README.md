# SNOMED Postprocessing

SNOMED Postprocessing checks SNOMED CT annotations in INCEpTION/UIMA exports against a materialized SNOMED HDF5 file. In policy mode, annotations are checked against whitelist/blacklist policy views. The tool reports non-whitelisted or blacklisted annotations, can generate sanitization suggestions, and can apply reviewed replacement/delete decisions to a copied project ZIP.

The project can be used from the command line or through a Streamlit GUI.  

The usage of this program requires a SNOMED CT policy file (``hdf5`` format). You can either create it yourself with a SNOMED CT release archive (``zip``)
or with a SNOWSTORM instance - see below for instructions.  
For the GeMTeX project there is a working file here:  
[Technik/Methodik > Technisches Dashboard > SNOMED CT Semantic Tag / Dashboard](https://confluence.imi.med.fau.de/download/attachments/317216732/gemtex_snomedct_codes_release20260401_policy20240401.hdf5?version=1&modificationDate=1788504062723&api=v2)

## Main workflows

### 1. Policy check / critical document logging

Input:
- an INCEpTION project export ZIP, or an INCEpTION project fetched through the API
- a whitelist/blacklist HDF5 file

Supported CAS formats in the export are JSON CAS and XMI. Java serialized CAS (`.ser`) exports are not supported. In INCEpTION, a suitable JSON CAS backup can be created via:

```text
Export > Export backup archive > Secondary format > UIMA CAS JSON 0.4.0
```

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

### 3. Sanitization suggestions and reviewed export

Input:
- a sanitization-ready HDF5 file
- a `critical_findings_*.json` file from the check step

Output:
- Markdown/JSON suggestion reports based on historical associations, optional ancestor fallback, and optional semantic BM25 fallback
- reviewed decisions JSON
- a copied, sanitized INCEpTION ZIP with reviewed replacements and deletions applied

Suggestion generation supports two target views and several fallback levels:

| Target view | Candidate rule |
|---|---|
| policy | active AND whitelisted AND not blacklisted |
| release | active in the selected release; optional blacklist exclusions |

| Suggestion source | Purpose |
|---|---|
| historical associations | preferred replacement source for inactive/outdated concepts |
| ancestor fallback | optional broader active ancestor when historical targets are unavailable |
| semantic BM25 | optional lexical fallback over SNOMED FSNs |
| processed SNOGIT cache | optional extra BM25 evidence from SNOGIT terms |

BM25 and SNOGIT are suggestion-only evidence. Candidates must still pass the selected target-view gates. The original INCEpTION ZIP is not modified.

## CLI usage

The installed console commands are:

```bash
log-critical-documents
create-concepts-dump
summarize-hdf5
suggest-sanitization
build-snogit-cache
build-inception-shell-project
build-inception-upload-artifacts
deploy-inception-sanitized-project
apply-decisions-to-inception
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

Docker CLI example with local files mounted into `/app/data`:

```bash
docker run \
  --volume ./data:/app/data \
  --rm \
  ghcr.io/medizininformatik-initiative/gemtex/snomed-postprocessing:2.0.1 \
  log-critical-documents \
  --lists-path /app/data/gemtex_snomedct_codes.hdf5 \
  /app/data/inception-export.zip
```

The Docker entrypoint adds `--forbid-prompt` for `log-critical-documents`, so interactive annotator selection is not available in this Docker CLI mode.

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
For the following three commands:
if you don't supply a SNOMED CT code as starting point as the positional argument,
it defaults to the SNOMED CT root code (``138875005``)


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

Create both blacklist and whitelist policy in one run:

```bash
uv run create-concepts-dump \
  --zip /path/to/SnomedCT_Release_INT.zip \
  --output /path/to/gemtex_snomedct_codes.hdf5 \
  --policy-date YYYYMMDD \
  --include-ancestors \
  --dump-mode version \
  --filter-list /path/to/blacklist_filter_tags.txt
```

### Create an HDF5 policy from Snowstorm
This will take a very long time, since it queries the API repeatedly ofr nearly all codes.
If possible at all, please use a RELEASE zip (see above).
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

Policy-view suggestions use the HDF5 whitelist/blacklist policy:

```bash
uv run suggest-sanitization \
  --lists-path /path/to/gemtex_snomedct_codes.hdf5 \
  --critical-findings /path/to/critical_findings.json \
  --output /path/to/sanitization_suggestions.md
```

Release-view suggestions ignore the whitelist and allow any active concept by default:

```bash
uv run suggest-sanitization \
  --lists-path /path/to/gemtex_snomedct_codes.hdf5 \
  --critical-findings /path/to/critical_findings.json \
  --output /path/to/sanitization_suggestions.md \
  --target-view release
```

Release-view blacklist exclusions are opt-in:

| Options | Effective release-view rule |
|---|---|
| none | active concept |
| `--enforce-embedded-blacklist` | active AND not in embedded HDF5 blacklist |
| `--custom-blacklist PATH` | active AND not in custom blacklist |
| both | active AND not in either blacklist |

A custom blacklist file uses the same format as RF2 blacklist ingestion: numeric SCTID lines exclude the concept and descendants; non-numeric lines exclude by FSN semantic tag.

Optional semantic BM25 fallback can be combined with either target view. It ranks SNOMED FSNs lexically and only keeps candidates that pass the selected policy/release gates:

```bash
uv run suggest-sanitization \
  --lists-path /path/to/gemtex_snomedct_codes.hdf5 \
  --critical-findings /path/to/critical_findings.json \
  --output /path/to/sanitization_suggestions.md \
  --semantic-bm25-fallback
```

To use SNOGIT terms as additional BM25 evidence, first build a processed SNOGIT cache from a SNOGIT ZIP, or from a single SNOGIT `.dat` file, and the same main HDF5:

```bash
uv run build-snogit-cache \
  --hdf5 /path/to/gemtex_snomedct_codes.hdf5 \
  --snogit-source /path/to/SNOGIT.zip \
  --output /path/to/processed_snogit_cache.hdf5
```

For backwards compatibility, `--snogit-zip` is still accepted as an alias for `--snogit-source`. By default, cache creation uses the newest general `SNOGIT_*.dat` member in ZIP inputs. To include specific `.dat` members from a ZIP instead, pass `--snogit-member` one or more times, for example to add ELGA or Latin term files. If you already have just one `.dat` file, pass it directly via `--snogit-source`; no member selection is needed.

Then pass that processed cache during suggestion generation:

```bash
uv run suggest-sanitization \
  --lists-path /path/to/gemtex_snomedct_codes.hdf5 \
  --critical-findings /path/to/critical_findings.json \
  --output /path/to/sanitization_suggestions.md \
  --semantic-bm25-fallback \
  --use-snogit-cache /path/to/processed_snogit_cache.hdf5
```

`suggest-sanitization` does not parse raw SNOGIT ZIP/`.dat` files or create caches; use `build-snogit-cache` for that step.

### Apply reviewed decisions and deploy to INCEpTION

The recommended deployment workflow is the one-step command:

```bash
uv run apply-decisions-to-inception \
  --source-project /path/to/original-inception-project.zip \
  --decisions /path/to/reviewed_sanitization_decisions.json \
  --output-dir /path/to/sanitized-inception-output
```

This is a dry-run/offline preparation by default. It does not contact or modify INCEpTION unless connection options and `--apply` are supplied.

It creates:

```text
/path/to/sanitized-inception-output/
  <source-name>-sanitized-shell.zip
  inception-upload-artifacts/
    *.json / *.xmi
    inception-upload-artifacts-report.json
  inception-sanitized-deployment-report.json
  inception-apply-decisions-upload-report.json
```

The original project ZIP is not modified. Reviewed decisions are applied to the original project ZIP, producing flattened sanitized CAS upload artifacts. These artifacts are repaired for INCEpTION remote-upload compatibility, including complete non-overlapping `Sentence` coverage of non-whitespace text so the sentence-based editor can load them.

To actually import the shell project and upload the sanitized CAS artifacts, pass INCEpTION credentials and explicit `--apply`:

```bash
export INCEPTION_PASSWORD='...'
uv run apply-decisions-to-inception \
  --source-project /path/to/original-inception-project.zip \
  --decisions /path/to/reviewed_sanitization_decisions.json \
  --output-dir /path/to/sanitized-inception-output \
  --inception-url http://localhost:8080 \
  --username USER \
  --password-env INCEPTION_PASSWORD \
  --annotation-user USER \
  --apply
```

Use `--check-connection` without `--apply` to authenticate and verify that the INCEpTION instance is reachable while still avoiding remote writes.  
Instead of `--password-env` you can use plain `--password` without an environment file, as well.

The lower-level commands are also available if you want to run the workflow step by step:

```bash
uv run build-inception-shell-project \
  --source-project /path/to/original-inception-project.zip \
  --output-project-shell /path/to/sanitized-shell.zip

uv run build-inception-upload-artifacts \
  --source-project /path/to/original-inception-project.zip \
  --decisions /path/to/reviewed_sanitization_decisions.json \
  --output-dir /path/to/inception-upload-artifacts

uv run deploy-inception-sanitized-project \
  --shell-project /path/to/sanitized-shell.zip \
  --upload-artifacts-dir /path/to/inception-upload-artifacts
```

`deploy-inception-sanitized-project` is also dry-run by default and requires `--apply` for remote writes.

## GUI usage

Start the Streamlit app locally:

```bash
uv run streamlit run src/snomed_post_processing/gui/app.py
```

With Docker, the GUI can be started as:

```bash
docker run --rm -p HOST_PORT:8501 \
  ghcr.io/medizininformatik-initiative/gemtex/snomed-postprocessing:2.0.1 \
  start-gui
```

Convenience scripts are included for the common Docker commands:

```bash
bash log-inception-docs.sh inception-export.zip
bash start-gui.sh 8501
```

If you want to run them as `./log-inception-docs.sh` or `./start-gui.sh`, mark them executable first with `chmod +x`. The logging script assumes files are in `./data` and relies on the container-visible `/app/data` paths.

The GUI has three tabs:

1. **Check whitelist/blacklist**  
   Upload an INCEpTION ZIP or fetch one through the INCEpTION API, upload the HDF5 policy file, optionally select annotators and annotation layers, then run the policy check. Reports and JSON artifacts can be downloaded.

2. **Sanitization suggestions**  
   Use the `CriticalFindings` JSON from the current session or upload one. Select policy or active-release target view, configure optional embedded/custom blacklist handling for release view, choose fallback methods, optionally select/create a processed SNOGIT cache, then download suggestion reports.

3. **Review & apply / Sanitization run**  
   Review suggestions, save/load reviewed decisions, and either:
   - run the legacy local sanitization ZIP export, or
   - run the INCEpTION deployment pipeline.

   The INCEpTION deployment section mirrors `apply-decisions-to-inception`: it builds a schema shell ZIP, builds repaired flattened upload artifacts, and then performs a dry-run or, only if explicitly selected, uploads to INCEpTION. Download buttons are provided for the shell ZIP, repaired upload artifacts ZIP, and pipeline report.

## Notes

- The policy check can take a while on large projects or large policy files.
- A default HDF5 path is attempted when `--lists-path` is omitted, but providing the policy file explicitly is recommended.
- Use masked markdown reports when sharing results outside a protected environment.
