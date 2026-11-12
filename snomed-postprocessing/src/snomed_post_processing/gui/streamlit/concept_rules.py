"""Concept-rule configuration, one-step application to review, and review controls."""
from __future__ import annotations

import dataclasses
import hashlib
import pathlib
from typing import Any

import pandas as pd
import streamlit as st

from snomed_post_processing.sanitization.concept_rules import (
    ConceptRule, DEFAULT_CONCEPT_RULES, decision_key, preview_concept_rules,
    read_rules_json, rules_json_text, split_rule_conflicts, validate_rules, preserve_rule_edits,
    validate_rule_targets,
)
from .files import save_uploaded_file
from .sidebar import GuiInputs
from snomed_post_processing.uima_processing.scope import normalize_annotators


ACTION_LABELS = {"clear_id": "Remove ID only", "replace": "Replace with concept"}
POLICY_OVERRIDE_HELP = (
    "Allow replacements outside the inclusion list or on an exclusion list. Targets must exist and be active. "
    "Does not override existing review decisions. No effect for Remove ID only."
)


def _file_signature(source):
    if isinstance(source, (str, pathlib.Path)):
        path = pathlib.Path(source)
        try:
            stat = path.stat()
            return (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
        except OSError:
            return (str(path.resolve()), None, None)
    if source is None:
        return None
    return (getattr(source, "name", ""), getattr(source, "size", None), getattr(source, "file_id", id(source)))


def source_signature(inputs: GuiInputs):
    return (
        _file_signature(st.session_state.get("zip_file")), _file_signature(inputs.hdf5_file),
        inputs.id_feature, inputs.id_prefix, inputs.annotation_types_text,
        inputs.target_view, inputs.release_blacklist_mode, _file_signature(inputs.runtime_blacklist_file),
        rules_json_text(st.session_state.get("concept_rules", DEFAULT_CONCEPT_RULES)),
        tuple(sorted(st.session_state.get("concept_rule_scope", {}).items())),
        normalize_annotators(inputs.annotators),
    )


def _lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def _rules_from_editor(rows):
    result = []
    for row in rows:
        def text(key):
            value = row.get(key)
            return "" if value is None or pd.isna(value) else str(value).strip()
        result.append(ConceptRule(
            rule_id=text("rule_id"), name=text("name"), source_code=text("source_code"),
            action={value: key for key, value in ACTION_LABELS.items()}.get(text("action"), text("action")),
            target_code=text("target_code"), enabled=bool(row.get("enabled", True)),
            override_policy=bool(row.get("override_policy", True)),
        ))
    return validate_rules(result)


def _decision_rows(decisions):
    return [{
        "Apply": item.get("apply", True), "Document": item["document"],
        "Annotator": item["annotator"], "Layer": item["layer"],
        "Offset": str(item["offset"]), "Source SCTID": item["source_code"],
        "Action": ACTION_LABELS[item["action"]], "Target SCTID": item.get("replacement_code") or "",
        "Rule": item["concept_rule"]["rule_id"],
        "Override policy": item["concept_rule"]["override_policy"],
        "Policy actually overridden": item.get("policy_overridden", False),
    } for item in decisions]


def render_concept_rules_form(inputs: GuiInputs) -> None:
    with st.expander("Concept rules", expanded=False):
        _render_concept_rules_form(inputs)


def _render_concept_rules_form(inputs: GuiInputs) -> None:
    st.caption(
        "Rules match original annotations across all documents in the selected layers and shared annotator scope (tab 1). "
        "Only IDs change; literal and other features are preserved. Rules never chain."
    )
    rules = st.session_state.get("concept_rules", DEFAULT_CONCEPT_RULES)
    upload = st.file_uploader(
        "Load concept rules JSON", type=["json"], key="concept_rules_upload",
        help="Load rule definitions into this form. Apply rules to review separately; loading does not select decisions.",
    )
    upload_key = hashlib.sha256(upload.getvalue()).hexdigest() if upload is not None else None
    if upload_key is None:
        st.session_state.pop("concept_rules_loaded_upload", None)
    elif st.session_state.get("concept_rules_loaded_upload") != upload_key:
        try:
            upload.seek(0)
            st.session_state["concept_rules"] = read_rules_json(upload)
            st.session_state["concept_rules_loaded_upload"] = upload_key
            st.session_state["concept_rules_editor_revision"] = st.session_state.get("concept_rules_editor_revision", 0) + 1
            st.rerun()
        except Exception as exc:
            st.error(f"Could not load concept rules: {exc}")
    layers = inputs.annotation_types_text
    with st.form("concept_rules_form"):
        records = [{**dataclasses.asdict(rule), "action": ACTION_LABELS[rule.action]} for rule in rules]
        edited = st.data_editor(
            pd.DataFrame(records, columns=["enabled", "rule_id", "name", "source_code", "action", "target_code", "override_policy"]),
            key=f"concept_rules_editor_{st.session_state.get('concept_rules_editor_revision', 0)}",
            num_rows="dynamic", hide_index=True, width="stretch",
            column_config={
                "enabled": st.column_config.CheckboxColumn(
                    "Enabled", default=True, required=True,
                    help="Include this rule when applying rules to review.",
                ),
                "rule_id": st.column_config.TextColumn(
                    "Rule ID", required=True, help="Unique, stable identifier for this rule; not a SNOMED concept ID.",
                ),
                "name": st.column_config.TextColumn(
                    "Name", help="Optional descriptive label; matching uses Source SCTID, not this name.",
                ),
                "source_code": st.column_config.TextColumn(
                    "Source SCTID", required=True, help="Match this concept ID on the original annotation, before any changes.",
                ),
                "action": st.column_config.SelectboxColumn(
                    "Action", options=list(ACTION_LABELS.values()), required=True,
                    help="Remove ID only keeps the annotation; Replace changes its concept ID. Neither changes literal.",
                ),
                "target_code": st.column_config.TextColumn(
                    "Target SCTID", help="Replacement concept ID. Required for Replace; leave empty for Remove ID only.",
                ),
                "override_policy": st.column_config.CheckboxColumn(
                    "Override policy", default=True, required=True,
                    help=POLICY_OVERRIDE_HELP,
                ),
            },
        )
        st.caption(
            "Override policy bypasses list restrictions—not existing review decisions "
            "or target existence/activity checks."
        )
        st.caption("Apply stages review decisions; only export/upload changes CAS files. Manual decisions are protected.")
        apply = st.form_submit_button(
            "Apply rules to review", disabled=not (st.session_state.get("zip_file") and inputs.hdf5_file),
            help="Validate rules, scan original annotations and select matching review decisions. Preserve saved Apply choices.",
        )
    if apply:
        try:
            rules = _rules_from_editor(edited.to_dict("records"))
            if not _lines(layers):
                raise ValueError("Select at least one annotation layer.")
            st.session_state["concept_rules"] = rules
            st.session_state["concept_rule_scope"] = {"layers": layers, "documents": "", "annotators": "\n".join(inputs.annotators)}
            # Import lazily to avoid coupling the rule engine to suggestion generation.
            from .sanitization_check_tab import _enforce_embedded_blacklist, _uses_custom_blacklist, _resolve_custom_blacklist_indices
            with st.spinner("Scanning original annotations for concept rules..."):
                project = save_uploaded_file(st.session_state["zip_file"], ".zip")
                hdf5 = save_uploaded_file(inputs.hdf5_file, ".hdf5")
                runtime = frozenset()
                if inputs.target_view == "release" and _uses_custom_blacklist(inputs.release_blacklist_mode):
                    if inputs.runtime_blacklist_file is None:
                        raise ValueError("Select a custom exclusion-list rule file first.")
                    _, runtime = _resolve_custom_blacklist_indices(hdf5, inputs.runtime_blacklist_file)
                decisions = preview_concept_rules(
                    project, hdf5, rules, annotation_types=_lines(layers), annotators=inputs.annotators,
                    id_prefix=inputs.id_prefix, id_feature=inputs.id_feature,
                    target_view=inputs.target_view,
                    release_exclude_blacklist=_enforce_embedded_blacklist(inputs.release_blacklist_mode),
                    runtime_blacklist_indices=runtime,
                )
            previous = st.session_state.get("concept_rule_decisions", [])
            previous_source = st.session_state.get("concept_rule_decisions_source")
            signature = source_signature(inputs)
            has_edits = any(item.get("rule_reviewed_by_human") for item in previous)
            if has_edits and previous_source is not None and previous_source[:8] != signature[:8]:
                raise ValueError("Inputs changed while manually edited rule decisions exist. Explicitly discard those decisions before applying new rules.")
            decisions = preserve_rule_edits(decisions, previous)
            st.session_state["concept_rule_decisions"] = decisions
            st.session_state["concept_rule_decisions_source"] = signature
            st.session_state.pop("concept_rule_needs_validation", None)
            st.session_state["concept_rule_review_revision"] = st.session_state.get("concept_rule_review_revision", 0) + 1
            selected = [item for item in decisions if item.get("apply")]
            removals = sum(item["action"] == "clear_id" for item in selected)
            replacements = sum(item["action"] == "replace" for item in selected)
            overrides = sum(bool(item.get("policy_overridden")) for item in selected)
            _, conflicts = _split_manual_conflicts(decisions)
            st.success(
                f"Rules applied to review: {removals} ID removal(s), {replacements} replacement(s), "
                f"{overrides} policy override(s), {len(conflicts)} manual conflict(s). "
                "Manual edits were preserved. No CAS files changed."
            )
        except Exception as exc:
            st.error(f"Could not apply concept rules to review: {exc}")
    _render_rule_decision_actions()
    st.download_button("Download concept rules JSON", rules_json_text(rules), "concept_rules.json", "application/json")


def _render_rule_decision_actions() -> None:
    decisions = st.session_state.get("concept_rule_decisions", [])
    if st.button(
        "Clear all pending rule decisions",
        disabled=not decisions,
        help="Clears every pending rule decision, including saved Apply checkbox choices. Rule definitions and CAS files are unchanged.",
    ):
        st.session_state["concept_rule_decisions"] = []
        st.session_state.pop("concept_rule_decisions_source", None)
        st.session_state["concept_rule_review_revision"] = st.session_state.get("concept_rule_review_revision", 0) + 1
        st.rerun()


def render_rule_review(inputs: GuiInputs) -> tuple[list[dict[str, Any]], bool]:
    decisions = st.session_state.get("concept_rule_decisions", [])
    if not decisions:
        return [], False
    st.subheader("Explicit concept rule decisions")
    if st.session_state.get("concept_rule_needs_validation"):
        try:
            _validate_loaded_decisions(inputs, decisions)
            st.session_state.pop("concept_rule_needs_validation", None)
        except Exception as exc:
            st.error(f"Loaded concept-rule decisions need validation before export: {exc}")
            return [], True
    binding = st.session_state.setdefault("concept_rule_decisions_source", source_signature(inputs))
    if binding != source_signature(inputs):
        st.error("Concept-rule inputs changed. Apply rules again or clear pending decisions in tab 2 (Concept rules). Export is blocked.")
        return [], True
    st.caption("Selected rule decisions are resolved. No CAS files change until explicit export/upload. Manual decisions are protected.")
    with st.form("concept_rule_review_form"):
        edited = st.data_editor(
            pd.DataFrame(_decision_rows(decisions)), hide_index=True, width="stretch",
            key=f"concept_rule_review_editor_{st.session_state.get('concept_rule_review_revision', 0)}",
            disabled=[key for key in _decision_rows(decisions)[0] if key != "Apply"],
            column_config={
                "Apply": st.column_config.CheckboxColumn(
                    "Apply", help="Include this staged action in export/upload; no project changes happen now. Uncheck to leave the annotation unchanged.",
                ),
                "Override policy": st.column_config.CheckboxColumn(
                    "Override policy", help=POLICY_OVERRIDE_HELP,
                ),
                "Policy actually overridden": st.column_config.CheckboxColumn(
                    "Policy actually overridden",
                    help="Checked only when this replacement needed the permitted exception to list restrictions. Permission alone does not mean it was used.",
                ),
            },
        )
        save = st.form_submit_button(
            "Save rule decisions", help="Save Apply-checkbox choices for these rule decisions; CAS files are unchanged.",
        )
    if save:
        decisions = [{
            **item, "apply": bool(row["Apply"]), "resolved": bool(row["Apply"]),
            "rule_reviewed_by_human": bool(item.get("rule_reviewed_by_human")) or bool(row["Apply"]) != bool(item.get("apply")),
        } for item, row in zip(decisions, edited.to_dict("records"))]
        st.session_state["concept_rule_decisions"] = decisions
    return decisions, False


def _validate_loaded_decisions(inputs, decisions):
    if inputs.hdf5_file is None:
        raise ValueError("Select a SNOMED HDF5 file.")
    from .sanitization_check_tab import _enforce_embedded_blacklist, _uses_custom_blacklist, _resolve_custom_blacklist_indices
    rules = {}
    for item in decisions:
        rule = ConceptRule(**item["concept_rule"])
        validate_rules([rule])
        if (not rule.enabled or item.get("source_code") != rule.source_code
                or item.get("action") != rule.action
                or (item.get("replacement_code") or "") != rule.target_code):
            raise ValueError("A loaded decision disagrees with its concept-rule definition.")
        if rule.rule_id in rules and rules[rule.rule_id] != rule:
            raise ValueError("Loaded rule definitions conflict.")
        rules[rule.rule_id] = rule
    hdf5 = save_uploaded_file(inputs.hdf5_file, ".hdf5")
    runtime = frozenset()
    if inputs.target_view == "release" and _uses_custom_blacklist(inputs.release_blacklist_mode):
        if inputs.runtime_blacklist_file is None:
            raise ValueError("Select a custom exclusion-list rule file first.")
        _, runtime = _resolve_custom_blacklist_indices(hdf5, inputs.runtime_blacklist_file)
    targets = validate_rule_targets(
        hdf5, rules.values(), target_view=inputs.target_view,
        release_exclude_blacklist=_enforce_embedded_blacklist(inputs.release_blacklist_mode),
        runtime_blacklist_indices=runtime,
    )
    for item in decisions:
        item["policy_overridden"] = targets.get(item["concept_rule"]["rule_id"], (None, False))[1]


def _split_manual_conflicts(rule_decisions):
    previous = st.session_state.get("sanitization_review_decisions", [])
    previous = previous + list(st.session_state.get("sanitization_restored_decisions_by_index", {}).values())
    from .sanitization_run_tab import _document_reviewed_key
    reviewed = {item.get("document") for item in previous
                if st.session_state.get(_document_reviewed_key(str(item.get("document", ""))), False)}
    return split_rule_conflicts(rule_decisions, previous, reviewed)


def protect_manual_decisions(rule_decisions):
    safe, conflicts = _split_manual_conflicts(rule_decisions)
    if conflicts:
        st.error(f"{len(conflicts)} concept-rule decision(s) conflict with manual decisions. Export is blocked until resolved.")
        if st.button(
            "Keep manual decisions for conflicts",
            help="Discard conflicting rule decisions and keep the existing manual choices.",
        ):
            keys = {decision_key(item) for item in conflicts}
            st.session_state["concept_rule_decisions"] = [item for item in rule_decisions if decision_key(item) not in keys]
            st.session_state["concept_rule_review_revision"] = st.session_state.get("concept_rule_review_revision", 0) + 1
            st.rerun()
    return safe, bool(conflicts)
