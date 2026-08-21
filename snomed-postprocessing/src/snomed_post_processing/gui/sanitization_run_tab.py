"""Sanitization-run tab for the Streamlit GUI."""

from __future__ import annotations

import datetime
import pathlib
import tempfile
from typing import Any

import pandas as pd
import streamlit as st

from snomed_post_processing.sanitization import (
    read_sanitization_decisions_json,
    read_sanitization_suggestions_json_with_metadata,
    sanitization_decisions_json_text,
)

from .downloads import download_json_report
from snomed_post_processing.sanitization.models import SanitizationStatus
from snomed_post_processing.pipelines.sanitization_run import run_sanitization

from .files import save_uploaded_file
from .sidebar import GuiInputs


NO_REPLACEMENT_LABEL = "— no replacement selected —"


def render_sanitization_run_tab(inputs: GuiInputs) -> None:
    st.write("Review sanitization suggestions before applying them back to CAS documents.")

    st.subheader("Sources")
    _render_suggestion_source_selector()
    _render_decision_source_selector()

    if st.session_state.get("sanitization_last_load_message"):
        st.success(st.session_state.pop("sanitization_last_load_message"))

    suggestions = st.session_state.get("sanitization_suggestions")
    if not suggestions:
        if st.session_state.get("sanitization_restored_decisions_by_index"):
            st.info(
                "Reviewed decisions are loaded, but no sanitization suggestions are available yet. "
                "Upload the matching suggestions JSON or generate suggestions in the previous tab."
            )
        else:
            st.info(
                "No sanitization suggestions are available yet. Generate suggestions in the previous tab "
                "or upload a saved suggestions JSON file."
            )
        st.button("Run sanitization", type="primary", disabled=True)
        return

    st.caption(f"Loaded {len(suggestions)} suggestion(s).")
    json_path = st.session_state.get("sanitization_suggestions_json_path")
    if json_path:
        st.caption(f"Suggestions JSON: `{json_path}`")
    report_path = st.session_state.get("sanitization_suggestions_report_path")
    if report_path:
        st.caption(f"Suggestion report: `{report_path}`")

    rows = _suggestions_to_review_rows(suggestions)
    _render_review_summary(rows)

    with st.popover("Suggestion metadata"):
        _render_suggestion_settings(st.session_state.get("sanitization_suggestions_metadata") or {})

    st.subheader("Review workspace")
    reviewed_decisions = _render_document_review_sections(rows)
    st.session_state["sanitization_review_decisions"] = reviewed_decisions

    decisions_metadata = _decisions_metadata(rows)
    decisions_text = sanitization_decisions_json_text(reviewed_decisions, metadata=decisions_metadata)

    invalid_selected_rows = [
        decision for decision in reviewed_decisions if decision["apply"] and not decision["valid_choice"]
    ]
    selected_count = sum(1 for decision in reviewed_decisions if decision["apply"] and decision["valid_choice"])
    st.caption(f"Selected {selected_count} valid replacement(s) for the future sanitization run.")
    if invalid_selected_rows:
        st.warning(
            "Some selected rows use a replacement choice that is not valid for that row. "
            "Please choose one of the row's candidate options."
        )

    _render_sanitization_run_controls(
        reviewed_decisions,
        decisions_text,
        selected_count=selected_count,
        has_invalid_selected_rows=bool(invalid_selected_rows),
    )


