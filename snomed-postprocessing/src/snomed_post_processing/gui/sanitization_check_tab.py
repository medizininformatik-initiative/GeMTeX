"""Sanitization-suggestion tab for the Streamlit GUI."""

from __future__ import annotations

import datetime
import pathlib
import tempfile
import time
from typing import Any

import h5py
import pandas as pd
import streamlit as st

from snomed_post_processing.findings_io import read_critical_findings_json
from snomed_post_processing.hdf5_handling.metadata import inspect_hdf5_metadata
from snomed_post_processing.hdf5_handling.policy import (
    read_blacklist_rule_file,
    resolve_blacklist_rule_indices,
)
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
from .sanitization_run_tab import _finding_context_label, _project_document_text_lookup
from .sidebar import GuiInputs


def _format_association_type_option(association_type: str) -> str:
    description = ASSOCIATION_TYPE_DESCRIPTIONS.get(association_type)
    if description:
        return f"{association_type} — {description}"
    return association_type


def _snogit_source_upload_suffix(uploaded_file: Any) -> str:
    suffix = pathlib.Path(str(getattr(uploaded_file, "name", ""))).suffix.lower()
    return suffix if suffix in {".zip", ".dat"} else ".zip"


def _snogit_cache_output_dir(data_dir: pathlib.Path) -> pathlib.Path:
    if data_dir.exists() and data_dir.is_dir():
        output_dir = data_dir / "generated-snogit-caches"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
    return pathlib.Path(tempfile.mkdtemp(prefix="snomed_gui_snogit_cache_"))


def _enforce_embedded_blacklist(release_blacklist_mode: str) -> bool:
    return release_blacklist_mode in {"embedded", "embedded+custom"}


def _uses_custom_blacklist(release_blacklist_mode: str) -> bool:
    return release_blacklist_mode in {"custom", "embedded+custom"}


def _suggestion_context_metadata(suggestions: list[Any]) -> list[dict[str, Any]]:
    document_texts = _project_document_text_lookup(st.session_state.get("zip_file"))
    if not document_texts:
        return []
    contexts = []
    for suggestion in suggestions:
        finding = getattr(suggestion, "finding", None)
        if finding is None:
            continue
        offset = tuple(getattr(finding, "offset", ()) or ())
        if len(offset) != 2:
            continue
        context = _finding_context_label(finding, document_texts)
        if not context or context.startswith("No full document context loaded:"):
            continue
        contexts.append(
            {
                "document": str(getattr(finding, "document", "") or ""),
                "annotator": str(getattr(finding, "annotator", "") or ""),
                "code": str(getattr(finding, "code", "") or ""),
                "offset": [int(offset[0]), int(offset[1])],
                "context": context,
            }
        )
    return contexts


def _prepare_custom_blacklist_path(runtime_blacklist_file: Any) -> pathlib.Path:
    if isinstance(runtime_blacklist_file, pathlib.Path):
        return runtime_blacklist_file
    if isinstance(runtime_blacklist_file, str):
        return pathlib.Path(runtime_blacklist_file).expanduser()
    return save_uploaded_file(runtime_blacklist_file, ".txt")


def _resolve_custom_blacklist_indices(
    hdf5_path: pathlib.Path,
    runtime_blacklist_file: Any,
) -> tuple[pathlib.Path, frozenset[int]]:
    custom_blacklist_path = _prepare_custom_blacklist_path(runtime_blacklist_file)
    with h5py.File(hdf5_path, "r") as h5_file:
        runtime_blacklist_indices = resolve_blacklist_rule_indices(
            h5_file,
            read_blacklist_rule_file(custom_blacklist_path),
        )
    return custom_blacklist_path, runtime_blacklist_indices


