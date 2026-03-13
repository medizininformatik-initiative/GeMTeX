import datetime
import pathlib
import sys
import tempfile
import time
from collections import Counter

import h5py
import streamlit as st

if __name__ == "__main__":
    sys.path.append(".")
    from uima_processing import (
        analyze_documents,
        get_annotator_names,
        log_final_tag_count,
        process_inception_zip,
    )
    from utils import Information, ListDumpType
else:
    from .uima_processing import (
        analyze_documents,
        get_annotator_names,
        log_final_tag_count,
        process_inception_zip,
    )
    from .utils import Information, ListDumpType


st.set_page_config(page_title="GeMTeX SNOMED CT Postprocessing", layout="wide")


def save_uploaded_file(uploaded_file, suffix: str) -> pathlib.Path:
    temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="snomed_gui_"))
    target = temp_dir / f"upload{suffix}"
    target.write_bytes(uploaded_file.getvalue())
    return target


def generate_report(
    project_zip: pathlib.Path,
    lists_path: pathlib.Path,
    annotator_filter=None,
    progress_obj=dict,
):
    output_path = project_zip.parent / (
        f"critical_documents_{datetime.datetime.now().strftime('%d-%m-%Y_%H-%M-%S')}.md"
    )

    erroneous_doc_count = 0

    result = process_inception_zip(project_zip, annotator_filter=annotator_filter)
    if result is None:
        raise RuntimeError("Processing failed.")

    with output_path.open("w", encoding="utf-8") as log_doc:
        log_doc.write(Information.log_dump_pretext)

        with h5py.File(lists_path, "r") as h5_file:
            blacklist_tag_counter = Counter()
            whitelist_code_counter = Counter()
            section_count = {}

            progress_increment = 1 / max(
                sum([len(x.documents) for x in result.annotators.values()]) * 2, 1
            )
            _iter_obj = [ListDumpType.WHITELIST, ListDumpType.BLACKLIST]
            for i, ft in enumerate(_iter_obj):
                group_name = ft.name.lower()
                if group_name not in h5_file:
                    continue

                filter_list = h5_file[group_name]["0"]["codes"][:]
                fsn_list = h5_file[group_name]["0"]["fsn"][:]

                erroneous_doc_count += analyze_documents(
                    result,
                    filter_list,
                    fsn_list,
                    ft,
                    log_doc,
                    True,
                    section_count,
                    blacklist_tag_counter,
                    whitelist_code_counter,
                    {
                        "obj": progress_obj["obj"],
                        "text_pre": f"__{ft.name.capitalize()}__: ",
                        "progress_increment": progress_increment,
                        "current_progress": 1.0 * (i / len(_iter_obj)),
                    },
                )

            log_final_tag_count(
                whitelist_code_counter,
                blacklist_tag_counter,
                log_doc,
            )

    return output_path, erroneous_doc_count


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
    load_annotators = st.checkbox("Load annotators from ZIP", value=True)
    zip_file = st.file_uploader("INCEpTION project ZIP", type=["zip"])
    hdf5_file = st.file_uploader("Whitelist/Blacklist HDF5", type=["hdf5"])


annotator_selection = None
zip_temp_path = None

if zip_file is not None:
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
            annotator_filter=annotator_filter,
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

    except Exception as exc:
        st.error(f"Analysis failed: {exc}")