def _render_suggestion_source_selector() -> None:
    session_suggestions_available = st.session_state.get("sanitization_suggestions") is not None
    if session_suggestions_available:
        source = st.segmented_control(
            "Sanitization suggestions source",
            options=["Current session", "Upload JSON"],
            default="Current session",
            key="sanitization_suggestions_source",
            help=(
                "Use suggestions generated in this browser session, or upload a "
                "saved sanitization suggestions JSON file."
            ),
            width="stretch",
        ) or "Current session"
    else:
        source = "Upload JSON"
        st.info(
            "No sanitization suggestions are available in the current session. "
            "Upload a suggestions JSON file or generate suggestions in the previous tab."
        )

    if source != "Upload JSON":
        return

    uploaded_suggestions_file = st.file_uploader(
        "Sanitization suggestions JSON",
        type=["json"],
        key="sanitization_suggestions_json_uploader",
        help="Upload suggestions saved from the sanitization-check tab.",
    )
    if uploaded_suggestions_file is None:
        return
    upload_key = _uploaded_file_key(uploaded_suggestions_file)
    if st.session_state.get("loaded_sanitization_suggestions_upload_key") == upload_key:
        return
    try:
        suggestions, metadata = read_sanitization_suggestions_json_with_metadata(
            uploaded_suggestions_file
        )
        st.session_state["sanitization_suggestions"] = suggestions
        st.session_state["sanitization_suggestions_metadata"] = metadata
        st.session_state["sanitization_suggestions_report_path"] = None
        st.session_state["sanitization_suggestions_json_path"] = uploaded_suggestions_file.name
        st.session_state["loaded_sanitization_suggestions_upload_key"] = upload_key
        _bump_review_state_revision()
        st.session_state["sanitization_last_load_message"] = (
            f"Loaded suggestions from {uploaded_suggestions_file.name}."
        )
        st.rerun()
    except Exception as exc:
        st.error(f"Could not load sanitization suggestions JSON: {exc}")


def _render_decision_source_selector() -> None:
    review_state = st.segmented_control(
        "Review state",
        options=["Start fresh", "Load reviewed decisions"],
        default="Start fresh",
        key="sanitization_review_state_source",
        help="Optionally restore a saved review state after loading matching suggestions.",
        width="stretch",
    ) or "Start fresh"
    if review_state != "Load reviewed decisions":
        return

    uploaded_decisions_file = st.file_uploader(
        "Reviewed sanitization decisions JSON",
        type=["json"],
        key="sanitization_decisions_json_uploader",
        help="Load a previously saved review state after loading/generating matching suggestions.",
    )
    if uploaded_decisions_file is None:
        return
    upload_key = _uploaded_file_key(uploaded_decisions_file)
    if st.session_state.get("loaded_sanitization_decisions_upload_key") == upload_key:
        return
    try:
        decisions, metadata = read_sanitization_decisions_json(uploaded_decisions_file)
        _restore_decision_state(decisions, metadata)
        st.session_state["loaded_sanitization_decisions_upload_key"] = upload_key
        _bump_review_state_revision()
        st.session_state["sanitization_last_load_message"] = (
            f"Loaded reviewed decisions from {uploaded_decisions_file.name}."
        )
        st.rerun()
    except Exception as exc:
        st.error(f"Could not load sanitization decisions JSON: {exc}")


def _render_run_readiness(
    *,
    project_loaded: bool,
    selected_count: int,
    has_invalid_selected_rows: bool,
) -> None:
    if project_loaded and selected_count > 0 and not has_invalid_selected_rows:
        st.success(
            f"Ready to run: project ZIP loaded and {selected_count} valid "
            "replacement(s) selected."
        )
        return

    messages = []
    if project_loaded:
        messages.append("✅ Project ZIP loaded")
    else:
        messages.append("❌ Upload or load an INCEpTION project ZIP in the sidebar")
    if selected_count > 0:
        messages.append(f"✅ {selected_count} valid replacement(s) selected")
    else:
        messages.append("❌ Select at least one valid replacement")
    if has_invalid_selected_rows:
        messages.append("⚠️ Some selected rows have invalid replacement choices")
    else:
        messages.append("✅ No invalid selected replacement choices")
    st.warning("Cannot run yet:\n\n" + "\n".join(f"- {message}" for message in messages))


