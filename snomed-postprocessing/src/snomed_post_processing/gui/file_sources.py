"""Reusable Streamlit widgets for upload/data-dir/path file selection."""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Any, Sequence

import streamlit as st


@dataclasses.dataclass(frozen=True)
class FileSourceSelection:
    """A selected file from upload, configured data directory, or explicit path."""

    value: Any = None
    source: str = "none"
    path: pathlib.Path | None = None

    @property
    def is_selected(self) -> bool:
        return self.value is not None


def list_server_files(
    data_dir: pathlib.Path,
    *,
    suffixes: Sequence[str],
    name_contains: Sequence[str] = (),
) -> list[pathlib.Path]:
    """List matching files directly below a server-side data directory."""
    if not data_dir.exists() or not data_dir.is_dir():
        return []
    suffixes_lower = tuple(suffix.casefold() for suffix in suffixes)
    contains_lower = tuple(part.casefold() for part in name_contains)
    return sorted(
        path
        for path in data_dir.iterdir()
        if path.is_file()
        and path.suffix.casefold() in suffixes_lower
        and all(part in path.name.casefold() for part in contains_lower)
    )


def render_file_source_selector(
    label: str,
    *,
    key: str,
    data_dir: pathlib.Path,
    suffixes: Sequence[str],
    upload_types: Sequence[str] | None = None,
    default_source: str = "Upload",
    name_contains: Sequence[str] = (),
    help: str | None = None,
) -> FileSourceSelection:
    """Render Upload / Data directory / Server path controls for one file."""
    options = ["Upload", "Data directory", "Server path"]
    if default_source not in options:
        default_source = "Upload"
    source = st.segmented_control(
        label,
        options=options,
        default=default_source,
        key=f"{key}_source",
        help=help,
        width="stretch",
    ) or default_source

    if source == "Upload":
        uploaded = st.file_uploader(
            f"Upload {label}",
            type=list(upload_types or _upload_types_from_suffixes(suffixes)),
            key=f"{key}_upload",
        )
        return FileSourceSelection(value=uploaded, source="upload", path=None)

    if source == "Data directory":
        candidates = list_server_files(
            data_dir,
            suffixes=suffixes,
            name_contains=name_contains,
        )
        if not candidates:
            st.info(f"No matching files found in `{data_dir}`.")
            return FileSourceSelection(source="data_dir")
        selected = st.selectbox(
            f"Select {label} from data directory",
            options=[None] + candidates,
            format_func=lambda path: "None" if path is None else path.name,
            key=f"{key}_data_dir_select",
        )
        return FileSourceSelection(value=selected, source="data_dir", path=selected)

    path_text = st.text_input(
        f"{label} path on this server",
        value="",
        key=f"{key}_path_text",
        help="Use an absolute path when the file is outside the configured data directory.",
    )
    if not path_text.strip():
        return FileSourceSelection(source="path")
    path = pathlib.Path(path_text).expanduser()
    if not path.exists():
        st.error(f"File does not exist on the Streamlit server: `{path}`")
        return FileSourceSelection(source="path", path=path)
    if not path.is_file():
        st.error(f"Path is not a file: `{path}`")
        return FileSourceSelection(source="path", path=path)
    return FileSourceSelection(value=path, source="path", path=path)


def _upload_types_from_suffixes(suffixes: Sequence[str]) -> tuple[str, ...]:
    return tuple(suffix.lstrip(".") for suffix in suffixes)
