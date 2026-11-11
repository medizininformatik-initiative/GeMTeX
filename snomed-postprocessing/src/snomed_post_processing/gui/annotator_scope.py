"""Keep GUI review state inside the shared processing scope, without renumbering suggestions."""
from __future__ import annotations

import streamlit as st

from ..uima_processing.scope import annotator_in_scope, normalize_annotators


def reset_generic_review_for_new_suggestions(suggestions):
    previous = st.session_state.get("sanitization_suggestions")
    if previous is None or previous == suggestions:
        return
    had_review = any(not item.get("concept_rule") for item in st.session_state.get("sanitization_review_decisions", []))
    for key in list(st.session_state):
        if key.startswith(("sanitization_replacement_choice_", "sanitization_previous_replacement_choice_",
                           "sanitization_manual_apply_", "sanitization_manual_delete_", "sanitization_manual_edit_",
                           "sanitization_document_reviewed_", "sanitization_human_reviewed_", "sanitization_bm25_browser_")):
            st.session_state.pop(key, None)
    for key in ("sanitization_restored_decisions_by_index", "sanitization_automatic_decisions",
                "sanitization_conditions_undo", "sanitization_automatic_reviewed_documents", "sanitization_conditions_source"):
        st.session_state.pop(key, None)
    st.session_state["sanitization_review_decisions"] = [item for item in st.session_state.get("sanitization_review_decisions", []) if item.get("concept_rule")]
    st.session_state["sanitization_review_state_revision"] = st.session_state.get("sanitization_review_state_revision", 0) + 1
    if had_review:
        message = "Suggestions changed; generic review choices were reset to avoid applying them to different annotations. Restore a matching decisions JSON if needed. Concept-rule choices were retained."
        st.session_state["sanitization_review_reset_message"] = message
        st.warning(message)


def sync_annotator_scope(annotators):
    current = normalize_annotators(annotators)
    previous = st.session_state.get("processing_annotators")
    changed = tuple(previous or ()) != current
    st.session_state["processing_annotators"] = current
    excluded_indices = set()
    for index, suggestion in enumerate(st.session_state.get("sanitization_suggestions") or []):
        if not annotator_in_scope(suggestion.finding.annotator, current):
            excluded_indices.add(index)
    for key in ("sanitization_review_decisions", "concept_rule_decisions"):
        items = st.session_state.get(key, [])
        for item in items:
            if not annotator_in_scope(item.get("annotator", ""), current) and "suggestion_index" in item:
                excluded_indices.add(int(item["suggestion_index"]))
        if key in st.session_state:
            st.session_state[key] = [item for item in items if annotator_in_scope(item.get("annotator", ""), current)]
    for key in ("sanitization_restored_decisions_by_index", "sanitization_automatic_decisions"):
        if key in st.session_state:
            items = st.session_state[key]
            excluded_indices.update(int(index) for index, item in items.items()
                                    if not annotator_in_scope(item.get("annotator", ""), current))
            st.session_state[key] = {index: item for index, item in items.items()
                                     if annotator_in_scope(item.get("annotator", ""), current)}
    for index in excluded_indices:
        for prefix in ("sanitization_replacement_choice_", "sanitization_previous_replacement_choice_",
                       "sanitization_manual_apply_", "sanitization_manual_delete_", "sanitization_manual_edit_"):
            st.session_state.pop(prefix + str(index + 1), None)
    if changed:
        for key in list(st.session_state):
            if key.startswith(("sanitization_document_reviewed_", "sanitization_human_reviewed_", "sanitization_bm25_browser_")):
                st.session_state.pop(key, None)
        st.session_state.pop("sanitization_conditions_undo", None)
        st.session_state.pop("sanitization_automatic_reviewed_documents", None)
        st.session_state["sanitization_review_state_revision"] = st.session_state.get("sanitization_review_state_revision", 0) + 1
        st.sidebar.info("Annotator scope changed. Out-of-scope decisions were discarded and document review progress reset. Recheck/reapply rules as needed.")
    return current
