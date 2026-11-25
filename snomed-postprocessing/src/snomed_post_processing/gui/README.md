# Graphical user interfaces

The application exposes two frontend choices through the shared launcher:

- `nicegui` — default; the project-authored workspace UI.
- `streamlit` — the previous UI, retained as a fallback.

```bash
# Default NiceGUI workspace
uv run src/snomed_post_processing/gui/app.py --show

# Explicit frontend selection
uv run src/snomed_post_processing/gui/app.py --frontend nicegui --show
uv run src/snomed_post_processing/gui/app.py --frontend streamlit
```

NiceGUI listens on `127.0.0.1:8080` by default and accepts `--host`, `--port`,
`--show`, and the development-only `--reload`. Streamlit accepts its normal
options after `--frontend streamlit`, for example `--server.port 8502`.

## Structure

- `app.py` — stable launcher; imports only the selected framework.
- `workspace/` — public NiceGUI shell, navigation, and project-authored styling.
- `nicegui/` — shared NiceGUI runtime and workflow controllers used internally by
  the workspace; it is not a separate frontend.
- `streamlit/` — retained Streamlit implementation.
- Framework-neutral GUI modules in this directory hold shared terminology,
  validation, scope, report, and artifact logic.

Both frontends use the same backend pipelines and artifact formats. The standard
Python 3.11 project environment contains both framework dependencies.

## Workflow

The workspace supports the complete local workflow:

1. Select a project ZIP, INCEpTION API export, or eligible SQLite annotation store,
   plus the SNOMED HDF5 and annotator scope.
2. Run or restore policy findings.
3. Generate or restore sanitization suggestions and apply explicit concept rules.
4. Review findings, save decisions, and download reviewed-decisions JSON.
5. Prepare a sanitized project ZIP and deployment artifacts.
6. Optionally import a new project into INCEpTION and upload repaired CAS files.

Preparation is offline and requires no INCEpTION credentials. Remote deployment
uses a separate connection form, explicit confirmation, and always creates a new
project rather than overwriting the source.

## Safety and state

- Selected ZIP, SQLite, HDF5, cache, and project-template inputs are read-only.
- Generated ZIPs, reports, review JSON, and deployment artifacts are separate outputs.
- Annotator exclusions take precedence over inclusions across all workflow stages.
- Clinical text and credentials are not logged; downloaded artifacts can still
  contain clinical data and must be protected accordingly.
- Page state, uploads, credentials, and unsaved review choices are memory-local and
  are lost on process restart or reload. Download decisions and outputs explicitly.
- Background results are rejected when their source, scope, settings, or review
  revision becomes stale.

## Development

Use reload only during development:

```bash
uv run src/snomed_post_processing/gui/app.py --reload
```

Reload restarts the process, interrupts active jobs, and discards in-memory state.
The workspace uses standard NiceGUI/Quasar components, AG Grid Community, system
fonts, and local project CSS; it does not fetch external presentation assets.

Focused tests live under `test/test_gui_*`, `test/test_nicegui_*`, and
`test/test_workspace_shell.py`. Tests mock remote INCEpTION operations unless a
separately approved live validation is performed.

For user-facing instructions, see the [GUI user guide](../../../docs/user-guide.md#workspace-frontend).
Architecture and behavioral details are maintained in the
[GUI knowledge document](../../../okf/snomed-post-processing/interfaces/gui.md).
