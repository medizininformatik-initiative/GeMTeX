"""Sanitization-suggestion tab for the Streamlit GUI."""

from __future__ import annotations

import datetime
import pathlib
import tempfile
import time

import streamlit as st

from snomed_post_processing.findings_io import read_critical_findings_json
from snomed_post_processing.hdf5_handling.metadata import inspect_hdf5_metadata
from snomed_post_processing.sanitization import (
    ASSOCIATION_TYPE_DESCRIPTIONS,
    DEFAULT_ALLOWED_ASSOCIATION_TYPES,
    SUPPORTED_ASSOCIATION_TYPES,
    SanitizationResolver,
    apply_semantic_bm25_fallback,
    build_snogit_sidecar,
    format_association_type_descriptions,
    list_snogit_zip_members,
    sanitization_suggestions_json_text,
    write_sanitization_markdown_report,
)

from .downloads import download_json_report, download_md_report
from .file_sources import list_server_files, render_file_source_selector
from .files import save_uploaded_file
from .sidebar import GuiInputs


def _format_association_type_option(association_type: str) -> str:
    description = ASSOCIATION_TYPE_DESCRIPTIONS.get(association_type)
    if description:
        return f"{association_type} — {description}"
    return association_type


def render_sanitization_check_tab(inputs: GuiInputs) -> None:
    if inputs.target_view == "release":
        st.info(
            "Release-view normalization suggestions are planned next. They will reuse this review/apply workflow, "
            "but replacement candidates will only need to be active in the release and optionally not blacklisted."
        )
    st.write(
        "Generate sanitization suggestions from CriticalFindings JSON produced by "
        "the check step. Policy suggestions target the same materialized HDF5 "
        "policy/view date used for checking."
    )
    session_findings_available = st.session_state.get("critical_findings") is not None
    uploaded_findings_file = None
    if session_findings_available:
        findings_source = st.segmented_control(
            "CriticalFindings source",
            options=["Current session", "Upload JSON"],
            default="Current session",
            key="sanitization_findings_source",
            help=(
                "Use findings produced by the check step in this browser session, "
                "or upload a saved CriticalFindings JSON file."
            ),
            width="stretch",
        ) or "Current session"
        use_session_findings = findings_source == "Current session"
    else:
        use_session_findings = False
        st.info(
            "No CriticalFindings are available in the current session. Upload a "
            "CriticalFindings JSON file or run the check step first."
        )

    if not use_session_findings:
        findings_selection = render_file_source_selector(
            "CriticalFindings JSON",
            key="critical_findings_json",
            data_dir=inputs.data_dir,
            suffixes=(".json",),
            upload_types=("json",),
            default_source="Upload",
            help="Load a CriticalFindings JSON file, or run the policy check in this session first.",
        )
        uploaded_findings_file = findings_selection.value

    st.subheader("Settings")
    fallback_col1, fallback_col2 = st.columns(2)
    with fallback_col1:
        activate_historical_ancestor_fallback = st.checkbox(
            "Historical ancestor fallback",
            value=False,
            help=(
                "For unresolved whitelist findings: try nearest active whitelisted "
                "ancestor, then nearest active whitelisted ancestor reachable "
                "through stored inactive is-a fallback edges."
            ),
        )
    sanitize_blacklist_suggestions = False
    with fallback_col2:
        sanitize_semantic_bm25_fallback = st.checkbox(
            "Semantic BM25 fallback",
            value=False,
            help="Suggest lexically similar active concepts for unresolved findings.",
        )
        if inputs.target_view == "policy" or inputs.release_blacklist_mode != "none":
            sanitize_blacklist_suggestions = st.checkbox(
                "Include blacklist findings in BM25 fallback",
                value=False,
                disabled=not sanitize_semantic_bm25_fallback,
                help=(
                    "This only affects semantic BM25 fallback candidates. Enable "
                    "'Semantic BM25 fallback' first. Historical ancestor fallback "
                    "does not resolve blacklist findings."
                ),
            )
            if not sanitize_semantic_bm25_fallback:
                st.caption("Enable Semantic BM25 fallback to include blacklist findings.")

    use_snogit_bm25 = False
    snogit_sidecar_file = None
    snogit_zip_file = None
    snogit_sidecar_path_text = ""
    snogit_zip_path_text = ""
    selected_snogit_cache_from_dir = None
    selected_snogit_zip_from_dir = None
    selected_snogit_members = []

    with st.popover("Advanced suggestion settings"):
        st.markdown("#### Historical associations")
        sanitization_association_types = st.multiselect(
            "Allowed historical association types",
            options=list(SUPPORTED_ASSOCIATION_TYPES),
            default=list(DEFAULT_ALLOWED_ASSOCIATION_TYPES),
            format_func=_format_association_type_option,
            help=(
                "Choose which RF2 historical association types may propose "
                "replacement candidates. Short explanations are shown in the "
                "dropdown labels and listed below."
            ),
        )
        st.caption("Association type explanations are listed below.")
        st.markdown("#### Ancestor fallback limits")
        use_absolute_ancestor_limit = st.checkbox(
            "Use absolute ancestor distance limit",
            value=True,
            disabled=not activate_historical_ancestor_fallback,
        )
        ancestor_max_distance = st.number_input(
            "Maximum absolute ancestor distance",
            min_value=1,
            max_value=20,
            value=3,
            step=1,
            disabled=(
                not activate_historical_ancestor_fallback
                or not use_absolute_ancestor_limit
            ),
        )
        use_relative_ancestor_limit = st.checkbox(
            "Use relative ancestor distance limit",
            value=True,
            disabled=not activate_historical_ancestor_fallback,
        )
        ancestor_max_relative_distance = st.number_input(
            "Maximum relative ancestor distance",
            min_value=0.0,
            max_value=1.0,
            value=0.35,
            step=0.05,
            disabled=(
                not activate_historical_ancestor_fallback
                or not use_relative_ancestor_limit
            ),
            help=(
                "Distance divided by source depth-to-root. Lower values reject "
                "broader jumps in shallow hierarchies."
            ),
        )
        st.markdown("#### BM25 thresholds")
        sanitize_bm25_min_score = st.number_input(
            "Minimum BM25 score", min_value=0.0, value=1.5, step=0.1
        )
        sanitize_bm25_min_lexical_score = st.number_input(
            "Minimum lexical overlap ratio",
            min_value=0.0,
            max_value=1.0,
            value=0.15,
            step=0.05,
        )
        sanitize_bm25_max_candidates = st.number_input(
            "Maximum retained candidates", min_value=1, max_value=50, value=5, step=1
        )
        st.markdown("#### Optional SNOGIT/interface terms")
        use_snogit_bm25 = st.checkbox(
            "Use SNOGIT/interface terms for BM25 candidates",
            value=False,
            disabled=not sanitize_semantic_bm25_fallback,
            help=(
                "Use a processed SNOGIT cache if available. This can be a cache downloaded/saved from a previous run. "
                "If no cache is available, create one from SNOGIT-release.zip first; suggestion generation starts only after you explicitly run it with a cache."
            ),
        )
        if use_snogit_bm25:
            snogit_cache_selection = render_file_source_selector(
                "Processed SNOGIT cache HDF5",
                key="snogit_cache_hdf5",
                data_dir=inputs.data_dir,
                suffixes=(".hdf5", ".h5"),
                upload_types=("hdf5", "h5"),
                default_source="Data directory",
                name_contains=("snogit",),
                help="Use a compatible processed SNOGIT cache. This defaults to server-side data-directory selection for large cache files.",
            )
            selected_snogit_cache_from_dir = snogit_cache_selection.path if snogit_cache_selection.source in {"data_dir", "path"} else None
            snogit_sidecar_file = snogit_cache_selection.value if snogit_cache_selection.source == "upload" else None
            snogit_sidecar_path_text = str(snogit_cache_selection.path) if snogit_cache_selection.source == "path" and snogit_cache_selection.path is not None else ""

            snogit_zip_selection = render_file_source_selector(
                "SNOGIT release ZIP for processed cache creation",
                key="snogit_release_zip",
                data_dir=inputs.data_dir,
                suffixes=(".zip",),
                upload_types=("zip",),
                default_source="Data directory",
                name_contains=("snogit",),
                help="Use this only to create a processed SNOGIT cache first. Suggestion generation will not start automatically after cache creation.",
            )
            selected_snogit_zip_from_dir = snogit_zip_selection.path if snogit_zip_selection.source in {"data_dir", "path"} else None
            snogit_zip_file = snogit_zip_selection.value if snogit_zip_selection.source == "upload" else None
            snogit_zip_path_text = str(snogit_zip_selection.path) if snogit_zip_selection.source == "path" and snogit_zip_selection.path is not None else ""

            snogit_sidecar_path_candidate = selected_snogit_cache_from_dir
            snogit_zip_path_candidate = selected_snogit_zip_from_dir
            if (snogit_zip_file is not None or snogit_zip_path_candidate is not None) and snogit_sidecar_file is None and snogit_sidecar_path_candidate is None:
                try:
                    snogit_zip_temp_path = snogit_zip_path_candidate or save_uploaded_file(snogit_zip_file, ".zip")
                    snogit_members = list_snogit_zip_members(snogit_zip_temp_path)
                    default_members = [member.name for member in snogit_members if member.recommended_default]
                    selected_snogit_members = st.multiselect(
                        "SNOGIT ZIP members",
                        options=[member.name for member in snogit_members],
                        default=default_members,
                        help=(
                            "Default is the newest general SNOGIT_*.dat member only. "
                            "ELGA and Latin files can be selected explicitly."
                        ),
                    )
                    if default_members:
                        st.caption(f"Default general SNOGIT member: {default_members[0]}")
                except Exception as exc:
                    st.warning(f"Could not inspect SNOGIT ZIP members: {exc}")
        st.divider()
        st.markdown("#### Association type meanings")
        st.text(format_association_type_descriptions())

    selected_snogit_cache_path = None
    invalid_snogit_cache_path = None
    if use_snogit_bm25 and selected_snogit_cache_from_dir is not None:
        if selected_snogit_cache_from_dir.exists():
            selected_snogit_cache_path = selected_snogit_cache_from_dir
        else:
            invalid_snogit_cache_path = selected_snogit_cache_from_dir
            st.error(f"Selected processed SNOGIT cache no longer exists: `{selected_snogit_cache_from_dir}`")
    elif use_snogit_bm25 and snogit_sidecar_path_text.strip():
        typed_cache_path = pathlib.Path(snogit_sidecar_path_text).expanduser()
        if typed_cache_path.exists():
            selected_snogit_cache_path = typed_cache_path
        else:
            invalid_snogit_cache_path = typed_cache_path
            st.error(
                "Processed SNOGIT cache path does not exist on the Streamlit server: "
                f"`{typed_cache_path}`. Use an absolute path if the file is outside the app working directory."
            )

    created_snogit_cache_path = st.session_state.get("created_snogit_cache_path")
    if use_snogit_bm25 and created_snogit_cache_path:
        created_path = pathlib.Path(created_snogit_cache_path)
        if created_path.exists():
            if selected_snogit_cache_path is None:
                selected_snogit_cache_path = created_path
            st.success(f"Processed SNOGIT cache ready: {created_path}")
            st.download_button(
                label="Download processed SNOGIT cache HDF5",
                data=created_path.read_bytes(),
                file_name=created_path.name,
                mime="application/x-hdf5",
                key="download_created_snogit_cache",
            )
        else:
            st.warning(
                "Previously created processed SNOGIT cache is no longer available: "
                f"`{created_path}`. Please create or select the cache again."
            )
            st.session_state.pop("created_snogit_cache_path", None)
            created_snogit_cache_path = None

    snogit_cache_available = snogit_sidecar_file is not None or selected_snogit_cache_path is not None
    snogit_zip_available = (snogit_zip_file is not None or selected_snogit_zip_from_dir is not None or bool(snogit_zip_path_text.strip())) and bool(selected_snogit_members)
    snogit_ready = not use_snogit_bm25 or snogit_cache_available
    if use_snogit_bm25 and not snogit_cache_available:
        st.info(
            "To use SNOGIT BM25 candidates, provide a processed SNOGIT cache or create one from a SNOGIT ZIP first. "
            "Creating the cache does not automatically start suggestion generation."
        )

    if use_snogit_bm25 and not snogit_cache_available and snogit_zip_available:
        if st.button(
            "Create processed SNOGIT cache",
            disabled=inputs.target_view != "policy" or not inputs.hdf5_file,
        ):
            try:
                with st.status("Creating processed SNOGIT cache...", expanded=True) as cache_status:
                    st.write("Preparing HDF5 input...")
                    if inputs.hdf5_temp_path is None:
                        inputs.hdf5_temp_path = save_uploaded_file(inputs.hdf5_file, ".hdf5")
                    st.write("Preparing SNOGIT ZIP input...")
                    if selected_snogit_zip_from_dir is not None:
                        snogit_zip_path = selected_snogit_zip_from_dir
                    elif snogit_zip_path_text.strip():
                        snogit_zip_path = pathlib.Path(snogit_zip_path_text).expanduser()
                    else:
                        snogit_zip_path = save_uploaded_file(snogit_zip_file, ".zip")
                    output_dir_for_sidecar = pathlib.Path(
                        tempfile.mkdtemp(prefix="snomed_gui_snogit_cache_")
                    )
                    timestamp_for_sidecar = datetime.datetime.now().strftime('%d-%m-%Y_%H-%M')
                    snogit_sidecar_path = output_dir_for_sidecar / f"snogit_cache_{timestamp_for_sidecar}.hdf5"
                    st.write("Parsing/filtering selected SNOGIT member(s) and writing cache...")
                    cache_progress = st.progress(0.0, text="Starting processed SNOGIT cache creation...")

                    def update_cache_progress(update: dict[str, object]) -> None:
                        phase = str(update.get("phase", "processing"))
                        progress_value = float(update.get("progress", 0.0) or 0.0)
                        progress_value = max(0.0, min(1.0, progress_value))
                        rows_read = int(update.get("rows_read", 0) or 0)
                        rows_written = int(update.get("rows_written", 0) or 0)
                        member = update.get("member")
                        if phase == "parsing":
                            label = (
                                f"Parsing {member or 'selected SNOGIT member(s)'} — "
                                f"{progress_value:.1%} · {rows_read:,} row(s) read · "
                                f"{rows_written:,} term row(s) written"
                            )
                        elif phase == "writing_index":
                            label = (
                                "Writing HDF5 inverted BM25 index — "
                                f"{rows_written:,} term row(s)"
                            )
                        elif phase == "complete":
                            label = (
                                "Processed SNOGIT cache complete — "
                                f"{rows_written:,} term row(s) written"
                            )
                        else:
                            label = "Starting processed SNOGIT cache creation..."
                        cache_progress.progress(progress_value, text=label)

                    build_result = build_snogit_sidecar(
                        hdf5_path=inputs.hdf5_temp_path,
                        snogit_zip_path=snogit_zip_path,
                        output_path=snogit_sidecar_path,
                        members=selected_snogit_members,
                        progress_callback=update_cache_progress,
                    )
                    st.write(
                        "Processed SNOGIT cache built: "
                        f"{build_result.rows_written:,} term row(s) written."
                    )
                    cache_status.update(
                        label="Processed SNOGIT cache created.",
                        state="complete",
                        expanded=False,
                    )
                st.session_state["created_snogit_cache_path"] = str(snogit_sidecar_path)
                selected_snogit_cache_path = snogit_sidecar_path
                snogit_cache_available = True
                snogit_ready = True
                st.success("Processed SNOGIT cache created. You can download it or start suggestion generation now.")
                st.download_button(
                    label="Download processed SNOGIT cache HDF5",
                    data=snogit_sidecar_path.read_bytes(),
                    file_name=snogit_sidecar_path.name,
                    mime="application/x-hdf5",
                    key="download_new_snogit_cache",
                )
            except Exception as exc:
                st.error(f"Processed SNOGIT cache creation failed: {exc}")

    if st.button(
        "Generate sanitization suggestions",
        type="primary",
        disabled=inputs.target_view != "policy" or not inputs.hdf5_file or not (use_session_findings or uploaded_findings_file) or not snogit_ready,
    ):
        try:
            with st.status(
                "Generating sanitization suggestions...",
                expanded=True,
            ) as status:
                st.write("Preparing HDF5 and CriticalFindings inputs...")
                if inputs.hdf5_temp_path is None:
                    inputs.hdf5_temp_path = save_uploaded_file(inputs.hdf5_file, ".hdf5")
                hdf5_summary = inspect_hdf5_metadata(inputs.hdf5_temp_path)
                st.write(
                    "Using HDF5 materialized view: "
                    f"release date {hdf5_summary.concepts_release_date or 'unknown'}, "
                    f"policy/view date {hdf5_summary.concepts_policy_date or 'unknown'}."
                )
                if use_session_findings:
                    findings = st.session_state["critical_findings"]
                else:
                    findings_path = save_uploaded_file(uploaded_findings_file, ".json")
                    findings = read_critical_findings_json(findings_path)

                st.write("Creating resolver and loading SNOMED lookup data...")
                resolver = SanitizationResolver(
                    inputs.hdf5_temp_path,
                    allowed_association_types=sanitization_association_types
                    or list(DEFAULT_ALLOWED_ASSOCIATION_TYPES),
                    activate_historical_ancestor_fallback=activate_historical_ancestor_fallback,
                    ancestor_max_distance=(
                        int(ancestor_max_distance) if use_absolute_ancestor_limit else None
                    ),
                    ancestor_max_relative_distance=(
                        float(ancestor_max_relative_distance)
                        if use_relative_ancestor_limit
                        else None
                    ),
                )
                st.write(
                    f"Resolving historical association candidates for {len(findings)} finding(s)..."
                )
                sanitization_progress = st.progress(
                    0.25,
                    text=(
                        f"Resolving historical-association suggestions for "
                        f"{len(findings)} finding(s)..."
                    ),
                )
                suggestions = resolver.suggest_all(findings)
                snogit_sidecar_path = None
                if sanitize_semantic_bm25_fallback and use_snogit_bm25:
                    if snogit_sidecar_file is not None:
                        st.write("Using uploaded processed SNOGIT cache...")
                        snogit_sidecar_path = save_uploaded_file(snogit_sidecar_file, ".hdf5")
                    elif selected_snogit_cache_path is not None:
                        st.write("Using selected processed SNOGIT cache...")
                        snogit_sidecar_path = selected_snogit_cache_path
                    if snogit_sidecar_path is not None and not pathlib.Path(snogit_sidecar_path).exists():
                        raise FileNotFoundError(
                            "Processed SNOGIT cache does not exist on the Streamlit server: "
                            f"{snogit_sidecar_path}. Select an existing cache or create it again."
                        )
                if sanitize_semantic_bm25_fallback:
                    st.write("Running semantic BM25 fallback for unresolved findings...")
                    sanitization_progress.empty()
                    sanitization_progress = st.progress(
                        0.65, text="Running semantic BM25 fallback suggestions..."
                    )
                    suggestions = apply_semantic_bm25_fallback(
                        suggestions,
                        inputs.hdf5_temp_path,
                        min_score=sanitize_bm25_min_score,
                        min_lexical_score=sanitize_bm25_min_lexical_score,
                        max_candidates=int(sanitize_bm25_max_candidates),
                        allow_blacklist_findings=sanitize_blacklist_suggestions,
                        snogit_sidecar_path=snogit_sidecar_path,
                    )
                st.write("Writing Markdown and JSON suggestion reports...")
                sanitization_progress.empty()
                sanitization_progress = st.progress(
                    0.9, text="Writing sanitization suggestion report..."
                )
                output_dir = pathlib.Path(
                    tempfile.mkdtemp(prefix="snomed_gui_sanitization_")
                )
                timestamp = datetime.datetime.now().strftime('%d-%m-%Y_%H-%M')
                output_sanitization_md = output_dir / f"sanitization_suggestions_{timestamp}.md"
                output_sanitization_json = output_dir / f"sanitization_suggestions_{timestamp}.json"
            sanitization_settings = {
                "target_view": inputs.target_view,
                "release_blacklist_mode": inputs.release_blacklist_mode,
                "allowed_association_types": list(
                    sanitization_association_types or DEFAULT_ALLOWED_ASSOCIATION_TYPES
                ),
                "historical_ancestor_fallback": bool(activate_historical_ancestor_fallback),
                "ancestor_max_distance": int(ancestor_max_distance) if use_absolute_ancestor_limit else None,
                "ancestor_max_relative_distance": (
                    float(ancestor_max_relative_distance) if use_relative_ancestor_limit else None
                ),
                "semantic_bm25_fallback": bool(sanitize_semantic_bm25_fallback),
                "blacklist_bm25_suggestions": bool(sanitize_blacklist_suggestions),
                "bm25_min_score": float(sanitize_bm25_min_score),
                "bm25_min_lexical_score": float(sanitize_bm25_min_lexical_score),
                "bm25_max_candidates": int(sanitize_bm25_max_candidates),
                "snogit_bm25": bool(use_snogit_bm25),
                "snogit_members": list(selected_snogit_members),
                "snogit_cache_path": str(snogit_sidecar_path) if snogit_sidecar_path is not None else None,
            }
            sanitization_metadata = {
                "source": "streamlit_sanitization_check_tab",
                "hdf5_file_name": getattr(inputs.hdf5_file, "name", None),
                "hdf5_release_date": hdf5_summary.concepts_release_date,
                "hdf5_policy_date": hdf5_summary.concepts_policy_date,
                "hdf5_rf2_view": hdf5_summary.concepts_rf2_view,
                "finding_count": len(findings),
                "suggestion_count": len(suggestions),
                "settings": sanitization_settings,
            }
            with output_sanitization_md.open("w", encoding="utf-8") as sanitization_fi:
                write_sanitization_markdown_report(suggestions, sanitization_fi)
            sanitization_json_text = sanitization_suggestions_json_text(
                suggestions,
                metadata=sanitization_metadata,
            )
            output_sanitization_json.write_text(sanitization_json_text + "\n", encoding="utf-8")
            sanitization_progress.progress(
                1.0, text="Sanitization suggestions finished."
            )
            time.sleep(0.2)
            sanitization_progress.empty()
            status.update(
                label="Sanitization suggestions finished.",
                state="complete",
                expanded=False,
            )

            st.session_state["sanitization_suggestions"] = suggestions
            st.session_state["sanitization_suggestions_metadata"] = sanitization_metadata
            st.session_state["sanitization_suggestions_report_path"] = str(output_sanitization_md)
            st.session_state["sanitization_suggestions_json_path"] = str(output_sanitization_json)

            sanitization_report_text = output_sanitization_md.read_text(encoding="utf-8")
            st.success("Sanitization suggestions finished.")

            download_json_report(sanitization_json_text, output_sanitization_json, "sanitization suggestion")

            st.subheader("Reports")
            download_md_report(
                sanitization_report_text,
                output_sanitization_md,
                "sanitization suggestions markdown",
            )
            with st.expander("Preview sanitization suggestion report", expanded=True):
                st.markdown(sanitization_report_text)
        except Exception as exc:
            st.error(f"Sanitization suggestion generation failed: {exc}")
