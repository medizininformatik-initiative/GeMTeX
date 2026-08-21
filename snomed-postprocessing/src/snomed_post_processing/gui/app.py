"""Streamlit GUI entrypoint."""

from __future__ import annotations

import h5py
import streamlit as st

from snomed_post_processing.hdf5_handling.policy import decode_array

from snomed_post_processing.hdf5_handling.metadata import (
    format_hdf5_metadata_summary,
    inspect_hdf5_metadata,
)

from snomed_post_processing.gui.files import save_uploaded_file
from snomed_post_processing.gui.policy_tab import render_policy_tab
from snomed_post_processing.gui.sanitization_check_tab import render_sanitization_check_tab
from snomed_post_processing.gui.sanitization_run_tab import render_sanitization_run_tab
from snomed_post_processing.gui.sidebar import render_sidebar


def _numeric_blacklist_rule_fsns(hdf5_path, numeric_rules: list[str]) -> dict[str, str]:
    if hdf5_path is None or not numeric_rules:
        return {}
    requested = set(numeric_rules)
    with h5py.File(hdf5_path, "r") as h5_file:
        if "concepts" not in h5_file or "codes" not in h5_file["concepts"] or "fsn" not in h5_file["concepts"]:
            return {}
        concepts = h5_file["concepts"]
        codes = decode_array(concepts["codes"][:])
        fsns = decode_array(concepts["fsn"][:])
    return {code: fsn for code, fsn in zip(codes, fsns) if code in requested and fsn}


def _format_blacklist_rule_for_gui(raw_rule: str, kind: str, numeric_rule_fsns: dict[str, str]) -> str:
    if kind == "concept_descendants" and raw_rule in numeric_rule_fsns:
        return f"{raw_rule} - {numeric_rule_fsns[raw_rule]}"
    return raw_rule


st.set_page_config(page_title="GeMTeX SNOMED CT Postprocessing", layout="wide")

st.title("SNOMED Postprocessing")
st.write(
    """Check SNOMED CT annotations in INCEpTION exports, generate replacement suggestions, and apply reviewed sanitization decisions to a copied project ZIP."""
)

inputs = render_sidebar()

if inputs.target_view == "policy":
    st.info(
        "**Current target: Policy rules** — annotations must be allowed by the "
        "embedded whitelist/blacklist policy views.",
        icon="🎯",
    )
else:
    blacklist_label = {
        "none": "no blacklist",
        "embedded": "embedded HDF5 blacklist",
        "runtime": "runtime blacklist rules",
    }.get(inputs.release_blacklist_mode, inputs.release_blacklist_mode)
    st.info(
        "**Current target: Active release** — annotations must be active release "
        f"concepts; blacklist mode: {blacklist_label}. Release execution is not "
        "enabled yet.",
        icon="🎯",
    )

if inputs.hdf5_file is not None:
    st.success(f"HDF5 uploaded: {inputs.hdf5_file.name}")
    try:
        inputs.hdf5_temp_path = save_uploaded_file(inputs.hdf5_file, ".hdf5")
        hdf5_summary = inspect_hdf5_metadata(inputs.hdf5_temp_path)
        with st.expander("HDF5 metadata summary", expanded=False):
            st.markdown(
                format_hdf5_metadata_summary(
                    hdf5_summary,
                    markdown=True,
                    include_path=False,
                    include_blacklist_rule_details=False,
                )
            )
            if hdf5_summary.blacklist_metadata:
                st.divider()
                st.markdown("#### Embedded blacklist rule metadata")
                for blacklist_metadata in hdf5_summary.blacklist_metadata:
                    source = blacklist_metadata.source_name or "unknown"
                    st.caption(
                        f"blacklists/{blacklist_metadata.view_name} · "
                        f"{len(blacklist_metadata.rules):,} rule(s) · source: {source}"
                    )
                    numeric_rule_fsns = _numeric_blacklist_rule_fsns(
                        inputs.hdf5_temp_path,
                        [rule.raw for rule in blacklist_metadata.rules if rule.kind == "concept_descendants"],
                    )
                    st.dataframe(
                        [
                            {
                                "Rule kind": rule.kind,
                                "Rule": _format_blacklist_rule_for_gui(rule.raw, rule.kind, numeric_rule_fsns),
                            }
                            for rule in blacklist_metadata.rules
                        ],
                        hide_index=True,
                        width="stretch",
                    )
            elif any(policy == "blacklist" for policy, _, _ in hdf5_summary.policy_view_counts):
                st.info(
                    "This HDF5 contains a compact blacklist view, but no embedded blacklist rule metadata was found. "
                    "Recreate or update the HDF5 with the current RF2 ingestion code to store the original blacklist rules."
                )
    except Exception as exc:
        st.warning(f"Could not read HDF5 metadata: {exc}")

check_label = "1. Check policy" if inputs.target_view == "policy" else "1. Check release view"
suggest_label = "2. Suggest policy sanitization" if inputs.target_view == "policy" else "2. Suggest release normalization"
run_label = "3. Review & apply"
policy_tab, sanitization_check_tab, sanitization_run_tab = st.tabs(
    [check_label, suggest_label, run_label]
)

with policy_tab:
    render_policy_tab(inputs)

with sanitization_check_tab:
    render_sanitization_check_tab(inputs)

with sanitization_run_tab:
    render_sanitization_run_tab(inputs)
