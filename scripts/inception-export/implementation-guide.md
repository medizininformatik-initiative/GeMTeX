# INCEpTION Annotator Export Implementation Guide

Short summary: implement a Python CLI, with an optional Streamlit GUI later, that uses the INCEpTION API to list/select projects, export one selected project in XMI format, optionally select included/excluded annotators, and write one small ZIP per selected document/annotator pair from `annotation/`. Each output ZIP contains only `TypeSystem.xml` and the annotator XMI, and is named `DOCUMENT_NAME-ANNOTATOR_NAME.zip` or, when anonymization is enabled, `DOCUMENT_NAME-ANON_NAME.zip` plus a mapping file.

## Goal

Create a script in this workspace, e.g. `inception-export.py`, that:

1. Connects to an INCEpTION instance via the API.
2. Lists available projects and supports selecting a project in both CLI and GUI modes.
3. Exports the selected project.
4. Lists available annotators in the selected project and supports include/exclude selection in both CLI and GUI modes.
5. Processes only selected annotator files under the project export's `annotation/` directory.
6. Produces individual ZIP files, one per exported annotation XMI.
7. Ensures every individual ZIP contains only:
   - `TypeSystem.xml`
   - the annotation XMI file
8. Names output ZIPs as:
   - without anonymization: `DOCUMENT_NAME-ANNOTATOR_NAME.zip`
   - with anonymization: `DOCUMENT_NAME-ANON_NAME.zip`
9. Optionally writes a mapping file from real annotator names to anonymized names.
10. If anonymization is enabled, the real annotator name must not appear anywhere in generated files, generated ZIP entry names, logs, summaries, temporary persisted outputs, or any other output artifact. The only permitted place for real annotator names is the explicit exported mapping file.

The desired output naming mirrors the effective result of `zip-renaming.py`: the document identifier/name is the prefix and the annotator ZIP name is the suffix. Unlike `zip-renaming.py`, this new script can obtain the document name directly from the INCEpTION export path or project metadata instead of recursively renaming existing ZIPs.

## Relevant existing code

### `zip-renaming.py`

Current script behavior to preserve conceptually:

- It finds ZIP files below document-named folders.
- It prefixes each ZIP with a document identifier extracted from the folder name.
- Resulting names look like:

```text
DOCUMENT_NAME-ANNOTATOR_NAME.zip
```

For the new implementation, do not reuse the recursive ZIP extraction/repacking logic. Only keep the output naming convention.

### INCEpTION API usage and selection examples

The SNOMED post-processing project contains useful API export logic in:

```text
../../snomed-postprocessing/src/snomed_post_processing/utils/__init__.py
```

Relevant pattern:

```python
from pycaprio import Pycaprio

client = Pycaprio(host, (username, password))
projects = {p.project_name: p.project_id for p in client.api.projects()}
project_export = client.api.export_project(project_id, "jsoncas")
```

For this script, export XMI instead of JSON CAS:

```python
project_export = client.api.export_project(project_id, "xmi")
```

If the exact format string differs for the installed INCEpTION/pycaprio version, verify it against the API documentation or by checking accepted export formats. The implementation should fail with a clear error if XMI export is unsupported.

The same SNOMED project also shows annotator discovery and selection patterns:

- `get_annotator_names(project_zip)` reads the exported ZIP and extracts available annotator names from annotation CAS paths.
- `prompt_for_names(annotator_names)` uses a checkbox prompt to let CLI users select which annotators to process.
- `streamlit_app.py` demonstrates a GUI flow for entering INCEpTION API credentials and choosing a project/export workflow.

For this implementation, expose project selection and annotator include/exclude selection in both CLI and GUI modes. The underlying non-UI functions should be shared so CLI and Streamlit behave identically.

## Expected INCEpTION project ZIP structure

An XMI project export is expected to contain entries similar to:

```text
TypeSystem.xml
exportedproject.json
annotation/<DOCUMENT_NAME>/<ANNOTATOR_NAME>.xmi
annotation/<DOCUMENT_NAME>/INITIAL_CAS.xmi
curation/<DOCUMENT_NAME>/CURATION_USER.xmi
```

