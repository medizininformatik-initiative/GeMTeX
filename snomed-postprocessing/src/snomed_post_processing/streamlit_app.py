import datetime
import pathlib
import sys
import tempfile
import time
from typing import Optional

import streamlit as st

if __name__ == "__main__":
    sys.path.append(".")
    from uima_processing import (
        get_annotator_names,
        process_inception_zip,
        create_log_from_results,
    )
    from utils import (
        get_project_zip
    )
else:
    from .uima_processing import (
        get_annotator_names,
        process_inception_zip,
        create_log_from_results,
    )
    from .utils import (
        get_project_zip
    )


st.set_page_config(page_title="GeMTeX SNOMED CT Postprocessing", layout="wide")


def save_uploaded_file(uploaded_file, suffix: str) -> pathlib.Path:
    if isinstance(uploaded_file, pathlib.Path):
        return uploaded_file
    temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="snomed_gui_"))
    target = temp_dir / f"upload{suffix}"
    target.write_bytes(uploaded_file.getvalue())
    return target


def generate_report(
    project_zip: pathlib.Path,
    lists_path: pathlib.Path,
    anno_filter: Optional[list] = None,
    progress_obj: dict = None,
):
    output = project_zip.parent / (
        f"critical_documents_{datetime.datetime.now().strftime('%d-%m-%Y_%H-%M-%S')}.md"
    )

    err_doc_count = 0
    result = process_inception_zip(project_zip, annotator_filter=anno_filter)
    if result is None:
        raise RuntimeError("Processing failed.")

    with output.open("w", encoding="utf-8") as log_doc:
        err_doc_count = create_log_from_results(
            result, log_doc, lists_path, progress_obj
        )

    return output, err_doc_count


@st.fragment
def download_report(report):
    st.download_button(
        label="Download markdown report",
        data=report,
        file_name=output_path.name,
        mime="text/markdown",
    )


st.title("SNOMED Postprocessing")
st.write("""Simple GUI for analyzing all critical documents in the given INCEpTION dump (supported export formats: ``json``).  
         Critical are documents when they contain SNOMED CT codes that are either on the blacklist or are not on the whitelist.  
         Whitelist and blacklist are both defined in a ``hdf5`` file, that must be provided.""")

with st.sidebar:
    st.header("Inputs")
    st.session_state["zip_file"] = None
    load_annotators = st.checkbox("Load annotators from ZIP", value=True)
    use_api = st.toggle("Use INCEpTION API", value=False)
    if use_api:
        _project_tmp = tempfile.mkdtemp("snomed_gui_dir")
        with st.form("inception_api_form"):
            url = st.text_input("INCEpTION API URL", value="http://localhost:8080")
            username = st.text_input("REMOTE Role Username")
            password = st.text_input("REMOTE Role Password", type="password")
            submitted = st.form_submit_button("Get Projects")
            if submitted:
                st.session_state["projects"] = get_project_zip(_project_tmp, url, username, password)
        if st.session_state.get("projects", None) is not None:
            project = st.selectbox("Select project", st.session_state.get("projects", []), index=None)
            st.session_state["current_project"] = project
            if project is not None:
                _zip = get_project_zip(_project_tmp, url, username, password, project)
                if isinstance(_zip, pathlib.Path):
                    st.session_state["zip_file"] = _zip
                elif isinstance(_zip, list):
                    pass
                else:
                    st.error("Could not load projects from INCEpTION API.")
    else:
        st.session_state["zip_file"] = st.file_uploader("INCEpTION project ZIP", type=["zip"])
    hdf5_file = st.file_uploader("Whitelist/Blacklist HDF5", type=["hdf5"])


annotator_selection = None
zip_temp_path = None

if zip_file := st.session_state.get("zip_file"):
    zip_temp_path = save_uploaded_file(zip_file, ".zip")
    st.success(f"ZIP uploaded: {zip_file.name}")

    if load_annotators:
        try:
            annotators = sorted(get_annotator_names(zip_temp_path))
            if annotators:
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

if hdf5_file is not None:
    st.success(f"HDF5 uploaded: {hdf5_file.name}")

if st.button("Run analysis", type="primary", disabled=not (zip_file and hdf5_file)):
    try:
        if zip_temp_path is None:
            raise RuntimeError("ZIP file was not prepared correctly.")
        progress_bar = st.progress(
            0.0, text="Running analysis... this may take a while."
        )
        time.sleep(1)

        hdf5_temp_path = save_uploaded_file(hdf5_file, ".hdf5")

        annotator_filter = (
            [name.lower() for name in annotator_selection]
            if annotator_selection
            else None
        )

        output_path, erroneous_doc_count = generate_report(
            project_zip=zip_temp_path,
            lists_path=hdf5_temp_path,
            anno_filter=annotator_filter,
            progress_obj={"obj": progress_bar, "text_pre": ""},
        )
        progress_bar.empty()

        report_text = output_path.read_text(encoding="utf-8")

        st.success("Analysis finished.")
        st.metric("Critical documents found", erroneous_doc_count)
        st.write(f"Report saved to: `{output_path}`")

        download_report(report_text)

        with st.expander("Preview report"):
            st.markdown(report_text)

        st.session_state["zip_file"] = None

    except Exception as exc:
        st.error(f"Analysis failed: {exc}")
