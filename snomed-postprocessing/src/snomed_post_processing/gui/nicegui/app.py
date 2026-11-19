"""NiceGUI prototype entry point, also selected by gui.app --frontend nicegui."""
from __future__ import annotations

import argparse
import importlib.metadata
from pathlib import Path
import sys
from typing import Optional, Sequence

NICEGUI_VERSION = "4.0.0"
SOURCE_ROOT = Path(__file__).resolve().parents[2]


def _load_ui():
    """Load the optional frontend lazily from the shared Python environment."""
    if sys.version_info < (3, 11):
        raise RuntimeError("The NiceGUI prototype needs Python 3.11+")
    try:
        version = importlib.metadata.version("nicegui")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError("Enable the nicegui extra in the project environment: uv sync --locked --extra nicegui") from exc
    if version != NICEGUI_VERSION:
        raise RuntimeError(f"This prototype targets nicegui=={NICEGUI_VERSION}; found {version}.")
    from nicegui import app, ui, events
    from snomed_post_processing.gui.nicegui.transport import guard_socketio_disconnects
    guard_socketio_disconnects(app)
    return ui, events


def main(argv: Optional[Sequence[str]] = None, *, page_builder=None, setup=None,
         title="SNOMED Postprocessing — NiceGUI version") -> int:
    parser = argparse.ArgumentParser(description="NiceGUI frontend version for the SNOMED Postprocessing project.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--show", action="store_true", help="Open a browser on startup.")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Reload on Python or CSS changes; development only and discards in-memory state.",
    )
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        ui, events = _load_ui()
    except RuntimeError as exc:
        parser.exit(2, f"{exc}\n")
    if setup is not None:
        setup()
    if page_builder is None:
        from snomed_post_processing.gui.nicegui.page import build_page
        page_builder = build_page

    @ui.page("/")
    def index():
        page_builder(ui, events)

    run_options = {}
    if arguments.reload:
        run_options.update(
            uvicorn_reload_dirs=str(SOURCE_ROOT),
            uvicorn_reload_includes="*.py,*.css",
        )
    ui.run(host=arguments.host, port=arguments.port, show=arguments.show,
           reload=arguments.reload, title=title, **run_options)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
