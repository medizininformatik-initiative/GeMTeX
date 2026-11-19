"""Stable GUI launcher; Streamlit by default, with NiceGUI workspace options.

Run with:
    python -m snomed_post_processing.gui.app
or:
    python src/snomed_post_processing/gui/app.py

Additional arguments are forwarded to the selected frontend:
    --server.port 8502                 (Streamlit)
    --frontend nicegui --port 8080     (NiceGUI workspace)
    --frontend workspace --port 8080   (navigation workspace)
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
from typing import Optional, Sequence


def _discard_local_nicegui_aliases(directory: pathlib.Path) -> None:
    """Remove IDE-cached local aliases, never the installed SDK or project imports."""
    for name, module in tuple(sys.modules.items()):
        if name != "nicegui" and not name.startswith("nicegui."):
            continue
        origin = getattr(module, "__file__", None)
        if origin and pathlib.Path(origin).resolve().is_relative_to(directory):
            sys.modules.pop(name, None)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Launch one frontend in this environment."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--frontend", choices=("streamlit", "nicegui", "workspace"), default="streamlit")
    selected, arguments = parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    if selected.frontend in ("nicegui", "workspace"):
        # Import lazily: normal launcher imports do not load either framework.
        # Run in-process so NiceGUI owns one server without another child process.
        # File launches put gui/ first on sys.path. Its nicegui/ and streamlit/
        # subpackages must not shadow the installed frameworks as top-level names.
        original_path = sys.path[:]
        launcher_directory = pathlib.Path(__file__).resolve().parent
        try:
            sys.path[:] = [entry for entry in sys.path if pathlib.Path(entry).resolve() != launcher_directory]
            _discard_local_nicegui_aliases(launcher_directory / "nicegui")
            if selected.frontend == "workspace":
                from snomed_post_processing.gui.workspace.app import main as frontend_main
            else:
                from snomed_post_processing.gui.nicegui.app import main as frontend_main
            return frontend_main(arguments)
        finally:
            sys.path[:] = original_path
    app_path = pathlib.Path(__file__).resolve().parent / "streamlit" / "app.py"
    return subprocess.call([
        sys.executable, "-m", "streamlit", "run", str(app_path), *arguments,
    ])


if __name__ == "__main__":
    raise SystemExit(main())
if __name__ == "__mp_main__":
    main()