Only paths below `annotation/` should be considered.

Skip:

- `curation/`
- `annotation_ser/`
- `curation_ser/`
- directories
- non-`.xmi` files
- `INITIAL_CAS.xmi`, unless the user explicitly asks otherwise later

## CLI design

Recommended command:

```bash
python inception-export.py \
  --host https://inception.example.org \
  --username USER \
  --password PASSWORD \
  --project PROJECT_SLUG_OR_ID \
  --output-dir ./exports
```

List/select projects before export:

```bash
# Print available projects and exit
python inception-export.py \
  --host https://inception.example.org \
  --username USER \
  --password PASSWORD \
  --list-projects

# Prompt interactively for a project if --project is omitted
python inception-export.py \
  --host https://inception.example.org \
  --username USER \
  --password PASSWORD \
  --output-dir ./exports \
  --select-project
```

Select annotators:

```bash
# Include only selected annotators
python inception-export.py \
  --host https://inception.example.org \
  --username USER \
  --password PASSWORD \
  --project PROJECT_SLUG_OR_ID \
  --output-dir ./exports \
  --include-annotator alice \
  --include-annotator bob

# Exclude selected annotators
python inception-export.py \
  --host https://inception.example.org \
  --username USER \
  --password PASSWORD \
  --project PROJECT_SLUG_OR_ID \
  --output-dir ./exports \
  --exclude-annotator test_user

# Prompt interactively with available annotators from the selected project
python inception-export.py \
  --host https://inception.example.org \
  --username USER \
  --password PASSWORD \
  --project PROJECT_SLUG_OR_ID \
  --output-dir ./exports \
  --select-annotators
```

Optional anonymization:

```bash
python inception-export.py \
  --host https://inception.example.org \
  --username USER \
  --password PASSWORD \
  --project PROJECT_SLUG_OR_ID \
  --output-dir ./exports \
  --anonymize \
  --mapping-file ./exports/annotator-mapping.csv
```

Recommended arguments:

| Argument | Required | Description |
| --- | --- | --- |
| `--host` | yes | Base URL of the INCEpTION instance. |
| `--username` | yes | User with `REMOTE` role/API access. |
| `--password` | yes | Password. Prefer allowing env var fallback. |
| `--project` | no if `--select-project`/GUI is used; otherwise yes | Project URL slug, project name, or numeric project id. |
| `--list-projects` | no | List available projects from the INCEpTION instance and exit. |
| `--select-project` | no | Interactively select one project in the CLI if `--project` is not supplied. |
| `--output-dir` | yes | Directory for individual ZIP files. |
| `--anonymize` | no | Replace annotator names in all output filenames, ZIP entry names, and file contents where they occur. Real annotator names may appear only in the mapping file. |
| `--mapping-file` | no | CSV/JSON file storing anonymization mapping. Default: `<output-dir>/annotator-mapping.csv`. |
| `--keep-project-export` | no | Keep the full temporary project export ZIP for debugging. |
| `--verify-ssl` | no | Boolean/path option matching the SNOMED helper behavior. |
| `--overwrite` | no | Permit replacing existing output ZIPs/mapping file. Default should be false. |
| `--include-annotator` | no | Repeatable option. Only export these annotators. Mutually exclusive with `--exclude-annotator`. |
| `--exclude-annotator` | no | Repeatable option. Export all annotators except these. Mutually exclusive with `--include-annotator`. |
| `--list-annotators` | no | Export/read the selected project enough to list available annotators, then exit. Requires a selected project. |
| `--select-annotators` | no | Interactively select annotators in the CLI after the project is selected/exported. |

## Implementation steps

### 1. Connect to INCEpTION

Use `pycaprio` as in the SNOMED code.

Pseudo-code:

```python
from pycaprio import Pycaprio

client = Pycaprio(host, (username, password))

if verify_ssl is False:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    client.api.client.session.verify = False
elif isinstance(verify_ssl, str):
    client.api.client.session.verify = verify_ssl
```

Do not log the password.

### 2. List and select project

Project discovery must be available to both CLI and GUI.

Required project selection behavior:

