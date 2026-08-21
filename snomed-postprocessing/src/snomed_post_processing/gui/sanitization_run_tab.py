"""Sanitization-run tab for the Streamlit GUI."""

from __future__ import annotations

import datetime
import io
import pathlib
import tempfile
import zipfile
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
from snomed_post_processing.uima_processing.io import (
    _load_cas_from_zip_member,
    _load_typesystem_from_zip,
    _read_project,
    _yield_matching_files,
)

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

    document_texts = _project_document_text_lookup(st.session_state.get("zip_file"))
    rows = _suggestions_to_review_rows(suggestions, document_texts)
    actionable_rows = [row for row in rows if _row_has_actionable_replacement(row)]
    non_actionable_rows = [row for row in rows if not _row_has_actionable_replacement(row)]
    _render_review_summary(rows)
    _render_non_actionable_summary(non_actionable_rows)

    with st.popover("Suggestion metadata"):
        _render_suggestion_settings(st.session_state.get("sanitization_suggestions_metadata") or {})

    st.subheader("Review workspace")
    reviewed_decisions = _review_rows_to_decisions(non_actionable_rows, non_actionable_rows, {})
    if actionable_rows:
        _render_manual_choice_bulk_actions(actionable_rows)
        reviewed_decisions.extend(_render_document_review_sections(actionable_rows))
    else:
        st.info(
            "No actionable replacement suggestions are available. This can happen, "
            "for example, when the findings are blacklist-only and blacklist BM25 "
            "suggestions were not enabled."
        )
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


def _project_document_text_lookup(project_source: Any) -> dict[str, str]:
    if project_source is None:
        return {}
    upload_key = _uploaded_file_key(project_source)
    cache_key = "sanitization_project_text_lookup_key"
    if st.session_state.get(cache_key) == upload_key:
        return st.session_state.get("sanitization_project_text_lookup", {})
    try:
        data = project_source.getvalue()
        lookup = _extract_project_document_texts(data, getattr(project_source, "name", None))
    except Exception:
        lookup = {}
    st.session_state[cache_key] = upload_key
    st.session_state["sanitization_project_text_lookup"] = lookup
    return lookup


def _extract_project_document_texts(project_zip_bytes: bytes, file_name: str | None) -> dict[str, str]:
    lookup: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(project_zip_bytes)) as zip_file:
        project_documents = _read_project(zip_file, file_name or "uploaded project")
        for document_name, cas_paths in _yield_matching_files(
            project_documents,
            zip_file,
            file_name=file_name,
            allowed_extensions=[".json", ".xmi"],
        ):
            for cas_path in cas_paths:
                try:
                    typesystem = _load_typesystem_from_zip(zip_file, cas_path)
                    cas = _load_cas_from_zip_member(zip_file, cas_path, typesystem=typesystem)
                    text = _cas_document_text(cas)
                except Exception:
                    continue
                if text:
                    _store_document_text_aliases(lookup, document_name, cas_path, text)
                    break
    return lookup


def _cas_document_text(cas: Any) -> str:
    text = getattr(cas, "sofa_string", None)
    if text:
        return str(text)
    try:
        sofa = cas.get_sofa()
        text = getattr(sofa, "sofaString", None)
        if text:
            return str(text)
    except Exception:
        pass
    return ""


def _store_document_text_aliases(
    lookup: dict[str, str], document_name: str, cas_path: str, text: str
) -> None:
    path = pathlib.PurePosixPath(cas_path)
    aliases = {
        document_name,
        path.name,
        path.parent.name,
        _strip_known_suffix(document_name),
        _strip_known_suffix(path.name),
        _strip_known_suffix(path.parent.name),
    }
    for alias in aliases:
        if alias:
            lookup.setdefault(alias, text)


