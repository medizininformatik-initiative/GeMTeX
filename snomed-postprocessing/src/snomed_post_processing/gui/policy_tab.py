"""Policy-check tab for the Streamlit GUI."""

from __future__ import annotations

from collections import defaultdict
import pathlib

import streamlit as st

from snomed_post_processing.terminology import policy_label
from snomed_post_processing.uima_processing import CriticalFinding, get_annotator_names

from .downloads import download_json_report, download_md_report
from .files import save_uploaded_file
from .report_generation import generate_report
from .sidebar import GuiInputs


def render_policy_tab(inputs: GuiInputs) -> None:
    if inputs.target_view == "release":
        st.info(
            "Release view affects sanitization suggestion generation only: "
            "replacement candidates are valid when they are active in the "
            "materialized HDF5 release view, with optional embedded/custom "
            "exclusion-list rules. This tab still runs the policy check that "
            "identifies critical findings from the inclusion/exclusion-list policy."
        )
    else:
        st.caption(
            "Policy view: annotations are critical when they are not in the "
            "inclusion list or are in the exclusion list for the materialized policy/view "
            "date stored in the uploaded HDF5."
        )
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
        help="Check selected layers and annotators against inclusion/exclusion policy. No annotations are changed.",
        type="primary",
        disabled=not (st.session_state.get("zip_file") and inputs.hdf5_file),
    ):
        try:
            if zip_temp_path is None:
                raise RuntimeError("ZIP file was not prepared correctly.")
            with st.status("Running policy check...", expanded=True) as status:
                st.write("Preparing project ZIP and SNOMED HDF5 inputs...")
                if inputs.hdf5_temp_path is None:
                    inputs.hdf5_temp_path = save_uploaded_file(inputs.hdf5_file, ".hdf5")

                st.write("Preparing annotator and annotation-layer filters...")
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

                st.write("Checking annotations and writing reports...")
                progress_bar = st.progress(
                    0.0, text="Running document analysis... this may take a while."
                )
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
                    id_prefix=inputs.id_prefix,
                    id_feature=inputs.id_feature,
                )
                progress_bar.empty()
                status.update(label="Policy check finished.", state="complete", expanded=False)

            report_text = output_path_md.read_text(encoding="utf-8")
            report_text_masked = output_path_md_masked.read_text(encoding="utf-8")
            json_text = output_path_json.read_text(encoding="utf-8")
            findings_json_text = output_path_findings_json.read_text(encoding="utf-8")

            st.session_state["critical_findings"] = critical_findings
            st.session_state["critical_findings_json_text"] = findings_json_text
            st.session_state["critical_findings_json_name"] = output_path_findings_json.name

            st.session_state["policy_check_result"] = {
                "critical_findings": critical_findings,
                "critical_documents_found": erroneous_doc_count,
                "report_folder": str(output_path_md.parent.resolve()),
                "markdown_text": report_text,
                "markdown_name": output_path_md.name,
                "masked_markdown_text": report_text_masked,
                "masked_markdown_name": output_path_md_masked.name,
                "json_text": json_text,
                "json_name": output_path_json.name,
                "findings_json_text": findings_json_text,
                "findings_json_name": output_path_findings_json.name,
            }
            st.success("Policy check finished.")

        except Exception as exc:
            st.error(f"Policy check failed: {exc}")

    render_policy_check_result()


def render_policy_check_result() -> None:
    """Render the last successful check on every rerun, including filter changes."""
    result = st.session_state.get("policy_check_result")
    if not result:
        return

    st.caption("Results from the last successful policy check; changed inputs require a new check.")
    st.metric("Critical documents found", result["critical_documents_found"])
    st.download_button(
        label="Download CriticalFindings JSON",
        data=result["findings_json_text"],
        file_name=result["findings_json_name"],
        mime="application/json",
        help="Download the critical findings as JSON to load them in later for sanitization.",
    )

    render_findings_table(result["critical_findings"])

    st.subheader("Reports")
    st.write(f"Report saved to folder: `{result['report_folder']}`")
    report_col1, report_col2, report_col3 = st.columns(3)
    with report_col1:
        download_md_report(result["markdown_text"], pathlib.Path(result["markdown_name"]), "markdown")
    with report_col2:
        download_md_report(
            result["masked_markdown_text"], pathlib.Path(result["masked_markdown_name"]), "masked markdown",
            help="Masks document and annotator names, not clinical text. This is not full anonymization.",
        )
    with report_col3:
        download_json_report(
            result["json_text"], pathlib.Path(result["json_name"]), "report",
            help="Structured policy-check report. Use CriticalFindings JSON instead as input for suggestion generation.",
        )