- `--list-projects`: connect, list available project names/ids, then exit.
- `--project VALUE`: resolve the given name/slug/id non-interactively.
- `--select-project`: show an interactive CLI selection if `--project` is omitted.
- GUI: show the same available projects in a Streamlit selectbox after connecting.

Support either exact/case-insensitive project name match or numeric id.

Pseudo-code:

```python
projects = client.api.projects()
project_by_name = {p.project_name: p.project_id for p in projects}

if project_arg.isdigit():
    project_id = int(project_arg)
    project_label = next((p.project_name for p in projects if p.project_id == project_id), project_arg)
else:
    matches = [p for p in projects if p.project_name.lower() == project_arg.lower()]
    if not matches:
        raise ValueError(f"Project not found: {project_arg}")
    project_id = matches[0].project_id
    project_label = matches[0].project_name
```

### 3. Export selected project as XMI

```python
project_export_bytes = client.api.export_project(project_id, "xmi")
```

Write bytes to a temporary file or process via `io.BytesIO`. A temporary file is useful for debugging when `--keep-project-export` is set.

Recommended:

```python
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as tmpdir:
    full_export_path = Path(tmpdir) / f"{safe_filename(project_label)}.zip"
    full_export_path.write_bytes(project_export_bytes)
    process_project_zip(full_export_path, output_dir, anonymize, mapping_file)
```

### 4. Discover available annotators and apply selection

After exporting the selected project, discover annotators from the exported XMI ZIP before writing individual output ZIPs. This mirrors `get_annotator_names(project_zip)` and `prompt_for_names(annotator_names)` from `../../snomed-postprocessing/`, but should work for XMI paths under `annotation/`.

Recommended behavior:

- No include/exclude/prompt option: export all discovered annotators.
- `--list-annotators`: print discovered annotators for the selected project and exit.
- `--include-annotator NAME`: export only matching annotators. Repeatable.
- `--exclude-annotator NAME`: export all except matching annotators. Repeatable.
- `--select-annotators`: show a checkbox prompt in CLI.
- GUI: show discovered annotators in a multiselect, plus an include/exclude mode selector.

Include and exclude options should be mutually exclusive. Matching should be case-insensitive, but the original real annotator name should remain the mapping key internally.

Pseudo-code:

```python
def discover_annotators(project_zip_path: Path) -> set[str]:
    annotators = set()
    with zipfile.ZipFile(project_zip_path, "r") as z:
        for _, _, annotator_name in iter_annotation_xmis(z):
            annotators.add(annotator_name)
    return annotators


def build_annotator_filter(available, include=None, exclude=None, selected=None):
    available_by_lower = {a.lower(): a for a in available}
    if include and exclude:
        raise ValueError("--include-annotator and --exclude-annotator are mutually exclusive")
    if selected is not None:
        include = selected
    if include:
        requested = {a.lower() for a in include}
        unknown = requested - set(available_by_lower)
        if unknown:
            raise ValueError(f"Unknown annotator(s): {', '.join(sorted(unknown))}")
        return requested
    if exclude:
        requested = {a.lower() for a in exclude}
        unknown = requested - set(available_by_lower)
        if unknown:
            raise ValueError(f"Unknown annotator(s): {', '.join(sorted(unknown))}")
        return set(available_by_lower) - requested
    return None  # None means all annotators
```

When anonymization is enabled, do not print real annotator names in normal progress logs after the user has finalized selection. Listing/selecting annotators necessarily displays real names to the authorized user; generated logs/artifacts after export should use anonymous names or counts only.

### 5. Read required files from project ZIP

Open the full export with `zipfile.ZipFile`.

Find `TypeSystem.xml` exactly, allowing for possible leading folder prefixes if needed:

```python
def find_typesystem(zip_file):
    candidates = [i.filename for i in zip_file.infolist() if i.filename.endswith("TypeSystem.xml") and not i.is_dir()]
    if not candidates:
        raise ValueError("Export does not contain TypeSystem.xml")
    return candidates[0]
```

Iterate annotation XMI files:

