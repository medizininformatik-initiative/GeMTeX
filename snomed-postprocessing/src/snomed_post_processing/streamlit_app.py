import datetime
import json
import pathlib
import sys
import tempfile
import time
from typing import Optional

import streamlit as st

from snomed_post_processing.uima_processing import (
    CriticalFinding,
    get_annotator_names,
    process_inception_zip,
    create_log_from_results,
)
from snomed_post_processing.sanitization import (
    DEFAULT_ALLOWED_ASSOCIATION_TYPES,
    SUPPORTED_ASSOCIATION_TYPES,
    SanitizationResolver,
    apply_semantic_bm25_fallback,
    format_association_type_descriptions,
    write_sanitization_markdown_report,
)
from snomed_post_processing.utils import get_project_zip
from snomed_post_processing.hdf5_metadata import (
    inspect_hdf5_metadata,
    format_hdf5_metadata_summary,
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
    annotation_types: Optional[list[str]] = None,
    ignore_overlap_types: Optional[list[str]] = None,
    ignore_overlap_mode: str = "overlap",
    suggest_sanitization: bool = False,
    sanitization_association_types: Optional[list[str]] = None,
    sanitization_progress_obj: Optional[dict] = None,
    sanitize_semantic_bm25_fallback: bool = False,
    sanitize_blacklist_suggestions: bool = False,
    sanitize_bm25_min_score: float = 1.5,
    sanitize_bm25_min_lexical_score: float = 0.15,
    sanitize_bm25_max_candidates: int = 5,
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, Optional[pathlib.Path], int]:
    json_dump_dictionary = {}
    output_md = project_zip.parent / (
        f"critical_documents_{datetime.datetime.now().strftime('%d-%m-%Y_%H-%M')}.md"
    )
    output_md_masked = output_md.with_suffix(".masked.md")
    output_json = output_md.with_suffix(".json")
    output_sanitization_md = output_md.with_name(
        output_md.stem.replace("critical_documents", "sanitization_suggestions")
        + output_md.suffix
    )

    err_doc_count = 0
    critical_findings: list[CriticalFinding] = []
    result = process_inception_zip(
        project_zip,
        annotator_filter=anno_filter,
        annotation_types=annotation_types,
        ignore_overlap_types=ignore_overlap_types,
        ignore_overlap_mode=ignore_overlap_mode,
    )
    if result is None:
        raise RuntimeError("Processing failed.")

    with (
        output_md.open("w", encoding="utf-8") as log_doc,
        output_md_masked.open("w", encoding="utf-8") as log_doc_masked,
    ):
        err_doc_count = create_log_from_results(
            result,
            log_doc,
            log_doc_masked,
            lists_path,
            progress_obj,
            json_dump_dictionary,
            critical_findings=critical_findings,
        )
    if progress_obj is not None and progress_obj.get("obj") is not None:
        progress_obj["obj"].empty()

    with output_json.open("w", encoding="utf-8") as json_fi:
        json.dump(json_dump_dictionary, json_fi, indent=2, ensure_ascii=False)

    if suggest_sanitization:
        sanitization_progress = (
            sanitization_progress_obj.get("obj")
            if sanitization_progress_obj is not None
            else None
        )
        if sanitization_progress is not None:
            sanitization_progress.progress(
                0.0,
                text="Preparing sanitization suggestions...",
            )
        resolver = SanitizationResolver(
            lists_path,
            allowed_association_types=sanitization_association_types or list(DEFAULT_ALLOWED_ASSOCIATION_TYPES),
        )
        if sanitization_progress is not None:
            sanitization_progress.progress(
                0.25,
                text=f"Resolving historical-association suggestions for {len(critical_findings)} finding(s)...",
            )
        suggestions = resolver.suggest_all(critical_findings)
        if sanitize_semantic_bm25_fallback:
            if sanitization_progress is not None:
                sanitization_progress.progress(
                    0.65,
                    text="Running semantic BM25 fallback suggestions...",
                )
            suggestions = apply_semantic_bm25_fallback(
                suggestions,
                lists_path,
                min_score=sanitize_bm25_min_score,
                min_lexical_score=sanitize_bm25_min_lexical_score,
                max_candidates=sanitize_bm25_max_candidates,
                allow_blacklist_findings=sanitize_blacklist_suggestions,
            )
        if sanitization_progress is not None:
            sanitization_progress.progress(
                0.9,
                text="Writing sanitization suggestion report...",
            )
        with output_sanitization_md.open("w", encoding="utf-8") as sanitization_fi:
            write_sanitization_markdown_report(suggestions, sanitization_fi)
        if sanitization_progress is not None:
            sanitization_progress.progress(
                1.0,
                text="Sanitization suggestions finished.",
            )
            time.sleep(0.2)
            sanitization_progress.empty()
    else:
        output_sanitization_md = None

    return output_md, output_md_masked, output_json, output_sanitization_md, err_doc_count