def render_findings_table(findings: list[CriticalFinding]) -> None:
    st.subheader("Findings")
    if not findings:
        st.success("No findings to display.")
        return

    critical_count = sum(1 for finding in findings if not finding.ignored)
    ignored_count = len(findings) - critical_count
    inclusion_count = sum(1 for finding in findings if finding.list_type == "whitelist")
    exclusion_count = sum(1 for finding in findings if finding.list_type == "blacklist")
    affected_documents = len({finding.document for finding in findings})
    affected_annotators = len({finding.annotator for finding in findings})
    metric_cols = st.columns(6)
    metric_cols[0].metric("Critical findings", critical_count)
    metric_cols[1].metric("Ignored findings", ignored_count)
    metric_cols[2].metric("Inclusion-list findings", inclusion_count)
    metric_cols[3].metric("Exclusion-list findings", exclusion_count)
    metric_cols[4].metric("Affected documents", affected_documents)
    metric_cols[5].metric("Affected annotators", affected_annotators)

    with st.expander("Filters", expanded=False):
        st.caption("Filters affect this display only, not report downloads or findings passed to suggestion generation.")
        if st.button("Clear all filters", key="findings_clear_filters"):
            st.session_state["findings_filter_status"] = "all"
            st.session_state["findings_filter_check"] = "all"
            st.session_state["findings_filter_sctid"] = ""
            st.session_state["findings_filter_text"] = ""
            st.rerun()

        filter_cols = st.columns(4)
        status = filter_cols[0].selectbox(
            "Status", options=["all", "critical", "ignored"], index=0,
            key="findings_filter_status",
        )
        check = filter_cols[1].selectbox(
            "Check", options=["all", "inclusion list", "exclusion list"], index=0,
            key="findings_filter_check",
        )
        sctid_query = filter_cols[2].text_input(
            "SCTID contains", value="", key="findings_filter_sctid",
        ).strip()
        text_query = filter_cols[3].text_input(
            "Covered text contains", value="", key="findings_filter_text",
        ).strip().lower()

    filtered = [
        finding for finding in findings
        if _finding_matches_filters(
            finding, status=status, check=check,
            sctid_query=sctid_query, text_query=text_query,
        )
    ]
    if not filtered:
        st.info("No findings match the current filters.")
        return

    grouped: dict[str, dict[str, list[CriticalFinding]]] = defaultdict(lambda: defaultdict(list))
    for finding in sorted(filtered, key=lambda item: (item.document, item.annotator, item.offset[0], item.offset[1])):
        grouped[finding.document][finding.annotator].append(finding)

    st.caption(f"Showing {len(filtered):,} of {len(findings):,} finding(s).")
    for document, annotator_groups in grouped.items():
        doc_critical_count = sum(1 for group in annotator_groups.values() for finding in group if not finding.ignored)
        doc_ignored_count = sum(1 for group in annotator_groups.values() for finding in group if finding.ignored)
        label = f"{document} — {doc_critical_count:,} critical"
        if doc_ignored_count:
            label += f", {doc_ignored_count:,} ignored"
        with st.expander(label, expanded=False):
            for annotator, annotator_findings in annotator_groups.items():
                st.markdown(f"#### {annotator}")
                st.caption(_finding_count_summary(annotator_findings))
                st.dataframe(
                    [_finding_row(finding) for finding in annotator_findings],
                    hide_index=True,
                    width="stretch",
                )


def _finding_count_summary(findings: list[CriticalFinding]) -> str:
    critical_count = sum(1 for finding in findings if not finding.ignored)
    ignored_count = len(findings) - critical_count
    inclusion_count = sum(1 for finding in findings if finding.list_type == "whitelist")
    exclusion_count = sum(1 for finding in findings if finding.list_type == "blacklist")
    return (
        f"{critical_count:,} critical · "
        f"{ignored_count:,} ignored · "
        f"{inclusion_count:,} inclusion-list · "
        f"{exclusion_count:,} exclusion-list"
    )


def _finding_matches_filters(
    finding: CriticalFinding,
    *,
    status: str,
    check: str,
    sctid_query: str,
    text_query: str,
) -> bool:
    if status == "critical" and finding.ignored:
        return False
    if status == "ignored" and not finding.ignored:
        return False
    if check != "all" and _check_label(finding.list_type) != check:
        return False
    if sctid_query and sctid_query not in (finding.code or ""):
        return False
    if text_query and text_query not in finding.covered_text.lower():
        return False
    return True


def _finding_row(finding: CriticalFinding) -> dict[str, str]:
    return {
        "sctid": finding.code or "",
        "fsn": finding.fsn or "",
        "covered_text": finding.covered_text,
        "status": "ignored" if finding.ignored else "critical",
        "check": _check_label(finding.list_type),
        "annotation_layer": finding.layer or "",
    }


def _check_label(list_type: str) -> str:
    return policy_label(list_type)