```python
def iter_annotation_xmis(zip_file):
    for info in zip_file.infolist():
        path = info.filename.replace("\\", "/")
        if info.is_dir():
            continue
        if not path.startswith("annotation/"):
            continue
        if not path.endswith(".xmi"):
            continue
        if path.endswith("/INITIAL_CAS.xmi"):
            continue

        # Expected: annotation/<document>/<annotator>.xmi
        parts = path.split("/")
        if len(parts) < 3:
            continue

        document_name = parts[1]
        annotator_name = Path(parts[-1]).stem
        yield info, document_name, annotator_name
```

If document names may contain slashes due to nested paths, use the first segment after `annotation/` only if INCEpTION guarantees that layout. Otherwise derive the annotator from the basename and the document from all middle path parts:

```python
parts = path.split("/")
document_name = "/".join(parts[1:-1])
annotator_name = Path(parts[-1]).stem
```

For filenames, sanitize `/` to `_`.

### 6. Create one ZIP per annotator/document XMI

Each output ZIP should contain only:

```text
TypeSystem.xml
<ANNOTATOR_NAME>.xmi
```

or optionally preserve a minimal path:

```text
TypeSystem.xml
annotation.xmi
```

Recommended: keep the original annotator XMI basename inside the individual ZIP because it is simple and traceable. If anonymization is enabled, use the anonymized name inside the ZIP too.

Important anonymization requirement: when `--anonymize` is enabled, the real annotator name must not be present anywhere in the produced ZIP file. This includes:

- the outer ZIP filename
- paths/file names inside the ZIP
- XMI XML content
- ZIP comments or metadata fields if the implementation sets any

The implementation must either sanitize the XMI content before writing it or validate that the real annotator name is absent. A conservative approach is to decode the XMI as UTF-8/XML text, replace exact occurrences of the real annotator name with the anonymous annotator name, write the sanitized bytes, and then assert that the real name no longer occurs in the written content.

Pseudo-code:

```python
with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as out_zip:
    out_zip.writestr("TypeSystem.xml", source_zip.read(typesystem_path))
    xmi_bytes = source_zip.read(info.filename)
    if anonymize:
        xmi_bytes = sanitize_xmi_bytes(xmi_bytes, real_annotator_name, output_annotator_name)
    out_zip.writestr(f"{safe_filename(output_annotator_name)}.xmi", xmi_bytes)
```

Do not copy `exportedproject.json`, source documents, curation files, other users, or directories.

### 7. Naming output ZIPs

Required format:

```text
DOCUMENT_NAME-ANNOTATOR_NAME.zip
```

Implementation:

```python
zip_name = f"{safe_filename(document_name)}-{safe_filename(output_annotator_name)}.zip"
output_zip_path = output_dir / zip_name
```

`safe_filename` should remove or replace characters invalid on Windows and problematic on Unix:

```python
import re

def safe_filename(value: str) -> str:
    value = value.strip()
    value = re.sub(r'[<>:"/\\|?*]+', "_", value)
    value = re.sub(r"\s+", "_", value)
    value = value.strip("._ ")
    return value or "unnamed"
```

Collision handling:

- Default: fail if `output_zip_path` already exists.
- With `--overwrite`: replace existing file.
- If two annotations resolve to the same sanitized name, fail and print both source paths, or append a deterministic suffix such as `-2`. Failing is safer.

### 8. Anonymization mapping

When `--anonymize` is set, replace annotator names with stable anonymous IDs.

Recommended anonymous names:

```text
annotator001
annotator002
annotator003
```

Rules:

1. The same real annotator must always map to the same anonymous name within a run.
2. If `--mapping-file` exists, load it first and preserve existing assignments.
3. New annotators get the next unused number.
4. Write the mapping file at the end only after successful export, unless the script streams output and needs incremental safety.
5. Never anonymize document names unless a separate future flag is added.

CSV format:

```csv
real_annotator,anonymous_annotator
alice,annotator001
bob,annotator002
```

Pseudo-code:

```python
def get_anon_name(real_name, mapping):
    if real_name in mapping:
        return mapping[real_name]
    used = set(mapping.values())
    idx = 1
    while True:
        candidate = f"annotator{idx:03d}"
        if candidate not in used:
            mapping[real_name] = candidate
            return candidate
        idx += 1
```