def render_sanitization_check_tab(inputs: GuiInputs) -> None:
    if inputs.target_view == "release":
        st.info(
            "Release-view normalization suggestions are enabled. Replacement candidates only need to be active "
            "in the release, unless the embedded and/or custom release blacklist is selected."
        )
    st.write(
        "Generate sanitization suggestions from CriticalFindings JSON produced by "
        "the check step. Policy suggestions target the same materialized HDF5 "
        "policy/view date used for checking; release suggestions target active release concepts."
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
    st.caption("Change settings inside the form, then apply them. This avoids rerunning the app for every checkbox or threshold edit.")
    with st.form("sanitization_suggestion_settings_form"):
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
            sanitize_blacklist_suggestions = st.checkbox(
                "Include blacklist findings in BM25 fallback",
                value=False,
                help=(
                    "This only affects semantic BM25 fallback candidates. If "
                    "Semantic BM25 fallback is off, this setting is saved but has no effect. "
                    "Historical ancestor fallback does not resolve blacklist findings."
                ),
            )

        use_snogit_bm25 = False
        snogit_sidecar_file = None
        snogit_source_file = None
        snogit_sidecar_path_text = ""
        snogit_source_path_text = ""
        selected_snogit_cache_from_dir = None
        selected_snogit_source_from_dir = None
        selected_snogit_members = []

        with st.expander("Advanced suggestion settings"):
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
                help="Used only when Historical ancestor fallback is enabled.",
            )
            ancestor_max_distance = st.number_input(
                "Maximum absolute ancestor distance",
                min_value=1,
                max_value=20,
                value=3,
                step=1,
                help="Used only when Historical ancestor fallback and absolute distance limiting are enabled.",
            )
            use_relative_ancestor_limit = st.checkbox(
                "Use relative ancestor distance limit",
                value=True,
                help="Used only when Historical ancestor fallback is enabled.",
            )
            ancestor_max_relative_distance = st.number_input(
                "Maximum relative ancestor distance",
                min_value=0.0,
                max_value=1.0,
                value=0.35,
                step=0.05,
                help=(
                    "Used only when Historical ancestor fallback and relative distance limiting are enabled. "
                    "Distance divided by source depth-to-root. Lower values reject broader jumps in shallow hierarchies."
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
                help=(
                    "Use a processed SNOGIT cache if available. This setting is used only when Semantic BM25 fallback is enabled. "
                    "If no cache is available, create one from a SNOGIT ZIP or .dat file first; suggestion generation starts only after you explicitly run it with a cache."
                ),
            )
            snogit_cache_selection = render_file_source_selector(
                "Processed SNOGIT cache HDF5",
                key="snogit_cache_hdf5",
                data_dir=inputs.data_dir,
                suffixes=(".hdf5", ".h5"),
                upload_types=("hdf5", "h5"),
                default_source="Data directory",
                # name_contains=("snogit",),
                help="Use a compatible processed SNOGIT cache. This defaults to server-side data-directory selection for large cache files.",
            )
            selected_snogit_cache_from_dir = snogit_cache_selection.path if snogit_cache_selection.source in {"data_dir", "path"} else None
            snogit_sidecar_file = snogit_cache_selection.value if snogit_cache_selection.source == "upload" else None
            snogit_sidecar_path_text = str(snogit_cache_selection.path) if snogit_cache_selection.source == "path" and snogit_cache_selection.path is not None else ""

            snogit_source_selection = render_file_source_selector(
                "SNOGIT ZIP or .dat source for processed cache creation",
                key="snogit_source",
                data_dir=inputs.data_dir,
                suffixes=(".zip", ".dat"),
                upload_types=("zip", "dat"),
                default_source="Data directory",
                # name_contains=("snogit",),
                help="Use this only to create a processed SNOGIT cache first. Suggestion generation will not start automatically after cache creation.",
            )
            selected_snogit_source_from_dir = snogit_source_selection.path if snogit_source_selection.source in {"data_dir", "path"} else None
            snogit_source_file = snogit_source_selection.value if snogit_source_selection.source == "upload" else None
            snogit_source_path_text = str(snogit_source_selection.path) if snogit_source_selection.source == "path" and snogit_source_selection.path is not None else ""

            snogit_sidecar_path_candidate = selected_snogit_cache_from_dir
            snogit_source_path_candidate = selected_snogit_source_from_dir
            if (snogit_source_file is not None or snogit_source_path_candidate is not None) and snogit_sidecar_file is None and snogit_sidecar_path_candidate is None:
                try:
                    snogit_source_temp_path = snogit_source_path_candidate or save_uploaded_file(snogit_source_file, _snogit_source_upload_suffix(snogit_source_file))
                    snogit_members = list_snogit_zip_members(snogit_source_temp_path)
                    default_members = [member.name for member in snogit_members if member.recommended_default]
                    selected_snogit_members = st.multiselect(
                        "SNOGIT .dat source/member(s)",
                        options=[member.name for member in snogit_members],
                        default=default_members,
                        help=(
                            "ZIP inputs default to the newest general SNOGIT_*.dat member only. "
                            "ELGA and Latin files can be selected explicitly. Raw .dat inputs are selected directly."
                        ),
                    )
                    if default_members:
                        st.caption(f"Default SNOGIT source/member: {default_members[0]}")
                except Exception as exc:
                    st.warning(f"Could not inspect SNOGIT source: {exc}")
            st.divider()
            st.markdown("#### Association type meanings")
            st.text(format_association_type_descriptions())
        settings_applied = st.form_submit_button("Apply suggestion settings")
    if settings_applied:
        st.success("Suggestion settings applied.")

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
    snogit_source_available = (snogit_source_file is not None or selected_snogit_source_from_dir is not None or bool(snogit_source_path_text.strip())) and bool(selected_snogit_members)
    snogit_ready = not (sanitize_semantic_bm25_fallback and use_snogit_bm25) or snogit_cache_available
    if sanitize_semantic_bm25_fallback and use_snogit_bm25 and not snogit_cache_available:
        st.info(
            "To use SNOGIT BM25 candidates, provide a processed SNOGIT cache or create one from a SNOGIT ZIP or .dat file first. "
            "Creating the cache does not automatically start suggestion generation."
        )

    if use_snogit_bm25 and not snogit_cache_available and snogit_source_available:
        if st.button(
            "Create processed SNOGIT cache",
            disabled=not inputs.hdf5_file,
        ):
            try:
                with st.status("Creating processed SNOGIT cache...", expanded=True) as cache_status:
                    st.write("Preparing HDF5 input...")
                    if inputs.hdf5_temp_path is None:
                        inputs.hdf5_temp_path = save_uploaded_file(inputs.hdf5_file, ".hdf5")
                    st.write("Preparing SNOGIT ZIP/.dat input...")
                    if selected_snogit_source_from_dir is not None:
                        snogit_source_path = selected_snogit_source_from_dir
                    elif snogit_source_path_text.strip():
                        snogit_source_path = pathlib.Path(snogit_source_path_text).expanduser()
                    else:
                        snogit_source_path = save_uploaded_file(snogit_source_file, _snogit_source_upload_suffix(snogit_source_file))
                    output_dir_for_sidecar = _snogit_cache_output_dir(inputs.data_dir)
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
                        snogit_zip_path=snogit_source_path,
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

    _render_active_settings_notice(
        historical_ancestor_fallback=activate_historical_ancestor_fallback,
        semantic_bm25_fallback=sanitize_semantic_bm25_fallback,
        blacklist_bm25=sanitize_blacklist_suggestions,
        use_snogit_bm25=use_snogit_bm25,
        snogit_cache_available=snogit_cache_available,
        association_types=sanitization_association_types,
        ancestor_max_distance=(int(ancestor_max_distance) if use_absolute_ancestor_limit else None),
        ancestor_max_relative_distance=(float(ancestor_max_relative_distance) if use_relative_ancestor_limit else None),
        bm25_min_score=float(sanitize_bm25_min_score),
        bm25_min_lexical_score=float(sanitize_bm25_min_lexical_score),
        bm25_max_candidates=int(sanitize_bm25_max_candidates),
    )

    custom_blacklist_ready = (
        not _uses_custom_blacklist(inputs.release_blacklist_mode)
        or inputs.runtime_blacklist_file is not None
    )
    if _uses_custom_blacklist(inputs.release_blacklist_mode) and inputs.runtime_blacklist_file is None:
        st.warning("Custom blacklist mode is selected. Select or upload a custom blacklist rule file before generating suggestions.")

    if st.button(
        "Generate sanitization suggestions",
        type="primary",
        disabled=not inputs.hdf5_file or not (use_session_findings or uploaded_findings_file) or not snogit_ready or not custom_blacklist_ready,
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
                enforce_embedded_blacklist = _enforce_embedded_blacklist(inputs.release_blacklist_mode)
                runtime_blacklist_indices = frozenset()
                custom_blacklist_path = None
                if inputs.target_view == "release" and _uses_custom_blacklist(inputs.release_blacklist_mode):
                    if inputs.runtime_blacklist_file is None:
                        raise ValueError("Custom blacklist mode is selected, but no custom blacklist rule file was provided.")
                    st.write("Resolving custom release blacklist rules...")
                    custom_blacklist_path, runtime_blacklist_indices = _resolve_custom_blacklist_indices(
                        inputs.hdf5_temp_path,
                        inputs.runtime_blacklist_file,
                    )
                    st.write(
                        f"Resolved custom blacklist to {len(runtime_blacklist_indices):,} concept(s)."
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
                    target_view=inputs.target_view,
                    release_exclude_blacklist=enforce_embedded_blacklist,
                    runtime_blacklist_indices=runtime_blacklist_indices,
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
                    if selected_snogit_cache_path is not None:
                        st.write("Using selected/created processed SNOGIT cache...")
                        snogit_sidecar_path = selected_snogit_cache_path
                    elif snogit_sidecar_file is not None:
                        st.write("Using uploaded processed SNOGIT cache...")
                        snogit_sidecar_path = save_uploaded_file(snogit_sidecar_file, ".hdf5")
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

                    def update_bm25_progress(update: dict[str, object]) -> None:
                        processed = int(update.get("processed", 0) or 0)
                        total = int(update.get("total", 0) or 0)
                        attempted = int(update.get("attempted", 0) or 0)
                        replaced = int(update.get("replaced", 0) or 0)
                        ambiguous = int(update.get("ambiguous", 0) or 0)
                        progress_value = float(update.get("progress", 0.0) or 0.0)
                        progress_value = max(0.0, min(1.0, progress_value))
                        ui_progress = 0.65 + 0.20 * progress_value
                        phase = str(update.get("phase", "processed"))
                        if phase == "scoring":
                            document = update.get("current_document") or "document"
                            code = update.get("current_code") or "code"
                            label = (
                                f"BM25 scoring {attempted:,} actionable finding(s) — "
                                f"{processed:,}/{total:,} processed · current: {document} / {code}"
                            )
                        elif phase == "complete":
                            label = (
                                f"BM25 fallback complete — {processed:,}/{total:,} processed · "
                                f"{replaced:,} replacement(s), {ambiguous:,} ambiguous"
                            )
                        else:
                            label = (
                                f"BM25 fallback — {processed:,}/{total:,} processed · "
                                f"{attempted:,} scored · {replaced:,} replacement(s), {ambiguous:,} ambiguous"
                            )
                        sanitization_progress.progress(ui_progress, text=label)

                    suggestions = apply_semantic_bm25_fallback(
                        suggestions,
                        inputs.hdf5_temp_path,
                        min_score=sanitize_bm25_min_score,
                        min_lexical_score=sanitize_bm25_min_lexical_score,
                        max_candidates=int(sanitize_bm25_max_candidates),
                        allow_blacklist_findings=sanitize_blacklist_suggestions,
                        snogit_sidecar_path=snogit_sidecar_path,
                        target_view=inputs.target_view,
                        release_exclude_blacklist=enforce_embedded_blacklist,
                        runtime_blacklist_indices=runtime_blacklist_indices,
                        progress_callback=update_bm25_progress,
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
                "enforce_embedded_blacklist": _enforce_embedded_blacklist(inputs.release_blacklist_mode),
                "custom_blacklist_path": str(custom_blacklist_path) if custom_blacklist_path is not None else None,
                "custom_blacklist_concepts": len(runtime_blacklist_indices),
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
                "finding_contexts": _suggestion_context_metadata(suggestions),
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

            st.subheader("Suggestion overview")
            _render_suggestion_overview(suggestions)

            st.subheader("Reports")
            download_md_report(
                sanitization_report_text,
                output_sanitization_md,
                "sanitization suggestions markdown",
            )
            with st.expander("Preview Markdown sanitization suggestion report", expanded=False):
                st.markdown(sanitization_report_text)
        except Exception as exc:
            st.error(f"Sanitization suggestion generation failed: {exc}")


def _render_suggestion_overview(suggestions: list[Any]) -> None:
    rows = [_suggestion_overview_row(index, suggestion) for index, suggestion in enumerate(suggestions, start=1)]
    if not rows:
        st.info("No sanitization suggestions to preview.")
        return
    st.caption(
        "Interactive read-only overview. Columns are intentionally wide; use horizontal scrolling "
        "instead of the Markdown table preview if values are truncated."
    )
    overview_df = pd.DataFrame(rows)
    st.data_editor(
        overview_df,
        key="sanitization_suggestion_overview_editor",
        hide_index=True,
        width="stretch",
        height=min(700, max(260, 38 * (len(rows) + 1))),
        disabled=True,
        column_config={
            "#": st.column_config.NumberColumn("#", width="small"),
            "Document": st.column_config.TextColumn("Document", width="medium"),
            "Annotator": st.column_config.TextColumn("Annotator", width="small"),
            "Source code": st.column_config.TextColumn("Source code", width="small"),
            "Covered text": st.column_config.TextColumn("Covered text", width="medium"),
            "Issue": st.column_config.TextColumn("Issue", width="small"),
            "Status": st.column_config.TextColumn("Status", width="medium"),
            "Replacement code": st.column_config.TextColumn("Replacement code", width="small"),
            "Replacement FSN": st.column_config.TextColumn("Replacement FSN", width="large"),
            "Reason": st.column_config.TextColumn("Reason", width="large"),
            "Top candidates": st.column_config.TextColumn("Top candidates", width="large"),
        },
    )


def _suggestion_overview_row(index: int, suggestion: Any) -> dict[str, Any]:
    finding = suggestion.finding
    return {
        "#": index,
        "Document": finding.document,
        "Annotator": finding.annotator,
        "Source code": finding.code or "",
        "Covered text": finding.covered_text,
        "Issue": getattr(finding, "list_type", ""),
        "Status": _status_text(getattr(suggestion, "status", "")),
        "Replacement code": getattr(suggestion, "replacement_code", None) or "",
        "Replacement FSN": getattr(suggestion, "replacement_fsn", None) or "",
        "Reason": getattr(suggestion, "reason", "") or "",
        "Top candidates": _candidate_summary(getattr(suggestion, "candidates", ())),
    }


def _candidate_summary(candidates: Any) -> str:
    parts = []
    for candidate in tuple(candidates or ())[:3]:
        code = getattr(candidate, "code", "")
        fsn = getattr(candidate, "fsn", None) or ""
        association = getattr(candidate, "association_type", None)
        source = getattr(candidate, "source", None)
        score = getattr(candidate, "score", None)
        source_hint = source or association or "candidate"
        score_hint = f", score {float(score):.2f}" if score is not None else ""
        parts.append(f"{code} — {fsn} ({source_hint}{score_hint})")
    return " | ".join(parts)


def _status_text(status: Any) -> str:
    return getattr(status, "value", str(status))


def _render_active_settings_notice(
    *,
    historical_ancestor_fallback: bool,
    semantic_bm25_fallback: bool,
    blacklist_bm25: bool,
    use_snogit_bm25: bool,
    snogit_cache_available: bool,
    association_types: list[str],
    ancestor_max_distance: int | None,
    ancestor_max_relative_distance: float | None,
    bm25_min_score: float,
    bm25_min_lexical_score: float,
    bm25_max_candidates: int,
) -> None:
    ancestor_bits = []
    if historical_ancestor_fallback:
        if ancestor_max_distance is not None:
            ancestor_bits.append(f"≤{ancestor_max_distance} edge(s)")
        if ancestor_max_relative_distance is not None:
            ancestor_bits.append(f"≤{ancestor_max_relative_distance:.2f} relative")
    ancestor_text = "on" + (f" ({', '.join(ancestor_bits)})" if ancestor_bits else "") if historical_ancestor_fallback else "off"
    bm25_text = (
        f"on (score ≥{bm25_min_score:.2f}, lexical ≥{bm25_min_lexical_score:.2f}, "
        f"{bm25_max_candidates} candidate(s))"
        if semantic_bm25_fallback
        else "off"
    )
    blacklist_text = "included" if semantic_bm25_fallback and blacklist_bm25 else "not included"
    snogit_text = "off"
    if semantic_bm25_fallback and use_snogit_bm25:
        snogit_text = "on, cache ready" if snogit_cache_available else "on, cache missing"
    elif use_snogit_bm25:
        snogit_text = "selected, inactive until BM25 is on"
    association_text = ", ".join(association_types or list(DEFAULT_ALLOWED_ASSOCIATION_TYPES))
    st.info(
        "Active settings: "
        f"historical associations {association_text} · "
        f"ancestor fallback {ancestor_text} · "
        f"BM25 {bm25_text} · "
        f"blacklist BM25 {blacklist_text} · "
        f"SNOGIT {snogit_text}",
        icon="ℹ️",
    )
