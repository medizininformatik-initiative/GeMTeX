# SNOMED Postprocessing — Working Notes

This document summarizes how the `snomed-postprocessing` CLI/GUI works. It is intended as an implementation reference for future maintenance and improvements.

## 1. Purpose

The project post-processes INCEpTION project exports containing SNOMED CT annotations. It identifies **critical documents** by comparing each annotated SNOMED CT code against SNOMED CT filter lists stored in an HDF5 file:

- **Whitelist**: a code is critical if it is **not present** in the whitelist.
- **Blacklist**: a code is critical if it **is present** in the blacklist.

It produces:

- Markdown report with critical documents and concepts.
- Masked Markdown report where annotator/document names are replaced with random names.
- JSON dump of critical concepts and offsets.

The project also contains commands to create whitelist/blacklist HDF5 dumps from a Snowstorm server.

## 2. Entry Points

Defined in `pyproject.toml`:

| Command | Python function | Purpose |
|---|---|---|
| `log-critical-documents` | `snomed_post_processing.main:log_documents` | Process an INCEpTION ZIP/local or remote project and create reports. |
| `create-concepts-dump` | `snomed_post_processing.main:create_concept_id_dump` | Create/update HDF5 whitelist/blacklist dumps from Snowstorm. |
| `list-branches` | `snomed_post_processing.main:list_branches` | List available Snowstorm branches. |
| `program-entry` | `snomed_post_processing.main:help_me` | Fallback/help command. |

The GUI is launched directly with Streamlit:

```bash
uv run streamlit run src/snomed_post_processing/streamlit_app.py
```

Docker uses `entrypoint.sh` as a command dispatcher.

## 3. Main Modules

```text
src/snomed_post_processing/
├── main.py                    # Click CLI commands
├── streamlit_app.py           # Streamlit GUI
├── uima_processing/__init__.py # INCEpTION ZIP/CAS parsing, filtering, report writing
├── snowstorm_funcs/__init__.py # Snowstorm API traversal helpers
└── utils/__init__.py          # Shared models, enums, HDF5 helpers, INCEpTION API helper
```

## 4. CLI Workflow: `log-critical-documents`

Source: `src/snomed_post_processing/main.py`

### Inputs

Required:

- `process_path`: either:
  - path to a local INCEpTION project ZIP, or
  - temporary export folder when using INCEpTION API mode.

Optional:

- `--lists-path`: HDF5 file containing whitelist/blacklist groups.
- `--ip`, `--port`, `--use-secure_protocol`: INCEpTION host options.
- `--inception-username`, `--inception-password`, `--inception-project`: enable API export mode.
- `--keep-export`: keep downloaded temporary project ZIP.
- `--omit-dump`: skip JSON dump creation.
- `--forbid-prompt`: disable interactive annotator selection.

### Processing steps

1. Configure logging.
2. Build INCEpTION host URL.
3. Resolve project ZIP via `get_project_zip()`:
   - local ZIP if credentials are missing;
   - remote export via Pycaprio if credentials and project are provided.
4. Resolve HDF5 lists path:
   - use provided valid `--lists-path`, or
   - fallback to `data/gemtex_snomedct_codes_2024-04-01.hdf5`.
5. Check annotators with `get_annotator_names()`.
6. If prompts are allowed, ask user which annotators to include via `prompt_for_names()`.
7. Process project ZIP with `process_inception_zip()`.
8. Write:
   - `critical_documents_<date>_<time>.md`
   - `critical_documents_<date>_<time>.masked.md`
   - `critical_documents_<date>_<time>.json`
9. Optionally delete temporary API export.
10. Log final critical document count.

## 5. GUI Workflow

Source: `src/snomed_post_processing/streamlit_app.py`

The GUI wraps the same processing functions as the CLI.

### Input modes

#### Local ZIP mode

- User uploads INCEpTION ZIP.
- User uploads HDF5 whitelist/blacklist file.

#### INCEpTION API mode

