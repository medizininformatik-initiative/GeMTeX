"""Stable GUI launcher; currently starts the Streamlit frontend.

Run with:
    python -m snomed_post_processing.gui.app
or:
    python src/snomed_post_processing/gui/app.py

Additional arguments are forwarded to Streamlit, e.g. --server.port 8502.
Switch the frontend here when the NiceGUI implementation is ready.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
from typing import Optional, Sequence


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Launch the frontend with this interpreter and preserve its exit code."""
    arguments = sys.argv[1:] if argv is None else argv
    app_path = pathlib.Path(__file__).resolve().parent / "streamlit" / "app.py"
    return subprocess.call([
        sys.executable, "-m", "streamlit", "run", str(app_path), *arguments,
    ])


if __name__ == "__main__":
    raise SystemExit(main())
