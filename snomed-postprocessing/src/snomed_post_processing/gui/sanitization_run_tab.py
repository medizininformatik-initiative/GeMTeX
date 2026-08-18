"""Sanitization-run tab for the Streamlit GUI."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from snomed_post_processing.sanitization import read_sanitization_suggestions_json_with_metadata
from snomed_post_processing.sanitization.models import SanitizationStatus

from .sidebar import GuiInputs


NO_REPLACEMENT_LABEL = "— no replacement selected —"


def render_sanitization_run_tab(inputs: GuiInputs) -> None:
    st.write("Review sanitization suggestions before applying them back to CAS documents.")

    uploaded_suggestions_file = st.file_uploader(
        "Sanitization suggestions JSON",
        type=["json"],
        help="Upload suggestions saved from the sanitization-check tab, or use suggestions from this session.",
    )
    if uploaded_suggestions_file is not None and st.button("Load suggestions JSON"):
        try:
            suggestions, metadata = read_sanitization_suggestions_json_with_metadata(uploaded_suggestions_file)
            st.session_state["sanitization_suggestions"] = suggestions
            st.session_state["sanitization_suggestions_metadata"] = metadata
            st.session_state["sanitization_suggestions_report_path"] = None
            st.session_state["sanitization_suggestions_json_path"] = uploaded_suggestions_file.name
            st.success(f"Loaded suggestions from {uploaded_suggestions_file.name}.")
        except Exception as exc:
            st.error(f"Could not load sanitization suggestions JSON: {exc}")

    suggestions = st.session_state.get("sanitization_suggestions")
    if not suggestions:
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

    _render_suggestion_settings(st.session_state.get("sanitization_suggestions_metadata") or {})

    rows = _suggestions_to_review_rows(suggestions)
    st.caption(
        "Highlighted cells in 'Suggested replacement' are controlled by row-specific "
        "selection widgets below the table and require explicit review before applying."
    )
    review_df = pd.DataFrame(rows)
    edited = st.data_editor(
        _style_review_table(review_df),
        key="sanitization_review_editor",
        width="stretch",
        hide_index=True,
        disabled=[
            "#",
            "Document",
            "Source code",
            "Covered text",
            "Original FSN",
            "Status",
            "Suggested replacement",
        ],
        column_config={
            "Apply": st.column_config.CheckboxColumn(
                "Apply",
                help="Toggle whether this suggestion should be applied in the sanitization run.",
            ),
            "Suggested replacement": st.column_config.TextColumn(
                "Suggested replacement",
                help="Unambiguous replacement, or a prompt to choose below for ambiguous suggestions.",
            ),
            "_valid_choices": None,
            "_needs_choice": None,
        },
    )

    row_choices = _render_row_choice_controls(rows)
    reviewed_decisions = _review_rows_to_decisions(edited.to_dict("records"), rows, row_choices)
    st.session_state["sanitization_review_decisions"] = reviewed_decisions

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

    st.info(
        "CAS write-back is still not implemented. This tab currently prepares reviewed "
        "replacement decisions for the next implementation step."
    )
    st.button("Run sanitization", type="primary", disabled=True)


def _render_suggestion_settings(metadata: dict[str, Any]) -> None:
    settings = metadata.get("settings") if isinstance(metadata, dict) else None
    if not isinstance(settings, dict):
        st.caption("No sanitization-generation settings found in the loaded suggestions JSON.")
        return
    with st.expander("Settings used to generate these suggestions", expanded=False):
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
    for idx, suggestion in enumerate(suggestions):
        replacement_options = _replacement_options(suggestion)
        replacement_label = _replacement_label(suggestion)
        is_automatic_replacement = replacement_label != NO_REPLACEMENT_LABEL
        needs_choice = _needs_row_specific_choice(suggestion, replacement_options)
        selected_label = st.session_state.get(
            _choice_key(idx + 1),
            replacement_options[0] if replacement_options else NO_REPLACEMENT_LABEL,
        )
        rows.append(
            {
                "#": idx + 1,
                "Apply": is_automatic_replacement and not needs_choice,
                "Document": suggestion.finding.document,
                "Source code": suggestion.finding.code or "",
                "Covered text": suggestion.finding.covered_text,
                "Original FSN": suggestion.finding.fsn or "",
                "Status": _status_value(suggestion.status),
                "Suggested replacement": selected_label if needs_choice else replacement_label,
                "_valid_choices": tuple(replacement_options),
                "_needs_choice": needs_choice,
            }
        )
    return rows


def _render_row_choice_controls(rows: list[dict[str, Any]]) -> dict[int, str]:
    choice_rows = [row for row in rows if row.get("_needs_choice")]
    if not choice_rows:
        return {}

    st.subheader("Replacement choices")
    st.caption(
        "Choose row-specific replacements for ambiguous suggestions and semantic BM25 suggestions. "
        "Options can include the nearest rejected ancestor and retained BM25 candidates."
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
                "source_code": edited.get("Source code", ""),
                "replacement_choice": choice,
                "replacement_code": _code_from_label(choice) if valid_choice else None,
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


def _status_value(status: Any) -> str:
    if isinstance(status, SanitizationStatus):
        return status.value
    return str(status)
