"""NiceGUI prototype entry point, also selected by gui.app --frontend nicegui."""
from __future__ import annotations

import argparse
import importlib.metadata
import sys
from typing import Optional, Sequence

NICEGUI_VERSION = "4.0.0"


def _load_ui():
    """Load the optional frontend lazily from the shared Python environment."""
    if sys.version_info < (3, 11):
        raise RuntimeError("The NiceGUI prototype needs Python 3.11+; use the project's .venv-py311 environment.")
    try:
        version = importlib.metadata.version("nicegui")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError("Enable the nicegui extra in the project environment: uv sync --locked --extra nicegui (set UV_PROJECT_ENVIRONMENT=.venv-py311).") from exc
    if version != NICEGUI_VERSION:
        raise RuntimeError(f"This prototype targets nicegui=={NICEGUI_VERSION}; found {version}.")
    from nicegui import app, ui, events
    from snomed_post_processing.gui.nicegui.transport import guard_socketio_disconnects
    guard_socketio_disconnects(app)
    return ui, events


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic, read-only NiceGUI frontend prototype.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--show", action="store_true", help="Open a browser on startup.")
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        ui, events = _load_ui()
    except RuntimeError as exc:
        parser.exit(2, f"{exc}\n")
    from snomed_post_processing.gui.nicegui.page import build_page

    @ui.page("/")
    def index():
        build_page(ui, events)

    # One server, no reload worker, no implicit browser launch.
    ui.run(host=arguments.host, port=arguments.port, show=arguments.show,
           reload=False, title="SNOMED Postprocessing — NiceGUI prototype")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
