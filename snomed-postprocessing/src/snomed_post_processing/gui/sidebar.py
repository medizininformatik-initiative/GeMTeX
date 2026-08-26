"""Sidebar input controls for the Streamlit GUI."""

from __future__ import annotations

import dataclasses
import pathlib
import tempfile
from typing import Any

import streamlit as st

from snomed_post_processing.inception import get_project_zip

from .file_sources import render_file_source_selector


@dataclasses.dataclass
class GuiInputs:
    load_annotators: bool
    hdf5_file: Any
    annotation_types_text: str
    ignore_overlap_types_text: str
    ignore_overlap_mode: str
    data_dir: pathlib.Path
    target_view: str = "policy"
    release_blacklist_mode: str = "none"
    runtime_blacklist_file: Any = None
    hdf5_temp_path: pathlib.Path | None = None


def render_sidebar() -> GuiInputs:
    with st.sidebar:
        st.header("Inputs")
        load_annotators = st.checkbox("Load annotators from ZIP", value=True)
        use_api = st.toggle("Use INCEpTION API", value=False)
        st.header("Server-side files")
        data_dir = pathlib.Path(
            st.text_input(
                "Data directory",
                value=st.session_state.get("server_data_dir", "data"),
                help="Directory on the Streamlit server used to list large HDF5/ZIP files without browser upload.",
            )
        ).expanduser()
        st.session_state["server_data_dir"] = str(data_dir)
        if data_dir.exists() and data_dir.is_dir():
            st.caption(f"Using server data directory: `{data_dir.resolve()}`")
        else:
            st.warning(f"Server data directory not found: `{data_dir}`")

        if use_api:
            _render_inception_api_controls()
        else:
            project_selection = render_file_source_selector(
                "INCEpTION project ZIP",
                key="inception_project_zip",
                data_dir=data_dir,
                suffixes=(".zip",),
                upload_types=("zip",),
                default_source="Upload",
                help="Project ZIPs can be large; use data-directory or server-path mode if browser upload exceeds Streamlit limits.",
            )
            st.session_state["zip_file"] = project_selection.value

        hdf5_selection = render_file_source_selector(
            "SNOMED HDF5",
            key="snomed_hdf5",
            data_dir=data_dir,
            suffixes=(".hdf5", ".h5"),
            upload_types=("hdf5", "h5"),
            default_source="Upload",
            help="Use upload by default, or select a large HDF5 already present in the server data directory.",
        )
        hdf5_file = hdf5_selection.value

        st.header("Target")
        target_view = _render_target_view_selector()
        release_blacklist_mode = "none"
        runtime_blacklist_file = None
        if target_view == "release":
            release_blacklist_mode, runtime_blacklist_file = (
                _render_release_blacklist_selector(data_dir)
            )

        with st.expander("Annotation layers", expanded=False):
            annotation_types_text = st.text_area(
                "Target annotation types to check",
                value="gemtex.Concept\nwebanno.custom.Concept",
                help="One UIMA layer/type per line. Faulty SNOMED code checks run on these annotations.",
            )
            ignore_overlap_types_text = st.text_area(
                "Ignore faulty target annotations overlapping these types",
                value="webanno.custom.No_Human",
                help=(
                    "One UIMA layer/type per line. Faulty target annotations overlapping these layers "
                    "are reported separately and excluded from the critical count. Default: "
                    "webanno.custom.No_Human."
                ),
            )
            ignore_overlap_mode = st.selectbox(
                "Ignore overlap mode",
                options=["overlap", "covered-by", "contains", "exact"],
                index=0,
                help="Controls how target annotations must match ignore annotations to be ignored.",
            )

    return GuiInputs(
        load_annotators=load_annotators,
        hdf5_file=hdf5_file,
        annotation_types_text=annotation_types_text,
        ignore_overlap_types_text=ignore_overlap_types_text,
        ignore_overlap_mode=ignore_overlap_mode,
        data_dir=data_dir,
        target_view=target_view,
        release_blacklist_mode=release_blacklist_mode,
        runtime_blacklist_file=runtime_blacklist_file,
    )


