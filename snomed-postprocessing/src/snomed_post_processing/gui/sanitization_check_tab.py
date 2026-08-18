"""Sanitization-suggestion tab for the Streamlit GUI."""

from __future__ import annotations

import datetime
import pathlib
import tempfile
import time

import streamlit as st

from snomed_post_processing.findings_io import read_critical_findings_json
from snomed_post_processing.sanitization import (
    DEFAULT_ALLOWED_ASSOCIATION_TYPES,
    SUPPORTED_ASSOCIATION_TYPES,
    SanitizationResolver,
    apply_semantic_bm25_fallback,
    format_association_type_descriptions,
    sanitization_suggestions_json_text,
    write_sanitization_markdown_report,
)

from .downloads import download_json_report, download_md_report
from .files import save_uploaded_file
from .sidebar import GuiInputs


def render_sanitization_check_tab(inputs: GuiInputs) -> None:
    st.write(
        "Generate sanitization suggestions from CriticalFindings JSON produced by the policy check step."
    )
    uploaded_findings_file = st.file_uploader(
        "CriticalFindings JSON",
        type=["json"],
        help="Upload a CriticalFindings JSON file, or run the policy check in this session first.",
    )
    use_session_findings = st.checkbox(
        "Use CriticalFindings from current session",
        value=st.session_state.get("critical_findings") is not None,
        disabled=st.session_state.get("critical_findings") is None,
    )
    sanitization_association_types = st.multiselect(
        "Allowed historical association types",
        options=list(SUPPORTED_ASSOCIATION_TYPES),
        default=list(DEFAULT_ALLOWED_ASSOCIATION_TYPES),
    )
    activate_historical_ancestor_fallback = st.checkbox(
        "Activate historical ancestor fallback",
        value=False,
        help=(
            "For unresolved whitelist findings: try nearest active whitelisted ancestor, "
            "then nearest active whitelisted ancestor reachable through stored inactive is-a fallback edges."
        ),
    )
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
        disabled=not activate_historical_ancestor_fallback or not use_absolute_ancestor_limit,
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
        disabled=not activate_historical_ancestor_fallback or not use_relative_ancestor_limit,
        help="Distance divided by source depth-to-root. Lower values reject broader jumps in shallow hierarchies.",
    )
    sanitize_semantic_bm25_fallback = st.checkbox(
        "Use semantic BM25 for unresolved whitelist findings as fallback",
        value=False,
    )
    sanitize_blacklist_suggestions = st.checkbox(
        "Include blacklist findings in BM25 sanitization suggestions",
        value=False,
        disabled=not sanitize_semantic_bm25_fallback,
    )
    with st.expander("BM25 fallback thresholds", expanded=False):
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
    with st.expander("Association type meanings", expanded=False):
        st.text(format_association_type_descriptions())

    if st.button(
        "Generate sanitization suggestions",
        type="primary",
        disabled=not inputs.hdf5_file or not (use_session_findings or uploaded_findings_file),
    ):
        try:
            if inputs.hdf5_temp_path is None:
                inputs.hdf5_temp_path = save_uploaded_file(inputs.hdf5_file, ".hdf5")
            if use_session_findings:
                findings = st.session_state["critical_findings"]
            else:
                findings_path = save_uploaded_file(uploaded_findings_file, ".json")
                findings = read_critical_findings_json(findings_path)

            sanitization_progress = st.progress(
                0.0, text="Preparing sanitization suggestions..."
            )
            resolver = SanitizationResolver(
                inputs.hdf5_temp_path,
                allowed_association_types=sanitization_association_types
                or list(DEFAULT_ALLOWED_ASSOCIATION_TYPES),
                activate_historical_ancestor_fallback=activate_historical_ancestor_fallback,
                ancestor_max_distance=(
                    int(ancestor_max_distance) if use_absolute_ancestor_limit else None
                ),
                ancestor_max_relative_distance=(
                    float(ancestor_max_relative_distance) if use_relative_ancestor_limit else None
                ),
            )
            sanitization_progress.progress(
                0.25,
                text=(
                    f"Resolving historical-association suggestions for "
                    f"{len(findings)} finding(s)..."
                ),
            )
            suggestions = resolver.suggest_all(findings)
            if sanitize_semantic_bm25_fallback:
                sanitization_progress.progress(
                    0.65, text="Running semantic BM25 fallback suggestions..."
                )
                suggestions = apply_semantic_bm25_fallback(
                    suggestions,
                    inputs.hdf5_temp_path,
                    min_score=sanitize_bm25_min_score,
                    min_lexical_score=sanitize_bm25_min_lexical_score,
                    max_candidates=int(sanitize_bm25_max_candidates),
                    allow_blacklist_findings=sanitize_blacklist_suggestions,
                )
            sanitization_progress.progress(
                0.9, text="Writing sanitization suggestion report..."
            )
            output_dir = pathlib.Path(tempfile.mkdtemp(prefix="snomed_gui_sanitization_"))
            timestamp = datetime.datetime.now().strftime('%d-%m-%Y_%H-%M')
            output_sanitization_md = output_dir / f"sanitization_suggestions_{timestamp}.md"
            output_sanitization_json = output_dir / f"sanitization_suggestions_{timestamp}.json"
            sanitization_settings = {
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
            }
            sanitization_metadata = {
                "source": "streamlit_sanitization_check_tab",
                "hdf5_file_name": getattr(inputs.hdf5_file, "name", None),
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

            st.session_state["sanitization_suggestions"] = suggestions
            st.session_state["sanitization_suggestions_metadata"] = sanitization_metadata
            st.session_state["sanitization_suggestions_report_path"] = str(output_sanitization_md)
            st.session_state["sanitization_suggestions_json_path"] = str(output_sanitization_json)

            sanitization_report_text = output_sanitization_md.read_text(encoding="utf-8")
            st.success("Sanitization suggestions finished.")
            download_json_report(sanitization_json_text, output_sanitization_json)
            download_md_report(
                sanitization_report_text,
                output_sanitization_md,
                "sanitization suggestions markdown",
            )
            with st.expander("Preview sanitization suggestion report", expanded=True):
                st.markdown(sanitization_report_text)
        except Exception as exc:
            st.error(f"Sanitization suggestion generation failed: {exc}")
