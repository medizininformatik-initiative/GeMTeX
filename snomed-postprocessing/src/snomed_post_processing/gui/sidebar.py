"""Sidebar input controls for the Streamlit GUI."""

from __future__ import annotations

import dataclasses
import pathlib
import tempfile
from typing import Any

import streamlit as st

from snomed_post_processing.inception import get_project_zip


@dataclasses.dataclass
class GuiInputs:
    load_annotators: bool
    hdf5_file: Any
    annotation_types_text: str
    ignore_overlap_types_text: str
    ignore_overlap_mode: str
    target_view: str = "policy"
    release_blacklist_mode: str = "none"
    runtime_blacklist_file: Any = None
    hdf5_temp_path: pathlib.Path | None = None


def render_sidebar() -> GuiInputs:
    with st.sidebar:
        st.header("Inputs")
        load_annotators = st.checkbox("Load annotators from ZIP", value=True)
        use_api = st.toggle("Use INCEpTION API", value=False)
        if use_api:
            _render_inception_api_controls()
        else:
            st.session_state["zip_file"] = st.file_uploader(
                "INCEpTION project ZIP", type=["zip"]
            )

        hdf5_file = st.file_uploader("SNOMED HDF5", type=["hdf5"])

        st.header("Target")
        target_view = _render_target_view_selector()
        release_blacklist_mode = "none"
        runtime_blacklist_file = None
        if target_view == "release":
            release_blacklist_mode, runtime_blacklist_file = (
                _render_release_blacklist_selector()
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
            "ignored; blacklist is optional. Planned workflow."
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
        st.info("Release-view execution is scaffolded but not enabled yet.", icon="ℹ️")
        return "release"
    return "policy"


def _render_release_blacklist_selector() -> tuple[str, Any]:
    blacklist_options = {
        "No blacklist": "Accept every active concept in the release.",
        "Embedded blacklist": (
            "Exclude concepts already stored in the HDF5 blacklist view."
        ),
        "Upload rules": "Upload blacklist rules to resolve at runtime. Planned.",
    }
    selected_blacklist = st.pills(
        "Release blacklist",
        options=list(blacklist_options),
        default="No blacklist",
        key="release_blacklist_selector",
        help=(
            "Blacklist files are line-separated: numeric lines exclude a concept and descendants; "
            "non-numeric lines exclude by FSN semantic tag."
        ),
        width="stretch",
    ) or "No blacklist"
    st.caption(blacklist_options[selected_blacklist])

    if selected_blacklist == "Embedded blacklist":
        return "embedded", None
    if selected_blacklist == "Upload rules":
        runtime_blacklist_file = st.file_uploader(
            "Runtime blacklist rule file", type=["txt"]
        )
        st.caption(
            "Runtime blacklist calculation is planned; embedded HDF5 blacklist is "
            "the first supported release blacklist source."
        )
        return "runtime", runtime_blacklist_file
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
