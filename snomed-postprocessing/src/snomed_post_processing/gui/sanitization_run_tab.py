"""Sanitization-run tab for the Streamlit GUI."""

from __future__ import annotations

import streamlit as st

from .sidebar import GuiInputs


def render_sanitization_run_tab(inputs: GuiInputs) -> None:
    st.write("Apply reviewed sanitization suggestions back to CAS documents.")
    st.info(
        "This workflow is not implemented yet. Generate and review sanitization "
        "suggestions in the previous tab first."
    )
    st.button("Run sanitization", type="primary", disabled=True)
