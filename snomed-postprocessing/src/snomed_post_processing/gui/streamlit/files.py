"""File handling helpers for the Streamlit GUI."""

from __future__ import annotations

import pathlib
import tempfile


def save_uploaded_file(uploaded_file, suffix: str) -> pathlib.Path:
    """Persist a Streamlit upload-like object to a temporary file."""
    if isinstance(uploaded_file, pathlib.Path):
        return uploaded_file
    temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="snomed_gui_"))
    target = temp_dir / f"upload{suffix}"
    target.write_bytes(uploaded_file.getvalue())
    return target