def _strip_known_suffix(name: str) -> str:
    lower = name.lower()
    for suffix in (".xmi", ".json", ".zip", ".ser"):
        if lower.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _keep_document_open(document: str) -> None:
    st.session_state["sanitization_keep_document_open"] = document


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
        keep_open = st.session_state.get("sanitization_keep_document_open") == document
        title = _document_review_title(document, document_rows, reviewed)
        with st.expander(title, expanded=(focus_match or keep_open) and not reviewed):
            if reviewed:
                st.success("This document section is marked as reviewed.")
            _render_document_metrics(document_rows)

            manual_rows = [row for row in document_rows if row.get("_needs_choice")]
            automatic_rows = [row for row in document_rows if not row.get("_needs_choice")]

            if manual_rows:
                st.markdown("#### Manual choices")
                _render_manual_choice_bulk_actions(
                    manual_rows,
                    label_prefix=f"document {_safe_key(document)}",
                    compact=True,
                )
                decisions.extend(_render_manual_choice_cards(manual_rows, document))

            if automatic_rows:
                st.markdown("#### Automatic suggestions")
                review_df = pd.DataFrame(automatic_rows).drop(
                    columns=["Document", "_offset", "_layer", "_status_raw"],
                    errors="ignore",
                )
                edited = st.data_editor(
                    review_df,
                    key=f"sanitization_review_editor_{_safe_key(document)}_{_review_state_revision()}",
                    width="stretch",
                    hide_index=True,
                    disabled=[
                        "#",
                        "Annotator",
                        "Source code",
                        "Covered text",
                        "Policy issue",
                        "Finding context",
                        "Suggested replacement",
                        "Why suggested",
                        "Original FSN",
                        "Status",
                    ],
                    on_change=_keep_document_open,
                    args=(document,),
                    column_config={
                        "Apply": st.column_config.CheckboxColumn(
                            "Apply",
                            help="Toggle whether this suggestion should be applied in the sanitization run.",
                        ),
                        "Policy issue": st.column_config.TextColumn(
                            "Policy issue",
                            help="Whether the original finding came from the whitelist or blacklist policy check.",
                        ),
                        "Finding context": st.column_config.TextColumn(
                            "Finding context",
                            help="Short document/location context for the original annotation.",
                        ),
                        "Suggested replacement": st.column_config.TextColumn(
                            "Suggested replacement",
                            help="Single suggested replacement for this row.",
                        ),
                        "Why suggested": st.column_config.TextColumn(
                            "Why suggested",
                            help="Short ranking or provenance hint for the candidate.",
                        ),
                        "_valid_choices": None,
                        "_choice_hints": None,
                        "_needs_choice": None,
                    },
                )
                decisions.extend(
                    _review_rows_to_decisions(edited.to_dict("records"), automatic_rows, {})
                )

            st.checkbox(
                "Document reviewed",
                key=reviewed_key,
                help=(
                    "This is separate from saving choices: it marks your review "
                    "progress and collapses this document on the next rerun."
                ),
            )
    return decisions


def _render_document_metrics(document_rows: list[dict[str, Any]]) -> None:
    selected = sum(1 for row in document_rows if _row_apply_selected(row))
    manual_total = sum(1 for row in document_rows if row.get("_needs_choice"))
    manual_selected = sum(
        1 for row in document_rows if row.get("_needs_choice") and _row_apply_selected(row)
    )
    no_replacement = sum(
        1 for row in document_rows if row.get("Suggested replacement") == NO_REPLACEMENT_LABEL
    )
    manual_text = (
        f"{manual_selected}/{manual_total} manual-review selected"
        if manual_total
        else "0 manual-review rows"
    )
    st.caption(
        f"{selected} replacement(s) selected · {manual_text} · "
        f"{no_replacement} without replacement"
    )


