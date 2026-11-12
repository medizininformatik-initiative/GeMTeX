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
    id_prefix: str
    id_feature: str
    data_dir: pathlib.Path
    target_view: str = "policy"
    release_blacklist_mode: str = "none"
    runtime_blacklist_file: Any = None
    hdf5_temp_path: pathlib.Path | None = None
    annotators: tuple[str, ...] = ()


def render_sidebar() -> GuiInputs:
    # Decisions are loaded after sidebar widgets have rendered. Apply their ID
    # settings on the next rerun, before instantiating the bound widgets.
    for key, value in st.session_state.pop("sanitization_pending_id_settings", {}).items():
        st.session_state[key] = value
    with st.sidebar:
        st.header("Inputs")
        load_annotators = st.checkbox(
            "Load annotators from ZIP", value=True,
            help="Read annotator names for the shared selection in tab 1. That scope applies to checking, rules, suggestions, review and export/upload.",
        )
        use_api = st.toggle(
            "Use INCEpTION API", value=False,
            help="Load the source project from INCEpTION instead of selecting a project ZIP.",
        )
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

        st.header("Replacement requirements")
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
                help="One full UIMA type name per line. Used by policy checks and concept rules.",
            )
            ignore_overlap_types_text = st.text_area(
                "Ignore faulty target annotations overlapping these types",
                value="",
                help=(
                    "One UIMA layer/type per line. Faulty target annotations overlapping these layers "
                    "are reported separately and excluded from the critical count. "
                    "No ignore layer is selected by default. To ignore No_Human annotations, "
                    "add webanno.custom.No_Human explicitly."
                ),
            )
            ignore_overlap_mode = st.selectbox(
                "Ignore overlap mode",
                options=["overlap", "covered-by", "contains", "exact"],
                index=0,
                help=(
                    "overlap: any shared span; covered-by: target is inside the ignore span; "
                    "contains: target encloses the ignore span; exact: identical boundaries."
                ),
            )
            id_feature = st.text_input(
                "SNOMED ID feature name",
                value=st.session_state.get("snomed_annotation_id_feature", "id"),
                key="snomed_annotation_id_feature",
                help="Name of the string feature on the target annotation layer that stores the SNOMED CT ID/SCTID.",
            )
            id_prefix = st.text_input(
                "SNOMED ID prefix in annotation feature",
                value=st.session_state.get("snomed_annotation_id_prefix", "http://snomed.info/id/"),
                key="snomed_annotation_id_prefix",
                help=(
                    "Prefix used before the SCTID in the configured ID feature. "
                    "For plain SCTIDs, leave this empty. The same prefix is used when writing replacement IDs."
                ),
            )

    return GuiInputs(
        load_annotators=load_annotators,
        hdf5_file=hdf5_file,
        annotation_types_text=annotation_types_text,
        ignore_overlap_types_text=ignore_overlap_types_text,
        ignore_overlap_mode=ignore_overlap_mode,
        id_prefix=id_prefix,
        id_feature=id_feature,
        data_dir=data_dir,
        target_view=target_view,
        release_blacklist_mode=release_blacklist_mode,
        runtime_blacklist_file=runtime_blacklist_file,
        annotators=tuple(st.session_state.get("processing_annotators", ())),
    )


def _render_target_view_selector() -> str:
    target_options = {
        "Policy rules": (
            "Active concepts in the inclusion list and outside the exclusion list."
        ),
        "Active release": (
            "Any active concept; inclusion-list membership is not required. Exclusion lists are optional."
        ),
    }
    selected_target = st.segmented_control(
        "Allowed replacement concepts",
        options=list(target_options),
        default="Policy rules",
        key="target_view_selector",
        help="Choose which concepts may be suggested as replacements. Tab 1 always checks inclusion/exclusion policy.",
        width="stretch",
    ) or "Policy rules"
    st.caption(target_options[selected_target])
    if selected_target == "Active release":
        return "release"
    return "policy"


def _render_release_blacklist_selector(data_dir: pathlib.Path) -> tuple[str, Any]:
    enforce_embedded = st.checkbox(
        "Enforce embedded HDF5 exclusion list",
        value=False,
        help=(
            "If enabled, release-view suggestions exclude active concepts listed in the embedded HDF5 exclusion list. "
            "By default, release view ignores the embedded exclusion list."
        ),
    )
    use_custom_blacklist = st.checkbox(
        "Use custom exclusion-list rule file",
        value=False,
        help=(
            "If enabled, release-view suggestions exclude concepts matched by a custom exclusion-list rule file. "
            "Numeric lines exclude a concept and descendants; non-numeric lines exclude by FSN semantic tag."
        ),
    )
    runtime_blacklist_file = None
    if use_custom_blacklist:
        runtime_blacklist_selection = render_file_source_selector(
            "Custom exclusion-list rule file",
            key="custom_blacklist_rule_file",
            data_dir=data_dir,
            suffixes=(".txt",),
            upload_types=("txt",),
            default_source="Upload",
            help="Exclusion-list rule files are usually small, but upload, data-directory, and server-path modes are available.",
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
            "INCEpTION API URL", value=st.session_state["api_credentials"]["url"],
            help="Base URL of the INCEpTION server, including any deployment path.",
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
        submitted = st.form_submit_button(
            "Get Projects", help="Connect to INCEpTION and list projects available to this account.",
        )
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
            "Select project", st.session_state["projects"], index=None,
            help="Selecting a project downloads its export ZIP for local processing.",
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