Security note: the mapping file contains identifying information. Do not print its full contents by default.

Strict anonymization rule: if `--anonymize` is true/yes, the real annotator name must not appear in any generated artifact except the mapping file. This includes output ZIP names, internal ZIP entry names, XMI contents, logs, reports, console summaries, temporary files that are kept via `--keep-project-export`, and error messages. If an error needs to mention a source annotation while anonymization is active, use the anonymous name or a non-identifying counter/path redaction instead.

### 9. Suggested module/function layout

```python
# inception-export.py

def parse_args() -> argparse.Namespace: ...
def make_client(host, username, password, verify_ssl): ...
def list_projects(client) -> list[ProjectInfo]: ...
def prompt_for_project(projects: list[ProjectInfo]) -> ProjectInfo: ...
def resolve_project(client, project_arg) -> tuple[int, str]: ...
def export_project_xmi(client, project_id) -> bytes: ...
def find_typesystem(zip_file) -> str: ...
def iter_annotation_xmis(zip_file): ...
def discover_annotators(project_zip_path: Path) -> set[str]: ...
def prompt_for_annotators(annotators: set[str]) -> list[str] | None: ...
def build_annotator_filter(available, include=None, exclude=None, selected=None) -> set[str] | None: ...
def safe_filename(value: str) -> str: ...
def load_mapping(path: Path) -> dict[str, str]: ...
def write_mapping(path: Path, mapping: dict[str, str], overwrite: bool): ...
def get_anon_name(real_name: str, mapping: dict[str, str]) -> str: ...
def sanitize_xmi_bytes(xmi_bytes: bytes, real_annotator: str, anonymous_annotator: str) -> bytes: ...
def write_individual_zip(source_zip, typesystem_path, annotation_info, document_name, real_annotator_name, output_dir, anonymize, mapping, overwrite): ...
def process_project_export(project_zip_path, output_dir, anonymize=False, mapping_file=None, overwrite=False, annotator_filter=None) -> int: ...
def main() -> int: ...
```

Keep UI-independent logic in importable functions. The CLI and optional Streamlit GUI should both call the same project listing, project export, annotator discovery/filtering, anonymization, and ZIP-writing functions.

## Main processing pseudo-code

```python
def process_project_export(project_zip_path, output_dir, anonymize=False, mapping_file=None, overwrite=False, annotator_filter=None):
    output_dir.mkdir(parents=True, exist_ok=True)
    mapping = load_mapping(mapping_file) if anonymize and mapping_file.exists() else {}
    written = []

    with zipfile.ZipFile(project_zip_path, "r") as source_zip:
        typesystem_path = find_typesystem(source_zip)

        for info, document_name, real_annotator in iter_annotation_xmis(source_zip):
            if annotator_filter is not None and real_annotator.lower() not in annotator_filter:
                continue

            output_annotator = get_anon_name(real_annotator, mapping) if anonymize else real_annotator
            zip_name = f"{safe_filename(document_name)}-{safe_filename(output_annotator)}.zip"
            output_zip_path = output_dir / zip_name

            if output_zip_path.exists() and not overwrite:
                raise FileExistsError(f"Output exists: {output_zip_path}")

            with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as out_zip:
                out_zip.writestr("TypeSystem.xml", source_zip.read(typesystem_path))
                xmi_bytes = source_zip.read(info.filename)
                if anonymize:
                    xmi_bytes = sanitize_xmi_bytes(xmi_bytes, real_annotator, output_annotator)
                    assert real_annotator.encode("utf-8") not in xmi_bytes
                out_zip.writestr(f"{safe_filename(output_annotator)}.xmi", xmi_bytes)

            written.append(output_zip_path)

    if anonymize:
        write_mapping(mapping_file, mapping, overwrite=True)

    return len(written)
```

## Optional Streamlit GUI

Plan an optional GUI, e.g. `streamlit_app.py`, modeled after the Streamlit flow in `../../snomed-postprocessing/src/snomed_post_processing/streamlit_app.py`.

