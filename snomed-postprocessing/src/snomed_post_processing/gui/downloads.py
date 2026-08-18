"""Download widgets for the Streamlit GUI."""

from __future__ import annotations

import pathlib

import streamlit as st


@st.fragment
def download_json_report(json_dump, output_fi: pathlib.Path):
    st.download_button(
        label="Download sanitization suggestion json",
        data=json_dump,
        file_name=output_fi.name,
        mime="text/json",
    )


@st.fragment
def download_md_report(md_report, output_fi: pathlib.Path, label: str):
    st.download_button(
        label=f"Download {label} report",
        data=md_report,
        file_name=output_fi.name,
        mime="text/markdown",
    )
