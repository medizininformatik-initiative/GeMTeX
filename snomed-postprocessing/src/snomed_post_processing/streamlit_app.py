import datetime
import json
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
    from utils import get_project_zip
else:
    from .uima_processing import (
        get_annotator_names,
        process_inception_zip,
        create_log_from_results,
    )
    from .utils import get_project_zip


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
    progress_obj: dict = None
) -> tuple[pathlib.Path, pathlib.Path, int]:
    json_dump_dictionary = {}
    output_md = project_zip.parent / (
        f"critical_documents_{datetime.datetime.now().strftime('%d-%m-%Y_%H-%M')}.md"
    )
    output_json = output_md.with_suffix(".json")

    err_doc_count = 0
    result = process_inception_zip(project_zip, annotator_filter=anno_filter)
    if result is None:
        raise RuntimeError("Processing failed.")

    with output_md.open("w", encoding="utf-8") as log_doc:
        err_doc_count = create_log_from_results(
            result, log_doc, lists_path, progress_obj, json_dump_dictionary
        )
    with output_json.open("w", encoding="utf-8") as json_fi:
        json.dump(json_dump_dictionary, json_fi, indent=2, ensure_ascii=False)

    return output_md, output_json, err_doc_count


@st.fragment
def download_json_report(json_dump, output_fi: pathlib.Path):
    st.download_button(
        label="Download JSON dump",
        data=json_dump,
        file_name=output_fi.name,
        mime="text/json",
    )

@st.fragment
def download_md_report(md_report, output_fi: pathlib.Path):
    st.download_button(
        label="Download markdown report",
        data=md_report,
        file_name=output_fi.name,
        mime="text/markdown",
    )


st.title("SNOMED Postprocessing")
st.write("""Simple GUI for analyzing all critical documents in the given INCEpTION dump (supported export formats: ``json``).  
         Critical are documents when they contain SNOMED CT codes that are either on the blacklist or are not on the whitelist.  
         Whitelist and blacklist are both defined in a ``hdf5`` file, that must be provided.""")

with st.sidebar:
    st.header("Inputs")
    load_annotators = st.checkbox("Load annotators from ZIP", value=True)
    use_api = st.toggle("Use INCEpTION API", value=False)
    if use_api:
        if "api_credentials" not in st.session_state:
            st.session_state["api_credentials"] = {
                "url": "http://localhost:8080",
                "username": "",
                "password": "",
            }

        with st.form("inception_api_form"):
            url = st.text_input(
                "INCEpTION API URL", value=st.session_state["api_credentials"]["url"]
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
            submitted = st.form_submit_button("Get Projects")
            if submitted:
                st.session_state["api_credentials"] = {
                    "url": url,
                    "username": username,
                    "password": password,
                }
                try:
                    _project_tmp = tempfile.mkdtemp("snomed_gui_dir")
                    st.session_state["projects"] = get_project_zip(
                        _project_tmp, url, username, password
                    )
                    st.success(f"Found {len(st.session_state['projects'])} projects.")
                except RuntimeError:
                    st.error("Could not connect to INCEpTION API. Please check credentials and URL.")
                    st.session_state.pop("api_credentials", None)
                except Exception as e:
                    st.error(f"Error: {e}")
                    st.session_state.pop("projects", None)

        if st.session_state.get("projects"):
            project = st.selectbox(
                "Select project", st.session_state["projects"], index=None
            )
            if project and (st.session_state.get("current_project") != project):
                st.session_state["current_project"] = project
                with st.spinner(f"Downloading project '{project}'..."):
                    try:
                        _project_tmp = tempfile.mkdtemp("snomed_gui_dir")
                        creds = st.session_state["api_credentials"]
                        _zip = get_project_zip(
                            _project_tmp,
                            creds["url"],
                            creds["username"],
                            creds["password"],
                            project,
                        )
                        if isinstance(_zip, pathlib.Path):
                            st.session_state["zip_file"] = _zip
                        else:
                            st.error("Could not load project from INCEpTION API.")
                    except Exception as e:
                        st.error(f"Error downloading project: {e}")
    else:
        st.session_state["zip_file"] = st.file_uploader(
            "INCEpTION project ZIP", type=["zip"]
        )
    hdf5_file = st.file_uploader("Whitelist/Blacklist HDF5", type=["hdf5"])


annotator_selection = None
zip_temp_path = None

if zip_file := st.session_state.get("zip_file"):
    zip_temp_path = save_uploaded_file(zip_file, ".zip")
    # Handle both UploadedFile (has .name) and Path (has .name)
    zip_name = zip_file.name if hasattr(zip_file, "name") else str(zip_file)
    st.success(f"ZIP ready: {zip_name}")

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

        output_path_md, output_path_json, erroneous_doc_count = generate_report(
            project_zip=zip_temp_path,
            lists_path=hdf5_temp_path,
            anno_filter=annotator_filter,
            progress_obj={"obj": progress_bar, "text_pre": ""},
        )
        progress_bar.empty()

        report_text = output_path_md.read_text(encoding="utf-8")
        json_text = output_path_json.read_text(encoding="utf-8")

        st.success("Analysis finished.")
        st.metric("Critical documents found", erroneous_doc_count)
        st.write(f"Report saved to: `{output_path_md}`")

        download_md_report(report_text, output_path_md)
        download_json_report(json_text, output_path_json)

        with st.expander("Preview report"):
            st.markdown(report_text)

        st.session_state["zip_file"] = None
        st.session_state["current_project"] = None

    except Exception as exc:
        st.error(f"Analysis failed: {exc}")
