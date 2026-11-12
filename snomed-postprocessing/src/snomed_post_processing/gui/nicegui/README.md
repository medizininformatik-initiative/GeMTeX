# NiceGUI frontend — suggestions and explicit manual review

Preview **synthetic data or uploaded suggestions JSON**, then deliberately stage
and save manual choices and download/restore reviewed-decisions JSON.
Processing, CAS write-back and deployment are not connected.
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

## Load saved suggestions

In **3. Review & apply**, use **Load suggestions JSON** (one file, up to **50 MiB**).
Use the suggestions JSON produced by the existing CLI/Streamlit workflow, not
CriticalFindings or reviewed-decisions JSON. **Use synthetic demo** resets only
this page's preview.

The adapter uses `read_sanitization_suggestions_json_with_metadata` unchanged.
It preserves backend objects/metadata server-side and inherits the saved
`metadata.annotators` scope (empty/missing = all); there is no broader scope
selector yet. Original zero-based `suggestion_index` values survive filtering.
Grid filters change display only, not the artifact or scope.

Candidate rows have snapshot/finding/role/ordinal IDs, not SCTID identities:
duplicate SCTIDs/evidence channels and diagnostic-only targets remain distinct.
Saved score precision/order, competition ranks, rationale, proposed targets,
source/member/matched-term evidence, ignored flags and retrieval-limit warnings
are retained. Diagnostic context is unranked and cannot become selectable.
A saved proposal is displayed as provenance, never automatically selected.

Successful imports clear navigation; stale row/candidate clicks are rejected.
Parsing runs in a NiceGUI worker; newer uploads/demo reset supersede older
pending loads. Invalid, oversized or unreadable files leave the active preview
unchanged, with a safe error that does not echo file contents. No metadata paths
are followed and no HDF5/retrieval/policy pipeline is run.

State is page-local and discarded on reload; the application adds no persistent
store. Review JSON export is an explicit download. NiceGUI may temporarily spool uploads itself. Imported text is
rendered as text, not HTML. Real suggestions may contain clinical text: upload
only data you intend to show in this browser session.

## Stage, save and restore review

Load suggestions first; staging/import/export are disabled for the synthetic demo.

1. Click a finding and inspect candidates/evidence. Navigation never approves a target.
2. **Use candidate** stages the inspected selectable target, or **Keep original**
   stages an explicit human-reviewed unchanged annotation. Context targets cannot be used.
3. Optionally **Mark document reviewed** / **Unmark document reviewed**. Flags are
   progress, not proof of replacement for every finding.
4. **Save choices** commits pending choices/flags in this page only. Like Streamlit,
   confirming a document protects its unchanged rows as human-reviewed Keeps; it
   removes automatic ownership, not the chosen targets. **Discard pending changes**
   leaves saved choices and flags intact. Unmarking does not undo manual choices.
5. **Download reviewed decisions JSON** uses the backend version-1 format and is
   blocked until pending changes are saved or discarded. Reload loses page state;
   download explicitly to retain review. Download serialization runs in a worker;
   a concurrent review change invalidates that download. Downloads may contain clinical text.
6. **Load reviewed decisions JSON (replaces current review)** restores matching
   choices, provenance and flags atomically (50 MiB limit). Import replaces rather
   than merges prior saved/pending review. Invalid/read-error imports leave it intact.

Saved scope cannot silently cover broader suggestions. Original indices and source
identities are checked; NiceGUI exports also bind the full suggestions content by
SHA-256. Manual candidate ordinal/evidence distinguishes duplicate SCTIDs/channels.
Legacy Streamlit artifacts without this fingerprint use index/identity and current
selectable-candidate checks. Only write-back settings are copied from suggestions
metadata into review exports, not full-document clinical contexts; imported context
records, if present, are filtered to artifact scope. Metadata paths are not followed and HDF5 is not opened.
Imported rules are retained and reserve their source identities; imported deletions,
manual edits and ID removals are protected from generic edits. Rule/target policy
revalidation is **not** done here: edit/revalidate these actions in Streamlit. Rule-
manual conflicts are rejected rather than silently dropping protected manual work.
Unchanged automatic provenance survives unrelated manual saves; explicit human
confirmation removes automatic ownership for the affected choices/documents.