@st.fragment
def download_json_report(json_dump, output_fi: pathlib.Path):
    st.download_button(
        label="Download JSON dump",
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
                        _project_tmp, url, username, password, None, False
                    )
                    st.success(f"Found {len(st.session_state['projects'])} projects.")
                except RuntimeError:
                    st.error(
                        "Could not connect to INCEpTION API. Please check credentials and URL."
                    )
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
                            False
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
    st.header("Annotation layers")
    annotation_types_text = st.text_area(
        "Target annotation types to check",
        value="gemtex.Concept",
        help="One UIMA layer/type per line. Faulty SNOMED code checks run on these annotations.",
    )
    ignore_overlap_types_text = st.text_area(
        "Ignore faulty target annotations overlapping these types",
        value="webanno.custom.No_Human",
        help="One UIMA layer/type per line. Faulty target annotations overlapping these layers are reported separately and excluded from the critical count. Default: webanno.custom.No_Human.",
    )
    ignore_overlap_mode = st.selectbox(
        "Ignore overlap mode",
        options=["overlap", "covered-by", "contains", "exact"],
        index=0,
        help="Controls how target annotations must match ignore annotations to be ignored.",
    )
    st.header("Sanitization suggestions")
    suggest_sanitization = st.checkbox(
        "Create separate sanitization suggestion report",
        value=True,
        help="Generates a standalone Markdown report with conservative historical-association replacement suggestions. Documents are not modified.",
    )
    sanitization_association_types = st.multiselect(
        "Allowed historical association types",
        options=list(SUPPORTED_ASSOCIATION_TYPES),
        default=list(DEFAULT_ALLOWED_ASSOCIATION_TYPES),
        help="Used only when sanitization suggestions are enabled.",
    )
    sanitize_semantic_bm25_fallback = st.checkbox(
        "Use semantic BM25 fallback for unresolved whitelist findings",
        value=False,
        help="Suggestion-only fallback. Historical associations are tried first; BM25 suggestions are written to the same sanitization report when score thresholds are met.",
    )
    sanitize_blacklist_suggestions = st.checkbox(
        "Include blacklist findings in BM25 sanitization suggestions",
        value=False,
        disabled=not sanitize_semantic_bm25_fallback,
        help="Suggestion-only. Proposes active whitelisted non-blacklisted replacements for blacklisted findings when BM25 thresholds are met.",
    )
    with st.expander("BM25 fallback thresholds", expanded=False):
        sanitize_bm25_min_score = st.number_input(
            "Minimum BM25 score",
            min_value=0.0,
            value=1.5,
            step=0.1,
            help="Higher values make BM25 fallback suggestions more conservative.",
        )
        sanitize_bm25_min_lexical_score = st.number_input(
            "Minimum lexical overlap ratio",
            min_value=0.0,
            max_value=1.0,
            value=0.15,
            step=0.05,
            help="Minimum fraction of query tokens that must occur in the candidate label.",
        )
        sanitize_bm25_max_candidates = st.number_input(
            "Maximum retained candidates",
            min_value=1,
            max_value=50,
            value=5,
            step=1,
        )
    st.caption(
        "Association type meanings:\n"
        + format_association_type_descriptions()
    )


annotator_selection = None
zip_temp_path = None
hdf5_temp_path = None