def _render_target_view_selector() -> str:
    target_options = {
        "Policy rules": (
            "Use the embedded whitelist/blacklist policy views. Best for the current "
            "GeMTeX policy check and sanitization workflow."
        ),
        "Active release": (
            "Use active concepts from the selected SNOMED release. Whitelist is "
            "ignored; embedded and custom blacklists are optional."
        ),
    }
    selected_target = st.segmented_control(
        "Validation target",
        options=list(target_options),
        default="Policy rules",
        key="target_view_selector",
        help="Choose what makes an annotation acceptable.",
        width="stretch",
    ) or "Policy rules"
    st.caption(target_options[selected_target])
    if selected_target == "Active release":
        return "release"
    return "policy"


def _render_release_blacklist_selector(data_dir: pathlib.Path) -> tuple[str, Any]:
    enforce_embedded = st.checkbox(
        "Enforce embedded HDF5 blacklist",
        value=False,
        help=(
            "If enabled, release-view suggestions exclude active concepts listed in the embedded HDF5 blacklist. "
            "By default, release view ignores the embedded blacklist."
        ),
    )
    use_custom_blacklist = st.checkbox(
        "Use custom blacklist rule file",
        value=False,
        help=(
            "If enabled, release-view suggestions exclude rules from a custom blacklist file. "
            "Numeric lines exclude a concept and descendants; non-numeric lines exclude by FSN semantic tag."
        ),
    )
    runtime_blacklist_file = None
    if use_custom_blacklist:
        runtime_blacklist_selection = render_file_source_selector(
            "Custom blacklist rule file",
            key="custom_blacklist_rule_file",
            data_dir=data_dir,
            suffixes=(".txt",),
            upload_types=("txt",),
            default_source="Upload",
            help="Blacklist rule files are usually small, but upload, data-directory, and server-path modes are available.",
        )
        runtime_blacklist_file = runtime_blacklist_selection.value

    if enforce_embedded and use_custom_blacklist:
        return "embedded+custom", runtime_blacklist_file
    if enforce_embedded:
        return "embedded", runtime_blacklist_file
    if use_custom_blacklist:
        return "custom", runtime_blacklist_file
    st.caption("Release view default: accept every active concept in the release.")
    return "none", None


def _render_inception_api_controls() -> None:
    if "api_credentials" not in st.session_state:
        st.session_state["api_credentials"] = {
            "url": "http://localhost:8080",
            "username": "",
            "password": "",
        }

    with st.form("inception_api_form"):
        url = st.text_input(
            "INCEpTION API URL", value=st.session_state["api_credentials"]["url"]
        )
        username = st.text_input(
            "REMOTE Role Username",
            value=st.session_state["api_credentials"]["username"],
        )
        password = st.text_input(
            "REMOTE Role Password",
            type="password",
            value=st.session_state["api_credentials"]["password"],
        )
        submitted = st.form_submit_button("Get Projects")
        if submitted:
            st.session_state["api_credentials"] = {
                "url": url,
                "username": username,
                "password": password,
            }
            try:
                project_tmp = tempfile.mkdtemp("snomed_gui_dir")
                st.session_state["projects"] = get_project_zip(
                    project_tmp, url, username, password, None, False
                )
                st.success(f"Found {len(st.session_state['projects'])} projects.")
            except RuntimeError:
                st.error(
                    "Could not connect to INCEpTION API. Please check credentials and URL."
                )
                st.session_state.pop("api_credentials", None)
            except Exception as e:
                st.error(f"Error: {e}")
                st.session_state.pop("projects", None)

    if st.session_state.get("projects"):
        project = st.selectbox(
            "Select project", st.session_state["projects"], index=None
        )
        if project and (st.session_state.get("current_project") != project):
            st.session_state["current_project"] = project
            with st.spinner(f"Downloading project '{project}'..."):
                try:
                    project_tmp = tempfile.mkdtemp("snomed_gui_dir")
                    creds = st.session_state["api_credentials"]
                    project_zip = get_project_zip(
                        project_tmp,
                        creds["url"],
                        creds["username"],
                        creds["password"],
                        project,
                        False,
                    )
                    if isinstance(project_zip, pathlib.Path):
                        st.session_state["zip_file"] = project_zip
                    else:
                        st.error("Could not load project from INCEpTION API.")
                except Exception as e:
                    st.error(f"Error downloading project: {e}")
