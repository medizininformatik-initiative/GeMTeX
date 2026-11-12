# NiceGUI frontend — first prototype

This is a **synthetic, read-only prototype**, not a replacement production GUI.
Both frontends now use the same Python 3.11 project environment, `.venv-py311`.
The shared `gui/app.py` defaults to Streamlit; select NiceGUI explicitly.

## Run NiceGUI

From the repository root, with the already installed extra:

```bash
.venv-py311/Scripts/python -m snomed_post_processing.gui.app --frontend nicegui --show
```

Or run the Python file directly:

```bash
.venv-py311/Scripts/python src/snomed_post_processing/gui/app.py --frontend nicegui --show
```

In your IDE, select `.venv-py311/Scripts/python.exe`, use `gui/app.py` as the
script, and set its parameters to `--frontend nicegui --show`.

Default URL: `http://127.0.0.1:8080`. Omit `--show` to avoid opening a browser;
use `--port 8081` to select another port. NiceGUI runs in-process with reload
disabled: this launcher does not start Streamlit as well.
Do not launch this file using `streamlit run`.

For Streamlit, omit `--frontend` or use `--frontend streamlit`.
Its options remain unchanged, e.g. `--server.port 8502`.

## Install/update the shared environment

`nicegui==4.0.0` is pinned in the project's **optional `nicegui` extra** and
resolved in `uv.lock`, not a separate backend-less runtime. No `PYTHONPATH`
setting or `--no-project` command is needed. The original Python 3.9 `.venv`
remains untouched; do not select it for either frontend.

PowerShell:

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-py311"
uv sync --locked --extra nicegui
uv run --locked --extra nicegui python -m snomed_post_processing.gui.app --frontend nicegui --show
```

Bash:

```bash
UV_PROJECT_ENVIRONMENT=.venv-py311 uv sync --locked --extra nicegui
UV_PROJECT_ENVIRONMENT=.venv-py311 uv run --locked --extra nicegui python -m snomed_post_processing.gui.app --frontend nicegui --show
```

Keep `--extra nicegui` on uv run/sync commands for this environment; otherwise
uv can remove the optional packages. Direct `.venv-py311/Scripts/python` launches
do not sync packages. Other systems use the environment's `bin/python` path.
Setup commands may download dependencies. Docker still defaults to Streamlit
and does not install the optional extra automatically.

## Prototype contents and limits

- `app.py`: NiceGUI bootstrap, also accessible directly as a module.
- `page.py`: three workflow tabs and Community AG Grid findings/candidate panes.
- `state.py`: framework-independent, per-page navigation state with stable row IDs.
- `demo.py`: three artificial findings, toy string SCTIDs, tied ranks `1,1,3`,
  diagnostic-only context and a no-candidate example.
- `requirements.txt`: standalone reference pin; prefer the project extra above.

Clicks only navigate/preview: no target is preselected or approved. Selecting a
different finding updates details/candidates, not the main grid. Text renders as
text, not HTML; filters are display-only. Reloading discards per-page preview
state. There is no persistent/global review state or cookie secret.

**Not connected:** project/HDF5/file loading, processing scope, policy checks,
rules, generation, conditions, decision staging/import/export, reviewed flags,
ZIP sanitization or INCEpTION. Action buttons are disabled. No clinical project
files are read to build this prototype.

## Verification

NiceGUI 4.0.0 and Streamlit 1.50.0 are installed in the shared Python 3.11.13
environment. The 100-package cross-platform lock installs 99 packages on Windows.
Only certifi, idna and Pygments changed among the retained dependency versions.
Dependency consistency and offline lock checks pass.

Both file and module forms of the shared launcher were started on temporary
loopback ports. `GET /` returned HTTP 200 with the prototype warning, finding grid
and candidate controls; both test servers were stopped afterward. Direct file
startup avoids shadowing the installed SDK with the sibling `nicegui/` directory.
The launcher also discards cached top-level `nicegui` aliases only when they point
to that local folder, preserving the real installed SDK and qualified project
modules. This covers IDE sessions that imported the local folder before launch.
After updating the launcher, restart the IDE run rather than reusing an old session.
A follow-up check passed 31 focused tests and HTTP startup in module, direct-file
and deliberately preloaded-local-alias modes; the full suite was not rerun for this follow-up. This verifies server startup and page
construction, **not browser JavaScript, selection/focus/scroll or visual behavior**.
The full regression suite reports **280 passed, 3 pre-existing GUI-default failures,
2 warnings**. The same failures were previously reproduced under Python 3.9.
No live INCEpTION requests or clinical fixture reads were used for the startup check.

Continue with browser interaction checks, then connect existing backend artifacts
and explicit commands without changing scope, provenance, scoring or JSON/ZIP semantics.

References: `docs/gui-alternative/references/nicegui/` and
`docs/gui-alternative/STREAMLIT_TO_NICEGUI_COMPONENTS.md`.
