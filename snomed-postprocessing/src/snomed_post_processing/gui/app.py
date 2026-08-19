"""Streamlit GUI entrypoint."""

from __future__ import annotations

import streamlit as st

from snomed_post_processing.hdf5_handling.metadata import (
    format_hdf5_metadata_summary,
    inspect_hdf5_metadata,
)

from snomed_post_processing.gui.files import save_uploaded_file
from snomed_post_processing.gui.policy_tab import render_policy_tab
from snomed_post_processing.gui.sanitization_check_tab import render_sanitization_check_tab
from snomed_post_processing.gui.sanitization_run_tab import render_sanitization_run_tab
from snomed_post_processing.gui.sidebar import render_sidebar


st.set_page_config(page_title="GeMTeX SNOMED CT Postprocessing", layout="wide")

st.title("SNOMED Postprocessing")
st.write(
    """Simple GUI for analyzing all critical documents in the given INCEpTION dump (supported export formats: JSON CAS and XMI).  
         Critical are documents when they contain SNOMED CT codes that are either on the blacklist or are not on the whitelist.  
         Whitelist and blacklist are both defined in a ``hdf5`` file, that must be provided."""
)

inputs = render_sidebar()

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
                )
            )
    except Exception as exc:
        st.warning(f"Could not read HDF5 metadata: {exc}")

policy_tab, sanitization_check_tab, sanitization_run_tab = st.tabs(
    [
        "1. Check whitelist/blacklist",
        "2. Sanitization suggestions",
        "3. Sanitization run",
    ]
)

with policy_tab:
    render_policy_tab(inputs)

with sanitization_check_tab:
    render_sanitization_check_tab(inputs)

with sanitization_run_tab:
    render_sanitization_run_tab(inputs)