def _render_sanitization_run_controls(
    reviewed_decisions: list[dict[str, Any]],
    decisions_text: str,
    *,
    selected_count: int,
    has_invalid_selected_rows: bool,
) -> None:
    st.subheader("Run")
    project_source = st.session_state.get("zip_file")
    run_disabled = project_source is None or selected_count == 0 or has_invalid_selected_rows
    _render_run_readiness(
        project_loaded=project_source is not None,
        selected_count=selected_count,
        has_invalid_selected_rows=has_invalid_selected_rows,
    )

    control_col1, control_col2 = st.columns([1, 1])
    with control_col1:
        run_clicked = st.button(
            "Run sanitization",
            type="primary",
            disabled=run_disabled,
            help=(
                "Writes a sanitized copy of the uploaded project ZIP. The original "
                "project is not modified."
            ),
            width="stretch",
        )
    with control_col2:
        with st.popover("Review artifacts", width="stretch"):
            download_json_report(
                decisions_text,
                pathlib.Path("reviewed_sanitization_decisions.json"),
                "reviewed sanitization decisions",
            )
            st.caption("Save this JSON to restore the current review state later.")
    if not run_clicked:
        return

    try:
        with st.status("Running reviewed sanitization...", expanded=True) as status:
            st.write("Saving uploaded project ZIP to a temporary workspace...")
            input_project = save_uploaded_file(project_source, ".zip")
            output_dir = pathlib.Path(tempfile.mkdtemp(prefix="snomed_gui_sanitized_"))
            output_project = output_dir / f"sanitized_project_{datetime.datetime.now().strftime('%d-%m-%Y_%H-%M')}.zip"
            st.write("Applying reviewed decisions to copied JSON/XMI CAS files...")
            result = run_sanitization(
                input_project,
                reviewed_decisions,
                output_project,
            )
            st.write("Preparing sanitized project ZIP for download...")
            status.update(
                label="Reviewed sanitization finished.",
                state="complete",
                expanded=False,
            )
        st.success(
            f"Sanitized project written. Changed {result.changed_annotation_count} annotation(s) "
            f"in {result.changed_member_count} CAS file(s)."
        )
        if result.unmatched_decisions:
            st.warning(f"{len(result.unmatched_decisions)} applied decision(s) could not be matched to a CAS annotation.")
        st.download_button(
            "Download sanitized project ZIP",
            data=output_project.read_bytes(),
            file_name=output_project.name,
            mime="application/zip",
        )
    except Exception as exc:
        st.error(f"Sanitization run failed: {exc}")


def _uploaded_file_key(uploaded_file: Any) -> tuple[str, int | None]:
    return (getattr(uploaded_file, "name", ""), getattr(uploaded_file, "size", None))


def _review_state_revision() -> int:
    return int(st.session_state.get("sanitization_review_state_revision", 0))


def _bump_review_state_revision() -> None:
    st.session_state["sanitization_review_state_revision"] = _review_state_revision() + 1