New suggestions or **Use synthetic demo** reset all review state. Latest upload/reset
wins; a pending decision import cannot overwrite subsequent manual edits. Filtering
is display-only and never limits decision export. No CAS files are changed.

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
- `transport.py`: Socket.IO ASGI early-disconnect and response-header guard.
- `page.py`: three workflow tabs and vertically stacked, full-width Community AG Grid findings/candidate sections. Candidates sit below findings at every screen size; compact rank/score columns leave more room for FSNs, with internal horizontal scrolling on very narrow screens.
- `state.py`: framework-independent, per-page navigation state with stable row IDs.
- `suggestions.py`: read-only backend-reader adapter and safe import errors.
- `review.py`: page-local staging/save commands and backend-compatible JSON adapter.
- `review_ui.py`: event adapters, explicit review controls and guarded async import.
- `demo.py`: three artificial findings, toy string SCTIDs, tied ranks `1,1,3`,
  diagnostic-only context and a no-candidate example.
- `requirements.txt`: standalone reference pin; prefer the project extra above.

Clicks only navigate/preview: no target is preselected or approved. Selecting a
different finding updates details/candidates, not the main grid. Text renders as
text, not HTML; filters are display-only. Reloading discards per-page preview
state. There is no persistent/global review state or cookie secret.

**Not connected:** project ZIP/HDF5 loading, shared processing-scope controls,
policy checks, rule editing/application, generation, conditions, new deletion/manual-
edit/ID-removal choices, ZIP sanitization or INCEpTION. Those actions remain disabled.
Only explicitly uploaded suggestions/review JSON is read; startup uses artificial data.

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

The subsequent read-only import increment passes **67 focused checks**, including
existing reader/scope/synthetic workflow regressions. A real NiceGUI multipart
upload test used only the synthetic fixture: an Alice-scoped artifact loaded with
original indices, and a subsequent invalid upload preserved the prior data. The
owned loopback test server was stopped. No live INCEpTION, clinical project or
HDF5 was used for that integration check; the full suite was not rerun.

### Socket.IO transport regression

The installed Engine.IO adapter returns an empty environment if its first ASGI
frame is an already-closed HTTP/WebSocket connection, then accesses
`REQUEST_METHOD`. Its mixed-case response header names also prevent Starlette
recognizing existing gzip encoding, producing duplicate gzip encodings for larger
polling updates and disconnecting clients.

`transport.py` wraps only NiceGUI's `/_nicegui_ws` mount before server startup:
it ignores initial disconnects, replays valid first frames exactly once, and
lowercases response header names as ASGI requires (preserving values/order/repeats
and body bytes). Other routes, uploads, valid handshakes and downstream exceptions
are unchanged. Installation is idempotent; no installed packages are patched or
downgraded, and compression is not disabled.

61 focused tests pass, including real Engine.IO disconnect and Starlette gzip
regressions. Real polling **and** WebSocket clients completed page handshakes,
uploaded the scoped synthetic fixture, received live UI updates and safe invalid-
upload feedback without server ASGI errors. Owned loopback servers were stopped;
no clinical inputs or external services were used. This is protocol-level testing,
not visual/browser JavaScript testing; the full suite was not rerun.

After updating, stop/restart the NiceGUI process and refresh the browser; a page
refresh alone cannot update an already-running server with reload disabled.

### Manual review increment

97 focused tests pass, including scope/synthetic workflows, exact Streamlit fixture
round-trip, protected imports, duplicate-channel evidence, atomic failures and races.
Real polling and WebSocket clients exercised actual NiceGUI listener events through
scope-aware staging, Keep, Save, document flags, binary JSON download, replacing
import and safe failed import without ASGI errors. Owned loopback servers stopped;
no clinical/external-service inputs. Full-suite and visual/browser-JavaScript checks
were not performed for this increment. The three documented baseline failures remain
unresolved, not suppressed.

Continue with browser interaction validation and synthetic artifact comparisons before
connecting explicit processing commands or CAS write-back.

References: `docs/gui-alternative/references/nicegui/` and
`docs/gui-alternative/STREAMLIT_TO_NICEGUI_COMPONENTS.md`.