Required GUI capabilities should match CLI capabilities:

1. Enter INCEpTION connection settings:
   - host/base URL
   - username
   - password via `st.text_input(..., type="password")`
   - SSL verification option if implemented
2. Connect and list available projects from the INCEpTION instance.
3. Select one project via `st.selectbox`.
4. Export the selected project as XMI, preferably after an explicit button click.
5. Discover available annotators from the selected project export.
6. Select annotators with:
   - mode: `all`, `include selected`, or `exclude selected`
   - `st.multiselect` populated with discovered annotators
7. Configure output:
   - output directory
   - overwrite yes/no
   - anonymize yes/no
   - mapping file path when anonymization is enabled
8. Run export and show a concise result:
   - number of ZIPs written
   - output directory
   - mapping file path if anonymization is enabled

Important GUI anonymization rule: when anonymization is enabled, after the annotator selection step the GUI must not display real annotator names in result summaries, logs, downloadable reports, or generated files. Real names are visible only in the intentional selection UI and in the explicit mapping file.

Suggested GUI state flow:

```python
if "client" not in st.session_state:
    st.session_state.client = None
if "projects" not in st.session_state:
    st.session_state.projects = []
if "project_zip_path" not in st.session_state:
    st.session_state.project_zip_path = None
if "annotators" not in st.session_state:
    st.session_state.annotators = set()
```

Use buttons to avoid accidental API calls:

- `Connect / refresh projects`
- `Export selected project and load annotators`
- `Write individual ZIPs`

For large projects, use `st.spinner(...)` and avoid printing sensitive raw API responses or mapping contents.

## Validation checklist

After implementation, test with a small project export and verify:

1. CLI can list available projects from the INCEpTION instance.
2. GUI can list available projects from the INCEpTION instance.
3. CLI can select a project by id/name and via interactive selection.
4. GUI can select a project via a project dropdown/selectbox.
5. CLI can list discovered annotators for the selected project.
6. GUI can list discovered annotators for the selected project.
7. CLI include/exclude/interactive annotator selection exports only the intended annotators.
8. GUI include/exclude annotator selection exports only the intended annotators.
9. Only files from `annotation/` are exported.
10. No `curation/` files appear in outputs.
11. `INITIAL_CAS.xmi` is skipped.
12. Each output ZIP contains exactly two files:
   - `TypeSystem.xml`
   - one `.xmi`
13. ZIP filenames follow `DOCUMENT_NAME-ANNOTATOR_NAME.zip`.
14. With `--anonymize`, ZIP filenames use anonymous annotator IDs.
15. With `--anonymize`, real annotator names are absent from all generated artifacts except the mapping file. Validate by searching output filenames, internal ZIP entry names, and decoded file contents.
16. The mapping file preserves stable mappings across reruns.
17. Existing files are not overwritten unless `--overwrite` is set.
18. Passwords and mapping contents are not printed in logs.

## Minimal manual inspection commands

```bash
# list produced ZIPs
find ./exports -maxdepth 1 -name '*.zip' -print

# inspect one ZIP
python - <<'PY'
import zipfile, sys
p = sys.argv[1]
with zipfile.ZipFile(p) as z:
    print(z.namelist())
PY ./exports/DOCUMENT-annotator001.zip
```

Expected `namelist()` length is `2`.

## Error handling recommendations

- Missing project: show available project names, but not credentials.
- Project listing failure: report connection/authentication problem without printing credentials.
- Ambiguous project selection: ask user to choose explicitly in CLI/GUI or require exact id.
- Export failure: mention project id/name and requested format `xmi`.
- Missing `TypeSystem.xml`: abort; individual XMI ZIPs would not be self-contained.
- No annotation XMI files found: exit with non-zero status and a clear message.
- Unknown annotator in include/exclude selection: show valid choices in non-anonymized pre-export selection context; if anonymization is active after selection, avoid real names in later logs.
- Empty annotator selection: fail clearly before writing output.
- Existing output collision: abort unless `--overwrite` is set.
- Bad ZIP from API: abort and optionally keep the raw response only when debugging is requested.