def _render_document_review_sections(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    grouped_rows = _group_rows_by_document(rows)
    st.caption(
        "Each document can be reviewed separately. Highlighted 'Suggested replacement' cells "
        "are controlled by row-specific selection widgets in the same document section."
    )
    reviewed_count = sum(
        1 for document in grouped_rows if st.session_state.get(_document_reviewed_key(document), False)
    )
    st.caption(f"Reviewed {reviewed_count} of {len(grouped_rows)} document section(s).")
    focus = st.pills(
        "Focus documents",
        options=["All", "Needs choice", "No replacement", "Unreviewed"],
        default="All",
        key="sanitization_review_focus",
        help=(
            "Controls which document sections open by default. Other sections stay "
            "available so hidden edits are not lost."
        ),
        width="stretch",
    ) or "All"

    for document, document_rows in grouped_rows.items():
        reviewed_key = _document_reviewed_key(document)
        reviewed = bool(st.session_state.get(reviewed_key, False))
        focus_match = _document_matches_focus(document, document_rows, focus)
        title = _document_review_title(document, document_rows, reviewed)
        with st.expander(title, expanded=focus_match and not reviewed):
            if reviewed:
                st.success("This document section is marked as reviewed.")
            review_df = pd.DataFrame(document_rows).drop(columns=["Document", "_offset", "_layer"], errors="ignore")
            edited = st.data_editor(
                _style_review_table(review_df),
                key=f"sanitization_review_editor_{_safe_key(document)}_{_review_state_revision()}",
                width="stretch",
                hide_index=True,
                disabled=[
                    "#",
                    "Annotator",
                    "Source code",
                    "Covered text",
                    "Suggested replacement",
                    "Original FSN",
                    "Status",
                ],
                column_config={
                    "Apply": st.column_config.CheckboxColumn(
                        "Apply",
                        help="Toggle whether this suggestion should be applied in the sanitization run.",
                    ),
                    "Suggested replacement": st.column_config.TextColumn(
                        "Suggested replacement",
                        help="Unambiguous replacement, or a row-specific choice selected below.",
                    ),
                    "_valid_choices": None,
                    "_needs_choice": None,
                },
            )
            row_choices = _render_row_choice_controls(document_rows)
            decisions.extend(
                _review_rows_to_decisions(edited.to_dict("records"), document_rows, row_choices)
            )
            st.checkbox(
                "Mark this document section as reviewed",
                key=reviewed_key,
                help="On the next rerun this section will collapse and be marked with a checkmark.",
            )
    return decisions


def _document_matches_focus(
    document: str, document_rows: list[dict[str, Any]], focus: str
) -> bool:
    if focus == "All":
        return True
    if focus == "Needs choice":
        return any(row.get("_needs_choice") for row in document_rows)
    if focus == "No replacement":
        return any(
            row.get("Suggested replacement") == NO_REPLACEMENT_LABEL
            for row in document_rows
        )
    if focus == "Unreviewed":
        return not bool(st.session_state.get(_document_reviewed_key(document), False))
    return True


def _document_review_title(
    document: str, document_rows: list[dict[str, Any]], reviewed: bool
) -> str:
    selected = sum(1 for row in document_rows if row.get("Apply"))
    needs_choice = sum(1 for row in document_rows if row.get("_needs_choice"))
    no_replacement = sum(
        1 for row in document_rows if row.get("Suggested replacement") == NO_REPLACEMENT_LABEL
    )
    prefix = "✅" if reviewed else "📝"
    details = [f"{len(document_rows)} finding(s)", f"{selected} selected"]
    if needs_choice:
        details.append(f"{needs_choice} need choice")
    if no_replacement:
        details.append(f"{no_replacement} no replacement")
    return f"{prefix} {document} — {' · '.join(details)}"


def _group_rows_by_document(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("Document", "")), []).append(row)
    return grouped


def _render_review_summary(rows: list[dict[str, Any]]) -> None:
    grouped_rows = _group_rows_by_document(rows)
    automatic_replacements = sum(
        1
        for row in rows
        if row.get("Suggested replacement") != NO_REPLACEMENT_LABEL
        and not row.get("_needs_choice")
    )
    needs_choice = sum(1 for row in rows if row.get("_needs_choice"))
    no_replacement = sum(
        1 for row in rows if row.get("Suggested replacement") == NO_REPLACEMENT_LABEL
    )
    metric_cols = st.columns(5)
    metric_cols[0].metric("Suggestions", len(rows))
    metric_cols[1].metric("Documents", len(grouped_rows))
    metric_cols[2].metric("Automatic", automatic_replacements)
    metric_cols[3].metric("Need choice", needs_choice)
    metric_cols[4].metric("No replacement", no_replacement)


def _decisions_metadata(rows: list[dict[str, Any]]) -> dict[str, Any]:
    documents = list(_group_rows_by_document(rows).keys())
    reviewed_documents = [
        document
        for document in documents
        if st.session_state.get(_document_reviewed_key(document), False)
    ]
    return {
        "suggestions_json_path": st.session_state.get("sanitization_suggestions_json_path"),
        "suggestions_report_path": st.session_state.get("sanitization_suggestions_report_path"),
        "document_count": len(documents),
        "reviewed_documents": reviewed_documents,
    }