- User enters API URL, username, and password.
- GUI calls `get_project_zip(..., project_name=None)` to list projects.
- User selects a project.
- GUI exports selected project to a temporary ZIP.

### GUI processing steps

1. Save uploaded/project ZIP to a temporary path.
2. Optionally load annotator names from ZIP.
3. Allow annotator multiselect.
4. Save uploaded HDF5 file to temporary path.
5. Call `generate_report()`:
   - calls `process_inception_zip()`;
   - calls `create_log_from_results()`;
   - writes Markdown, masked Markdown, and JSON output.
6. Display critical document count.
7. Provide download buttons for all outputs.
8. Show Markdown preview.

## 6. INCEpTION ZIP Processing

Source: `src/snomed_post_processing/uima_processing/__init__.py`

### Expected ZIP structure

The processor expects `exportedproject.json` and source documents with CAS files under INCEpTION-style folders such as:

```text
curation/<document>/
annotation/<document>/
curation_ser/<document>/
annotation_ser/<document>/
```

Supported actual processing is JSON CAS through `cassis.load_cas_from_json()`.

`.ser` files are detected and rejected/skipped because Java Serialized CAS is unsupported by `dkpro-cassis` here.

### File selection logic

`_yield_matching_files()`:

1. Reads source documents from `exportedproject.json`.
2. Finds matching CAS files in curation/annotation folders.
3. If several CAS files exist for one document, filters out `INITIAL_CAS.*` files.
4. Yields document name and matching CAS paths.

### Annotation extraction

`get_annotations_from_document()` extracts annotations of type:

```python
gemtex.Concept
```

For each annotation it stores:

- SNOMED code from `annotation.id`, with `http://snomed.info/id/` removed.
- `(begin, end)` offsets.
- covered text.

Missing/empty/null IDs are represented as `nan`.

The extracted data is stored in `DocumentAnnotations`:

```python
@dataclass
class DocumentAnnotations:
    snomed_codes: np.ndarray
    offsets: np.ndarray
    text: np.ndarray
    length: int
```

Project-level result structure:

```python
TemporaryCorpus
└── annotators: dict[str, TemporaryContainer]
    └── documents: dict[str, DocumentAnnotations]
```

## 7. Filtering and Report Generation

Source: `create_log_from_results()` and `analyze_documents()`.

Policy checking now produces structured `CriticalFinding` records first. Markdown, masked Markdown, final count tables, and the JSON dump are rendered from those findings at the end of the report generation step. This keeps reporting behavior intact while providing a stable input object for future sanitization.

### HDF5 layout expected

The processing expects groups like:

```text
/whitelist/0/codes
/whitelist/0/fsn
/blacklist/0/codes
/blacklist/0/fsn
```

Only revision group `0` is currently read during report generation.

### Filter order

Policy findings are collected in this order:

1. Whitelist pass.
2. Blacklist pass.

Reports are then rendered from the collected `CriticalFinding` records:

1. Whitelist findings.
2. Blacklist findings.
3. Ignored faulty concepts.
4. Final count tables.

### Whitelist logic

For each annotation code:

```text
critical = code is not in whitelist
```

Additional behavior:

- `nan` codes are normally ignored by `nan_filter`.
- Numeric covered text without a valid code is filtered out in whitelist mode to avoid false positives for numeric spans.

### Blacklist logic

For each annotation code:

```text
critical = code is in blacklist
```

For blacklisted codes, the report also includes the FSN loaded from the HDF5 mapping array.

### Masking behavior

Masked reports use `randomname` to replace:

- annotator names with `annotator-<random-name>`;
- document names with `document-<random-name>`.

Covered text, SNOMED IDs, offsets, and FSNs are not masked.

### JSON dump behavior

The JSON dump stores critical concept codes with offsets and, when available, FSN:

```json
{
  "123456": {
    "offset": [[10, 20]],
    "fsn": "Example concept (finding)"
  }
}
```

Note: offsets are grouped by code across the processing run.

## 8. HDF5 Dump Creation: `create-concepts-dump`

Source: `src/snomed_post_processing/main.py`, `snowstorm_funcs`, and `utils`.