def _render_manual_choice_bulk_actions(
    rows: list[dict[str, Any]], *, label_prefix: str = "all", compact: bool = False
) -> None:
    manual_rows = [row for row in rows if row.get("_needs_choice")]
    if not manual_rows:
        return
    applied_count = sum(1 for row in manual_rows if _row_apply_selected(row))
    if compact:
        st.caption(
            f"Bulk actions for {len(manual_rows)} manual-choice suggestion(s) in "
            f"this document; {applied_count} currently selected."
        )
    elif applied_count == len(manual_rows):
        st.success(
            f"All {len(manual_rows)} manual-choice suggestion(s) currently have "
            "an applied replacement selected. Inspect exceptions per document before running."
        )
    else:
        st.warning(
            f"{len(manual_rows)} suggestion(s) need manual choices; "
            f"{applied_count} currently have an applied replacement selected. If the first "
            "candidate is acceptable as a review starting point, use the bulk action "
            "below and then inspect exceptions per document."
        )
    action_col1, action_col2 = st.columns(2)
    safe_label = _safe_key(label_prefix)
    with action_col1:
        if st.button(
            "Apply first candidate" if compact else "Apply first candidate to all manual choices",
            key=f"manual_apply_first_{safe_label}",
            help=(
                "Selects the first ranked candidate for each manual-choice row and "
                "marks it for application. Review carefully before running."
            ),
            width="stretch",
        ):
            _set_manual_choice_defaults(manual_rows, apply=True)
            st.rerun()
    with action_col2:
        if st.button(
            "Clear manual choices" if compact else "Clear all manual applications",
            key=f"manual_clear_{safe_label}",
            help="Keeps candidate selections but unchecks manual-choice applications.",
            width="stretch",
        ):
            _set_manual_choice_defaults(manual_rows, apply=False)
            st.rerun()


def _set_manual_choice_defaults(rows: list[dict[str, Any]], *, apply: bool) -> None:
    for row in rows:
        row_number = int(row["#"])
        options = list(row.get("_valid_choices", ()))
        choice = options[0] if options else NO_REPLACEMENT_LABEL
        if apply and choice != NO_REPLACEMENT_LABEL:
            st.session_state[_choice_key(row_number)] = choice
            st.session_state[_previous_choice_key(row_number)] = choice
            st.session_state[_manual_apply_key(row_number)] = True
        else:
            st.session_state[_manual_apply_key(row_number)] = False


def _save_manual_choice_form(document: str, row_numbers: list[int]) -> None:
    _keep_document_open(document)
    for row_number in row_numbers:
        choice = st.session_state.get(_choice_key(row_number), NO_REPLACEMENT_LABEL)
        previous_choice_key = _previous_choice_key(row_number)
        previous_choice = st.session_state.get(previous_choice_key)
        if choice == NO_REPLACEMENT_LABEL:
            st.session_state[_manual_apply_key(row_number)] = False
        elif previous_choice is not None and previous_choice != choice:
            st.session_state[_manual_apply_key(row_number)] = True
        st.session_state[previous_choice_key] = choice