def _restore_decision_state(decisions: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    st.session_state["sanitization_restored_decisions_by_index"] = {
        int(decision["suggestion_index"]): decision
        for decision in decisions
        if "suggestion_index" in decision
    }
    for decision in decisions:
        if "suggestion_index" not in decision:
            continue
        row_number = int(decision["suggestion_index"]) + 1
        replacement_choice = decision.get("replacement_choice")
        if replacement_choice:
            st.session_state[_choice_key(row_number)] = replacement_choice
    reviewed_documents = metadata.get("reviewed_documents", []) if isinstance(metadata, dict) else []
    for document in reviewed_documents:
        st.session_state[_document_reviewed_key(str(document))] = True
    st.session_state["sanitization_decisions_metadata"] = metadata


def _render_suggestion_settings(metadata: dict[str, Any]) -> None:
    settings = metadata.get("settings") if isinstance(metadata, dict) else None
    if not isinstance(settings, dict):
        st.caption("No sanitization-generation settings found in the loaded suggestions JSON.")
        return
    st.json(
        {
            "hdf5_file_name": metadata.get("hdf5_file_name"),
            "finding_count": metadata.get("finding_count"),
            "suggestion_count": metadata.get("suggestion_count"),
            "settings": settings,
        }
    )


def _style_review_table(review_df: pd.DataFrame):
    def highlight_choice_cells(data: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame("", index=data.index, columns=data.columns)
        if "_needs_choice" in data.columns and "Suggested replacement" in data.columns:
            styles.loc[
                data["_needs_choice"].astype(bool),
                "Suggested replacement",
            ] = "background-color: #fff3cd; color: #664d03; font-weight: 600"
        return styles

    return review_df.style.apply(highlight_choice_cells, axis=None)


def _suggestions_to_review_rows(suggestions: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    restored_by_index = st.session_state.get("sanitization_restored_decisions_by_index", {})
    for idx, suggestion in enumerate(suggestions):
        row_number = idx + 1
        restored_decision = restored_by_index.get(idx, {})
        replacement_options = _replacement_options(suggestion)
        replacement_label = _replacement_label(suggestion)
        is_automatic_replacement = replacement_label != NO_REPLACEMENT_LABEL
        needs_choice = _needs_row_specific_choice(suggestion, replacement_options)
        selected_label = st.session_state.get(
            _choice_key(row_number),
            restored_decision.get("replacement_choice")
            or (replacement_options[0] if replacement_options else NO_REPLACEMENT_LABEL),
        )
        rows.append(
            {
                "#": row_number,
                "Apply": bool(restored_decision.get("apply", is_automatic_replacement and not needs_choice)),
                "Document": suggestion.finding.document,
                "Annotator": suggestion.finding.annotator,
                "Source code": suggestion.finding.code or "",
                "Covered text": suggestion.finding.covered_text,
                "Suggested replacement": selected_label if needs_choice else replacement_label,
                "Original FSN": suggestion.finding.fsn or "",
                "Status": _status_value(suggestion.status),
                "_offset": tuple(suggestion.finding.offset),
                "_layer": suggestion.finding.layer,
                "_valid_choices": tuple(replacement_options),
                "_needs_choice": needs_choice,
            }
        )
    return rows


def _render_row_choice_controls(rows: list[dict[str, Any]]) -> dict[int, str]:
    choice_rows = [row for row in rows if row.get("_needs_choice")]
    if not choice_rows:
        return {}

    st.caption(
        "Replacement choices for highlighted rows. Options can include the nearest rejected ancestor "
        "and retained BM25 candidates."
    )
    choices: dict[int, str] = {}
    for row in choice_rows:
        options = list(row.get("_valid_choices", ()))
        if not options:
            continue
        row_number = int(row["#"])
        label = f"#{row_number}: {row['Document']} — {row['Source code']} — {row['Covered text']}"
        choices[row_number] = st.selectbox(
            label,
            options=options,
            key=_choice_key(row_number),
        )
    return choices


def _review_rows_to_decisions(
    edited_rows: list[dict[str, Any]],
    original_rows: list[dict[str, Any]],
    ambiguous_choices: dict[int, str],
) -> list[dict[str, Any]]:
    original_by_number = {row["#"]: row for row in original_rows}
    decisions = []
    for edited in edited_rows:
        row_number = int(edited["#"])
        original = original_by_number.get(row_number, {})
        choice = ambiguous_choices.get(row_number) or edited.get("Suggested replacement") or NO_REPLACEMENT_LABEL
        valid_choices = tuple(original.get("_valid_choices", ()))
        valid_choice = choice in valid_choices
        decisions.append(
            {
                "suggestion_index": row_number - 1,
                "apply": bool(edited.get("Apply")),
                "annotator": edited.get("Annotator", ""),
                "document": original.get("Document", ""),
                "source_code": edited.get("Source code", ""),
                "covered_text": edited.get("Covered text", ""),
                "offset": list(original.get("_offset", ())),
                "layer": original.get("_layer"),
                "replacement_choice": choice,
                "replacement_code": _code_from_label(choice) if valid_choice else None,
                "replacement_fsn": _fsn_from_label(choice) if valid_choice else None,
                "valid_choice": valid_choice,
            }
        )
    return decisions


def _replacement_options(suggestion: Any) -> list[str]:
    labels = []
    seen = set()

    def add_label(label: str) -> None:
        if label and label not in seen:
            labels.append(label)
            seen.add(label)

    replacement_label = _replacement_label(suggestion)
    if replacement_label != NO_REPLACEMENT_LABEL:
        add_label(replacement_label)
        if not _needs_top_k_choice(suggestion):
            return labels

    for candidate in getattr(suggestion, "context_candidates", ()) or ():
        add_label(_code_fsn_label(getattr(candidate, "code", None), getattr(candidate, "fsn", None)))
    for candidate in getattr(suggestion, "candidates", ()) or ():
        add_label(_code_fsn_label(getattr(candidate, "code", None), getattr(candidate, "fsn", None)))
    return labels


def _needs_row_specific_choice(suggestion: Any, replacement_options: list[str]) -> bool:
    if not replacement_options:
        return False
    status = _status_value(suggestion.status)
    return status in {
        SanitizationStatus.AMBIGUOUS_REPLACEMENT.value,
        SanitizationStatus.AMBIGUOUS_ANCESTOR.value,
        SanitizationStatus.SEMANTIC_BM25_REPLACEMENT.value,
    } or len(replacement_options) > 1


def _needs_top_k_choice(suggestion: Any) -> bool:
    return _status_value(suggestion.status) in {
        SanitizationStatus.AMBIGUOUS_REPLACEMENT.value,
        SanitizationStatus.SEMANTIC_BM25_REPLACEMENT.value,
    }


def _choice_key(row_number: int) -> str:
    return f"sanitization_replacement_choice_{row_number}"


def _document_reviewed_key(document: str) -> str:
    return f"sanitization_document_reviewed_{_safe_key(document)}"


def _safe_key(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value)[:80]


def _replacement_label(suggestion: Any) -> str:
    return _code_fsn_label(suggestion.replacement_code, suggestion.replacement_fsn) or NO_REPLACEMENT_LABEL


def _code_fsn_label(code: str | None, fsn: str | None) -> str:
    if not code:
        return ""
    return f"{code} — {fsn or ''}".strip()


def _code_from_label(label: str) -> str | None:
    if not label or label == NO_REPLACEMENT_LABEL:
        return None
    return label.split(" — ", 1)[0]


def _fsn_from_label(label: str) -> str | None:
    if not label or label == NO_REPLACEMENT_LABEL or " — " not in label:
        return None
    return label.split(" — ", 1)[1] or None


def _status_value(status: Any) -> str:
    if isinstance(status, SanitizationStatus):
        return status.value
    return str(status)