if zip_file := st.session_state.get("zip_file"):
    zip_temp_path = save_uploaded_file(zip_file, ".zip")
    # Handle both UploadedFile (has .name) and Path (has .name)
    zip_name = zip_file.name if hasattr(zip_file, "name") else str(zip_file)
    st.success(f"ZIP ready: {zip_name}")

    if load_annotators:
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

if hdf5_file is not None:
    st.success(f"HDF5 uploaded: {hdf5_file.name}")
    try:
        hdf5_temp_path = save_uploaded_file(hdf5_file, ".hdf5")
        hdf5_summary = inspect_hdf5_metadata(hdf5_temp_path)
        with st.expander("HDF5 metadata summary", expanded=True):
            st.markdown(format_hdf5_metadata_summary(hdf5_summary, markdown=True, include_path=False))
    except Exception as exc:
        st.warning(f"Could not read HDF5 metadata: {exc}")

if st.button("Run analysis", type="primary", disabled=not (zip_file and hdf5_file)):
    try:
        if zip_temp_path is None:
            raise RuntimeError("ZIP file was not prepared correctly.")
        progress_bar = st.progress(
            0.0, text="Running document analysis... this may take a while."
        )
        sanitization_progress_placeholder = st.empty()
        time.sleep(1)

        if hdf5_temp_path is None:
            hdf5_temp_path = save_uploaded_file(hdf5_file, ".hdf5")

        annotator_filter = (
            [name.lower() for name in annotator_selection]
            if annotator_selection
            else None
        )

        annotation_types = [
            line.strip()
            for line in annotation_types_text.splitlines()
            if line.strip()
        ] or ["gemtex.Concept"]
        ignore_overlap_types = [
            line.strip()
            for line in ignore_overlap_types_text.splitlines()
            if line.strip()
        ]

        (
            output_path_md,
            output_path_md_masked,
            output_path_json,
            output_path_sanitization_md,
            erroneous_doc_count,
        ) = generate_report(
            project_zip=zip_temp_path,
            lists_path=hdf5_temp_path,
            anno_filter=annotator_filter,
            progress_obj={"obj": progress_bar, "text_pre": ""},
            annotation_types=annotation_types,
            ignore_overlap_types=ignore_overlap_types,
            ignore_overlap_mode=ignore_overlap_mode,
            suggest_sanitization=suggest_sanitization,
            sanitization_association_types=sanitization_association_types,
            sanitization_progress_obj={"obj": sanitization_progress_placeholder},
            sanitize_semantic_bm25_fallback=sanitize_semantic_bm25_fallback,
            sanitize_blacklist_suggestions=sanitize_blacklist_suggestions,
            sanitize_bm25_min_score=sanitize_bm25_min_score,
            sanitize_bm25_min_lexical_score=sanitize_bm25_min_lexical_score,
            sanitize_bm25_max_candidates=int(sanitize_bm25_max_candidates),
        )
        progress_bar.empty()
        sanitization_progress_placeholder.empty()

        report_text = output_path_md.read_text(encoding="utf-8")
        report_text_masked = output_path_md_masked.read_text(encoding="utf-8")
        json_text = output_path_json.read_text(encoding="utf-8")
        sanitization_report_text = (
            output_path_sanitization_md.read_text(encoding="utf-8")
            if output_path_sanitization_md is not None
            else None
        )

        st.success("Analysis finished.")
        st.metric("Critical documents found", erroneous_doc_count)
        st.write(f"Report saved to folder: `{output_path_md.parent.resolve()}`")

        for triple in [
            (report_text, output_path_md, "markdown"),
            (report_text_masked, output_path_md_masked, "masked markdown"),
        ]:
            download_md_report(*triple)
        download_json_report(json_text, output_path_json)
        if sanitization_report_text is not None and output_path_sanitization_md is not None:
            download_md_report(
                sanitization_report_text,
                output_path_sanitization_md,
                "sanitization suggestions markdown",
            )

        with st.expander("Preview report"):
            st.markdown(report_text)
        if sanitization_report_text is not None:
            with st.expander("Preview sanitization suggestion report", expanded=True):
                st.markdown(sanitization_report_text)

        st.session_state["zip_file"] = None
        st.session_state["current_project"] = None

    except Exception as exc:
        st.error(f"Analysis failed: {exc}")