def _render_manual_choice_cards(rows: list[dict[str, Any]], document: str) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    st.caption(
        "These rows need an explicit replacement choice before they can be applied. "
        "Dropdown and checkbox edits are batched; click Save to update the page."
    )
    row_numbers = [int(row["#"]) for row in rows]
    with st.form(f"manual_choice_form_{_safe_key(document)}"):
        for row in rows:
            row_number = int(row["#"])
            options = list(row.get("_valid_choices", ()))
            if not options:
                options = [NO_REPLACEMENT_LABEL]
            current_choice = st.session_state.get(_choice_key(row_number), row.get("Suggested replacement"))
            if current_choice not in options:
                current_choice = options[0]
            previous_choice_key = _previous_choice_key(row_number)
            st.session_state.setdefault(previous_choice_key, current_choice)
            with st.container(border=True):
                st.markdown(
                    f"**#{row_number} · {row.get('Source code', '')}** — "
                    f"{row.get('Covered text', '')}"
                )
                st.caption(row.get("Policy issue", "Reason: unknown"))
                st.caption(f"Text context: {row.get('Finding context', '')}")
                st.caption(
                    f"Suggestion type: {row.get('Status', '')} · Annotator: {row.get('Annotator', '')}"
                )
                if row.get("Original FSN"):
                    st.caption(f"Original FSN: {row['Original FSN']}")
                choice_hints = row.get("_choice_hints", {})
                choice = st.selectbox(
                    "Replacement candidate",
                    options=options,
                    index=options.index(current_choice),
                    key=_choice_key(row_number),
                    format_func=lambda option, hints=choice_hints: _format_choice_option(option, hints),
                )
                if choice_hint := choice_hints.get(choice):
                    st.caption(f"Selected candidate rationale: {choice_hint}")
                apply = st.checkbox(
                    "Apply this replacement",
                    value=bool(row.get("Apply")) and choice != NO_REPLACEMENT_LABEL,
                    key=_manual_apply_key(row_number),
                    disabled=choice == NO_REPLACEMENT_LABEL,
                )
            decisions.extend(
                _review_rows_to_decisions(
                    [{**row, "Apply": apply, "Suggested replacement": choice}],
                    [row],
                    {row_number: choice},
                )
            )
        st.form_submit_button(
            "Save choices",
            help="Save dropdown and apply-checkbox edits for this document.",
            on_click=_save_manual_choice_form,
            args=(document, row_numbers),
        )
    return decisions


def _document_matches_focus(
    document: str, document_rows: list[dict[str, Any]], focus: str
) -> bool:
    if focus == "All":
        return False
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
    selected = sum(1 for row in document_rows if _row_apply_selected(row))
    manual_total = sum(1 for row in document_rows if row.get("_needs_choice"))
    manual_selected = sum(
        1 for row in document_rows if row.get("_needs_choice") and _row_apply_selected(row)
    )
    no_replacement = sum(
        1 for row in document_rows if row.get("Suggested replacement") == NO_REPLACEMENT_LABEL
    )
    prefix = "✅" if reviewed else "📝"
    details = [f"{len(document_rows)} finding(s)", f"{selected} replacement(s) selected"]
    if manual_total:
        if manual_selected == manual_total:
            details.append("all manual choices selected")
        else:
            details.append(f"{manual_selected}/{manual_total} manual choices selected")
    if no_replacement:
        details.append(f"{no_replacement} no replacement")
    return f"{prefix} {document} — {' · '.join(details)}"


def _group_rows_by_document(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("Document", "")), []).append(row)
    return grouped


def _row_has_actionable_replacement(row: dict[str, Any]) -> bool:
    return bool(row.get("_valid_choices")) and row.get("Suggested replacement") != NO_REPLACEMENT_LABEL


def _row_apply_selected(row: dict[str, Any]) -> bool:
    if not row.get("_needs_choice"):
        return bool(row.get("Apply"))
    row_number = int(row["#"])
    choice = st.session_state.get(_choice_key(row_number), row.get("Suggested replacement"))
    return (
        bool(st.session_state.get(_manual_apply_key(row_number), row.get("Apply")))
        and choice != NO_REPLACEMENT_LABEL
    )


def _render_non_actionable_summary(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    st.info(
        f"{len(rows)} suggestion(s) have no actionable replacement and are excluded "
        "from the review/apply workspace."
    )
    with st.expander("Show non-actionable findings", expanded=False):
        st.dataframe(
            pd.DataFrame(rows).drop(
                columns=[
                    "Apply",
                    "_valid_choices",
                    "_choice_hints",
                    "_needs_choice",
                    "_offset",
                    "_layer",
                    "_status_raw",
                ],
                errors="ignore",
            ),
            hide_index=True,
            width="stretch",
        )


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
        st.session_state[_manual_apply_key(row_number)] = bool(decision.get("apply"))
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
            "hdf5_release_date": metadata.get("hdf5_release_date"),
            "hdf5_policy_date": metadata.get("hdf5_policy_date"),
            "hdf5_rf2_view": metadata.get("hdf5_rf2_view"),
            "finding_count": metadata.get("finding_count"),
            "suggestion_count": metadata.get("suggestion_count"),
            "settings": settings,
        }
    )


