"""Policy-check tab for the Streamlit GUI."""

from __future__ import annotations

import time

import streamlit as st

from snomed_post_processing.uima_processing import get_annotator_names

from .downloads import download_json_report, download_md_report
from .files import save_uploaded_file
from .report_generation import generate_report
from .sidebar import GuiInputs


def render_policy_tab(inputs: GuiInputs) -> None:
    annotator_selection = None
    zip_temp_path = None

    if zip_file := st.session_state.get("zip_file"):
        zip_temp_path = save_uploaded_file(zip_file, ".zip")
        zip_name = zip_file.name if hasattr(zip_file, "name") else str(zip_file)
        st.success(f"ZIP ready: {zip_name}")

        if inputs.load_annotators:
            try:
                annotators, only_ser = get_annotator_names(zip_temp_path)
                annotators = sorted(annotators)
                if only_ser:
                    st.error(
                        "The project only contains UIMA Java Serialized CAS (.ser) files, which are not supported. Please export as JSON CAS or XMI instead."
                    )
                    st.session_state["zip_file"] = None
                    st.rerun()
                elif annotators:
                    annotator_selection = st.multiselect(
                        "Select annotators to include",
                        options=annotators,
                        default=[],
                        help="Leave empty to include all annotators.",
                    )
                else:
                    st.info("No annotators found in ZIP.")
            except Exception as exc:
                st.warning(f"Could not load annotators: {exc}")

    if st.button(
        "Run policy check",
        type="primary",
        disabled=not (st.session_state.get("zip_file") and inputs.hdf5_file),
    ):
        try:
            if zip_temp_path is None:
                raise RuntimeError("ZIP file was not prepared correctly.")
            progress_bar = st.progress(
                0.0, text="Running document analysis... this may take a while."
            )
            time.sleep(1)

            if inputs.hdf5_temp_path is None:
                inputs.hdf5_temp_path = save_uploaded_file(inputs.hdf5_file, ".hdf5")

            annotator_filter = (
                [name.lower() for name in annotator_selection]
                if annotator_selection
                else None
            )
            annotation_types = [
                line.strip()
                for line in inputs.annotation_types_text.splitlines()
                if line.strip()
            ] or ["gemtex.Concept"]
            ignore_overlap_types = [
                line.strip()
                for line in inputs.ignore_overlap_types_text.splitlines()
                if line.strip()
            ]

            (
                output_path_md,
                output_path_md_masked,
                output_path_json,
                output_path_findings_json,
                erroneous_doc_count,
                critical_findings,
            ) = generate_report(
                project_zip=zip_temp_path,
                lists_path=inputs.hdf5_temp_path,
                anno_filter=annotator_filter,
                progress_obj={"obj": progress_bar, "text_pre": ""},
                annotation_types=annotation_types,
                ignore_overlap_types=ignore_overlap_types,
                ignore_overlap_mode=inputs.ignore_overlap_mode,
            )
            progress_bar.empty()

            report_text = output_path_md.read_text(encoding="utf-8")
            report_text_masked = output_path_md_masked.read_text(encoding="utf-8")
            json_text = output_path_json.read_text(encoding="utf-8")
            findings_json_text = output_path_findings_json.read_text(encoding="utf-8")

            st.session_state["critical_findings"] = critical_findings
            st.session_state["critical_findings_json_text"] = findings_json_text
            st.session_state["critical_findings_json_name"] = output_path_findings_json.name

            st.success("Policy check finished.")
            st.metric("Critical documents found", erroneous_doc_count)
            st.write(f"Report saved to folder: `{output_path_md.parent.resolve()}`")

            for triple in [
                (report_text, output_path_md, "markdown"),
                (report_text_masked, output_path_md_masked, "masked markdown"),
            ]:
                download_md_report(*triple)
            download_json_report(json_text, output_path_json)
            st.download_button(
                label="Download CriticalFindings JSON",
                data=findings_json_text,
                file_name=output_path_findings_json.name,
                mime="application/json",
            )

            with st.expander("Preview report"):
                st.markdown(report_text)

        except Exception as exc:
            st.error(f"Policy check failed: {exc}")