This command connects to a Snowstorm server and recursively traverses SNOMED CT concepts to create HDF5 whitelist/blacklist datasets.

### Snowstorm helpers

- `build_endpoint()`: creates an `scttsrapy.EndpointBuilder`.
- `get_branches()`: fetches available Snowstorm branches.
- `get_root_code()`: fetches the configured root concept.
- `dump_concept_ids()`: recursively walks child concepts and collects concept IDs and FSNs.

### Dump modes

| Mode | Enum | Meaning |
|---|---|---|
| `version` | `DumpMode.VERSION` | Create whitelist-like dump of concepts under root. |
| `semantic` | `DumpMode.SEMANTIC` | Create blacklist-like dump filtered by semantic tags or explicit code roots. |

### Filter list behavior

`--filter-list` can be:

- repeated direct values;
- a file containing one value per line.

Values are split into:

- numeric concept IDs;
- semantic tags.

For semantic mode:

- if a concept ID is listed, its whole subtree is included;
- if a semantic tag is listed, concepts whose FSN contains that semantic tag are included.

### HDF5 writing

`dump_codes_to_hdf5()` writes datasets under `whitelist` or `blacklist` groups.

Behavior:

- Creates a numbered child group such as `0`.
- Stores sorted codes in `codes`.
- Stores corresponding FSNs in `fsn`.
- `force_overwrite=True` deletes and recreates an existing list group.
- Revision support is noted but not implemented; existing datasets are skipped unless forced.

## 9. Docker Behavior

### Dockerfile

- Base image: `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`.
- Installs Git because `scttsrapy` is pulled from Git.
- Uses `uv sync --locked`.
- Adds `/app/.venv/bin` to `PATH`.
- Uses `entrypoint.sh` as dispatcher.

### `entrypoint.sh`

- No args: show help.
- `start-gui`: runs Streamlit GUI.
- `log-critical-documents`: appends `--forbid-prompt` automatically, because Docker is non-interactive.
- Other commands are forwarded unchanged.

### Convenience scripts

- `start-gui.sh [PORT] [VERSION]`
- `log-inception-docs.sh ZIP_NAME [VERSION]`

`log-inception-docs.sh` mounts local `./data` to `/app/data`.

## 10. Important Data/Config Files

| Path | Purpose |
|---|---|
| `config/blacklist_filter_tags.txt` | Default/example blacklist semantic tags and concept roots used when creating a blacklist dump. |
| `data/` | Expected location for large HDF5 list files and local ZIPs in Docker workflows. |
| `test/test-export.zip` | Sample INCEpTION export. |

## 11. Current Assumptions and Limitations

- JSON CAS is the practical supported format; `.ser` is unsupported.
- XMI is mentioned in some messages/path filters, but loading currently calls `cassis.load_cas_from_json()`.
- Report generation reads only HDF5 revision group `0`.
- HDF5 revision creation is not implemented.
- Docker CLI disables interactive annotator selection.
- Masked reports do not mask covered text or offsets.
- CLI writes JSON output even when `--omit-dump` sets `dump_dictionary = None`; this can result in `null` JSON output.
- INCEpTION API SSL verification is disabled in some calls by passing `False` from CLI/GUI.

## 12. Improvement Ideas

- Add explicit XMI support or remove XMI wording where unsupported.
- Implement HDF5 revision selection and revision creation.
- Make `--omit-dump` skip JSON file creation entirely.
- Add tests for:
  - annotator filtering;
  - whitelist vs blacklist logic;
  - `.ser` rejection;
  - HDF5 reading/writing;
  - masked report generation.
- Add CLI option for annotation type instead of hard-coded `gemtex.Concept`.
- Add CLI option for feature id_prefix instead if hard-coded `http://snomed.info/id/`
- Add safer handling for missing HDF5 groups/datasets.
- Consider masking covered text for stronger privacy guarantees.
- Normalize and document offset serialization in JSON.
- Reuse one implementation path for CLI and GUI report generation to avoid drift.