def _suggestions_to_review_rows(
    suggestions: list[Any], document_texts: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    restored_by_index = st.session_state.get("sanitization_restored_decisions_by_index", {})
    for idx, suggestion in enumerate(suggestions):
        row_number = idx + 1
        restored_decision = restored_by_index.get(idx, {})
        replacement_options, replacement_hints = _replacement_options_and_hints(suggestion)
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
                "Policy issue": _policy_issue_label(suggestion.finding),
                "Finding context": _finding_context_label(suggestion.finding, document_texts or {}),
                "Suggested replacement": selected_label if needs_choice else replacement_label,
                "Why suggested": replacement_hints.get(
                    selected_label if needs_choice else replacement_label, ""
                ),
                "Original FSN": suggestion.finding.fsn or "",
                "Status": _status_label(suggestion.status),
                "_status_raw": _status_value(suggestion.status),
                "_offset": tuple(suggestion.finding.offset),
                "_layer": suggestion.finding.layer,
                "_valid_choices": tuple(replacement_options),
                "_choice_hints": replacement_hints,
                "_needs_choice": needs_choice,
            }
        )
    return rows


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


def _replacement_options_and_hints(suggestion: Any) -> tuple[list[str], dict[str, str]]:
    labels: list[str] = []
    hints: dict[str, str] = {}
    seen = set()

    def add_label(label: str, hint: str) -> None:
        if not label:
            return
        if label not in seen:
            labels.append(label)
            seen.add(label)
        if hint and (label not in hints or hints[label].startswith("rank #")):
            hints[label] = hint

    replacement_label = _replacement_label(suggestion)
    if replacement_label != NO_REPLACEMENT_LABEL:
        add_label(replacement_label, _suggestion_rationale(suggestion, rank=1))
        if not _needs_top_k_choice(suggestion):
            return labels, hints

    for rank, candidate in enumerate(getattr(suggestion, "context_candidates", ()) or (), start=1):
        add_label(
            _code_fsn_label(getattr(candidate, "code", None), getattr(candidate, "fsn", None)),
            _candidate_rationale(candidate, rank=rank),
        )
    for rank, candidate in enumerate(getattr(suggestion, "candidates", ()) or (), start=1):
        add_label(
            _code_fsn_label(getattr(candidate, "code", None), getattr(candidate, "fsn", None)),
            _candidate_rationale(candidate, rank=rank),
        )
    return labels, hints


def _format_choice_option(option: str, hints: dict[str, str]) -> str:
    hint = hints.get(option)
    if hint:
        return f"{option} [{hint}]"
    return option


def _policy_issue_label(finding: Any) -> str:
    list_type = str(getattr(finding, "list_type", "") or "").lower()
    reason = str(getattr(finding, "reason", "") or "").replace("_", " ").strip()
    if list_type == "blacklist":
        return "Reason: blacklisted"
    if list_type == "whitelist":
        return "Reason: not on whitelist"
    return f"Reason: {reason}" if reason else "Reason: policy finding"


def _finding_context_label(finding: Any, document_texts: dict[str, str]) -> str:
    document_text = _lookup_document_text(document_texts, str(getattr(finding, "document", "")))
    offset = getattr(finding, "offset", None)
    if document_text and offset and len(offset) == 2:
        return _offset_context(document_text, int(offset[0]), int(offset[1]))
    covered_text = _compact_text(getattr(finding, "covered_text", ""), max_length=80)
    if covered_text:
        return f"… {covered_text} …"
    return "No document text context available."


def _lookup_document_text(document_texts: dict[str, str], document: str) -> str:
    for alias in (document, _strip_known_suffix(document)):
        if alias in document_texts:
            return document_texts[alias]
    return ""


def _offset_context(text: str, begin: int, end: int, *, word_window: int = 2, char_window: int = 25) -> str:
    if begin < 0 or end < begin or begin > len(text):
        return _character_context(text, begin, end, char_window=char_window)
    end = min(end, len(text))
    left_words = text[:begin].split()
    right_words = text[end:].split()
    target = _compact_text(text[begin:end], max_length=80)
    if left_words or right_words:
        left = " ".join(left_words[-word_window:])
        right = " ".join(right_words[:word_window])
        return f"… {left} [{target}] {right} …".replace("  ", " ").strip()
    return _character_context(text, begin, end, char_window=char_window)


def _character_context(text: str, begin: int, end: int, *, char_window: int) -> str:
    begin = max(0, min(begin, len(text)))
    end = max(begin, min(end, len(text)))
    left = _compact_text(text[max(0, begin - char_window):begin], max_length=char_window)
    target = _compact_text(text[begin:end], max_length=80)
    right = _compact_text(text[end:min(len(text), end + char_window)], max_length=char_window)
    return f"… {left} [{target}] {right} …".replace("  ", " ").strip()


def _compact_text(value: Any, *, max_length: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1].rstrip()}…"


def _suggestion_rationale(suggestion: Any, *, rank: int) -> str:
    if hasattr(suggestion, "score"):
        return (
            f"rank #{rank} · BM25 {float(getattr(suggestion, 'score', 0.0)):.2f}"
        )
    association_type = getattr(suggestion, "association_type", None)
    if association_type:
        return f"rank #{rank} · {association_type}"
    return f"rank #{rank} · {_status_label(getattr(suggestion, 'status', 'suggested'))}"


def _candidate_rationale(candidate: Any, *, rank: int) -> str:
    if hasattr(candidate, "score"):
        parts = [
            f"rank #{rank}",
            f"BM25 {float(getattr(candidate, 'score', 0.0)):.2f}",
            f"lexical {float(getattr(candidate, 'lexical_score', 0.0)):.2f}",
        ]
        semantic_tag = getattr(candidate, "semantic_tag", None)
        if semantic_tag:
            parts.append(str(semantic_tag))
        return " · ".join(parts)
    association_type = getattr(candidate, "association_type", None)
    parts = [f"rank #{rank}"]
    if association_type:
        parts.append(str(association_type))
    effective_time = getattr(candidate, "effective_time", None)
    if effective_time:
        parts.append(f"effective {effective_time}")
    return " · ".join(parts)


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


def _manual_apply_key(row_number: int) -> str:
    return f"sanitization_manual_apply_{row_number}"


def _previous_choice_key(row_number: int) -> str:
    return f"sanitization_previous_replacement_choice_{row_number}"


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


def _status_label(status: Any) -> str:
    labels = {
        SanitizationStatus.HISTORICAL_ASSOCIATION_REPLACEMENT.value: "Historical association",
        SanitizationStatus.SEMANTIC_BM25_REPLACEMENT.value: "BM25/manual review",
        SanitizationStatus.NEAREST_TARGET_ANCESTOR.value: "Nearest active ancestor",
        SanitizationStatus.NEAREST_HISTORICAL_ANCESTOR.value: "Nearest historical ancestor",
        SanitizationStatus.AMBIGUOUS_REPLACEMENT.value: "Ambiguous replacement",
        SanitizationStatus.AMBIGUOUS_ANCESTOR.value: "Ambiguous ancestor",
        SanitizationStatus.NO_POLICY_ACCEPTABLE_CANDIDATE.value: "No acceptable candidate",
        SanitizationStatus.NO_HISTORICAL_ASSOCIATION.value: "No historical association",
        SanitizationStatus.BLACKLISTED_NO_AUTO_SANITIZATION.value: "Blacklisted/no automatic sanitization",
    }
    value = _status_value(status)
    return labels.get(value, value.replace("_", " ").title())


def _status_value(status: Any) -> str:
    if isinstance(status, SanitizationStatus):
        return status.value
    return str(status)
