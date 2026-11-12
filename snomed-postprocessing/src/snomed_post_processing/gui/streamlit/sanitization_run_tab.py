"""Sanitization-run tab for the Streamlit GUI."""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import io
import json
import logging
import math
import pathlib
import tempfile
import zipfile
from functools import partial
from typing import Any

import pandas as pd
import streamlit as st

from snomed_post_processing.sanitization import (
    read_sanitization_decisions_json,
    read_sanitization_suggestions_json_with_metadata,
    sanitization_decisions_json_text,
)

from .downloads import download_json_report
from snomed_post_processing.sanitization.models import (
    ASSOCIATION_TYPE_DESCRIPTIONS, SanitizationStatus, SUPPORTED_ASSOCIATION_TYPES,
)
from snomed_post_processing.sanitization.json_io import sanitization_suggestion_to_dict
from snomed_post_processing.sanitization.conditions import (
    DEFAULT_CONDITION_ASSOCIATIONS, apply_conditions, undo_automatic_conditions,
    bm25_assessments, decision_selection,
)
from snomed_post_processing.pipelines import apply_decisions_and_upload_to_inception
from snomed_post_processing.pipelines.sanitization_run import run_sanitization
from snomed_post_processing.uima_processing.io import (
    _annotator_name_from_cas_path,
    _load_cas_from_zip_member,
    _load_typesystem_from_zip,
    _read_project,
    _yield_matching_files,
)

from .file_sources import render_file_source_selector
from .files import save_uploaded_file
from .sidebar import GuiInputs
from .annotator_scope import sync_annotator_scope, reset_generic_review_for_new_suggestions
from snomed_post_processing.uima_processing.scope import annotator_in_scope, normalize_annotators, scope_covers
from .concept_rules import render_rule_review, protect_manual_decisions
from snomed_post_processing.sanitization.concept_rules import decision_key


logger = logging.getLogger(__name__)

NO_REPLACEMENT_LABEL = "— no replacement selected —"


def render_sanitization_run_tab(inputs: GuiInputs) -> None:
    st.write("Review sanitization suggestions before applying them back to CAS documents.")

    st.subheader("Sources")
    _render_suggestion_source_selector(inputs)
    _render_decision_source_selector(inputs)
    inputs.annotators = sync_annotator_scope(inputs.annotators)
    if st.session_state.get("sanitization_review_reset_message"):
        st.warning(st.session_state.pop("sanitization_review_reset_message"))

    if st.session_state.get("sanitization_last_load_message"):
        st.success(st.session_state.pop("sanitization_last_load_message"))

    suggestions = st.session_state.get("sanitization_suggestions") or []
    try:
        _validate_restored_suggestion_indices(list(st.session_state.get("sanitization_restored_decisions_by_index", {}).values()), suggestions)
    except ValueError as exc:
        st.error(str(exc))
        st.button("Run sanitization", disabled=True)
        return
    produced_for = (st.session_state.get("sanitization_suggestions_metadata") or {}).get("annotators", ())
    if not scope_covers(produced_for, inputs.annotators):
        st.warning("Suggestions were generated for a narrower annotator scope. Regenerate suggestions or load matching suggestions JSON.")
        suggestions = []
    _prepare_automatic_condition_source(suggestions)
    rule_decisions, rule_invalid = render_rule_review(inputs)
    rule_decisions, rule_conflicts = protect_manual_decisions(rule_decisions)
    rule_invalid = rule_invalid or rule_conflicts
    if not suggestions and st.session_state.get("sanitization_restored_decisions_by_index"):
        rule_invalid = True
        st.warning("Load the matching suggestions before exporting restored non-rule review decisions.")
    if not suggestions and not rule_decisions and not rule_invalid:
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

    in_scope_count = sum(annotator_in_scope(item.finding.annotator, inputs.annotators) for item in suggestions)
    st.caption(f"Loaded {in_scope_count} in-scope generic suggestion(s) and {len(rule_decisions)} explicit concept-rule decision(s).")
    json_path = st.session_state.get("sanitization_suggestions_json_path")
    if json_path:
        st.caption(f"Suggestions JSON: `{json_path}`")
    report_path = st.session_state.get("sanitization_suggestions_report_path")
    if report_path:
        st.caption(f"Suggestion report: `{report_path}`")

    document_texts = _project_document_text_lookup(st.session_state.get("zip_file"), annotators=inputs.annotators)
    metadata_contexts = _metadata_finding_context_lookup(
        st.session_state.get("sanitization_suggestions_metadata") or {}
    )
    _log_missing_context_documents([item for item in suggestions if annotator_in_scope(item.finding.annotator, inputs.annotators)], document_texts, metadata_contexts)
    rows = _suggestions_to_review_rows(suggestions, document_texts, metadata_contexts, annotators=inputs.annotators)
    # Preserve original suggestion indices; explicit rules reserve their annotations
    # even when deselected, rather than exposing an unrelated fallback candidate.
    rule_keys = {decision_key(item) for item in rule_decisions}
    rows = [row for row in rows if (
        row["Document"], row["Annotator"], row.get("_layer"),
        tuple(row.get("_offset") or ()), row["Source code"],
    ) not in rule_keys]
    if rows:
        _render_review_summary(rows)

    with st.popover("Suggestion metadata"):
        _render_suggestion_settings(st.session_state.get("sanitization_suggestions_metadata") or {})

    st.subheader("Review workspace")
    st.caption(
        "Concept-rule actions are reviewed above. For each remaining finding, apply a selected replacement, delete the matched annotation, or mark it for manual editing in the sanitized copy."
    )
    st.caption(
        "Checkbox behavior: no selection keeps the annotation unchanged; Needs manual edit takes precedence over Apply/Delete; deletion takes precedence over Apply."
    )
    manual_review_layer = st.text_input(
        "Manual-review marker layer",
        value=st.session_state.get("manual_review_layer", "webanno.custom.ManualReview"),
        key="manual_review_layer",
        help="Layer added to the sanitized project for rows marked 'Needs manual edit'.",
    )
    reviewed_decisions = list(rule_decisions)
    if rows:
        _render_automatic_conditions(suggestions, rows, rule_decisions)
        reviewed_decisions.extend(_render_document_review_sections(rows))
    else:
        st.info("No additional generic suggestions to review.")
    st.session_state["sanitization_review_decisions"] = reviewed_decisions

    decisions_metadata = _decisions_metadata(rows)
    decisions_metadata["annotators"] = list(inputs.annotators)
    decisions_metadata["concept_rule_scope"] = st.session_state.get("concept_rule_scope", {})
    decisions_metadata["concept_rules"] = (
        [dataclasses.asdict(rule) for rule in st.session_state["concept_rules"]]
        if "concept_rules" in st.session_state else list({
            item["concept_rule"]["rule_id"]: item["concept_rule"] for item in rule_decisions
        }.values())
    )
    # Rule-only documents are reviewed only when all their decisions are selected.
    rule_documents = {item["document"] for item in rule_decisions} - {row["Document"] for row in rows}
    auto_reviewed = {doc for doc in rule_documents if all(
        item.get("apply") for item in rule_decisions if item["document"] == doc
    )}
    if auto_reviewed:
        st.caption(f"Automatically reviewed {len(auto_reviewed)} rule-only document section(s): {', '.join(sorted(auto_reviewed))}.")
    decisions_metadata["reviewed_documents"] = sorted(set(decisions_metadata["reviewed_documents"]) | auto_reviewed)
    decisions_metadata["document_count"] = len({item["document"] for item in reviewed_decisions})
    decisions_text = sanitization_decisions_json_text(reviewed_decisions, metadata=decisions_metadata)

    invalid_selected_rows = [
        decision for decision in reviewed_decisions if decision["apply"] and not decision["valid_choice"]
    ]
    delete_count = sum(1 for decision in reviewed_decisions if decision.get("action") == "delete")
    manual_edit_count = sum(1 for decision in reviewed_decisions if decision.get("action") == "manual_edit")
    clear_id_count = sum(1 for decision in reviewed_decisions if decision.get("action") == "clear_id" and decision.get("apply"))
    replacement_count = sum(1 for decision in reviewed_decisions if decision.get("action") == "replace" and decision.get("apply"))
    selected_count = replacement_count + delete_count + manual_edit_count + clear_id_count
    st.caption(
        f"Selected {replacement_count} replacement(s), {clear_id_count} ID removal(s), {delete_count} deletion(s), "
        f"and {manual_edit_count} manual-edit marker(s) for the future sanitization run."
    )
    if invalid_selected_rows:
        st.warning(
            "Some selected rows use a replacement choice that is not valid for that row. "
            "Please choose one of the row's candidate options."
        )

    _render_sanitization_run_controls(
        reviewed_decisions,
        decisions_text,
        selected_count=selected_count,
        has_invalid_selected_rows=bool(invalid_selected_rows) or rule_invalid,
        manual_review_layer=manual_review_layer,
        id_prefix=inputs.id_prefix,
        id_feature=inputs.id_feature,
        annotators=inputs.annotators,
    )


def _render_suggestion_source_selector(inputs: GuiInputs) -> None:
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

    suggestions_selection = render_file_source_selector(
        "Sanitization suggestions JSON",
        key="sanitization_suggestions_json",
        data_dir=inputs.data_dir,
        suffixes=(".json",),
        upload_types=("json",),
        default_source="Upload",
        help="Load suggestions saved from the sanitization-check tab.",
    )
    if suggestions_selection.value is None:
        return
    upload_key = _selected_file_key(suggestions_selection.value)
    if st.session_state.get("loaded_sanitization_suggestions_upload_key") == upload_key:
        return
    try:
        suggestions, metadata = read_sanitization_suggestions_json_with_metadata(
            suggestions_selection.value
        )
        reset_generic_review_for_new_suggestions(suggestions)
        st.session_state["sanitization_suggestions"] = suggestions
        st.session_state["sanitization_suggestions_metadata"] = metadata
        st.session_state["sanitization_suggestions_report_path"] = None
        st.session_state["sanitization_suggestions_json_path"] = _selected_file_name(suggestions_selection.value)
        st.session_state["loaded_sanitization_suggestions_upload_key"] = upload_key
        _bump_review_state_revision()
        st.session_state["sanitization_last_load_message"] = (
            f"Loaded suggestions from {_selected_file_name(suggestions_selection.value)}."
        )
        st.rerun()
    except Exception as exc:
        st.error(f"Could not load sanitization suggestions JSON: {exc}")


def _render_decision_source_selector(inputs: GuiInputs) -> None:
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

    decisions_selection = render_file_source_selector(
        "Reviewed sanitization decisions JSON",
        key="sanitization_decisions_json",
        data_dir=inputs.data_dir,
        suffixes=(".json",),
        upload_types=("json",),
        default_source="Upload",
        help="Load a previously saved review state after loading/generating matching suggestions.",
    )
    if decisions_selection.value is None:
        st.session_state.pop("loaded_sanitization_decisions_upload_key", None)
        return
    upload_key = _selected_file_key(decisions_selection.value)
    if st.session_state.get("loaded_sanitization_decisions_upload_key") == upload_key:
        return
    try:
        decisions, metadata = read_sanitization_decisions_json(decisions_selection.value)
        if not scope_covers(metadata.get("annotators", ()), inputs.annotators):
            raise ValueError("Reviewed decisions were saved for a narrower annotator scope. Select matching annotators in tab 1 before loading them.")
        _restore_decision_state(decisions, metadata, annotators=inputs.annotators)
        st.session_state["loaded_sanitization_decisions_upload_key"] = upload_key
        _bump_review_state_revision()
        st.session_state["sanitization_last_load_message"] = (
            f"Loaded reviewed decisions from {_selected_file_name(decisions_selection.value)}."
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
            f"Ready to run: project ZIP loaded and {selected_count} reviewed "
            "action(s) selected."
        )
        return

    messages = []
    if project_loaded:
        messages.append("✅ Project ZIP loaded")
    else:
        messages.append("❌ Upload or load an INCEpTION project ZIP in the sidebar")
    if selected_count > 0:
        messages.append(f"✅ {selected_count} reviewed action(s) selected")
    else:
        messages.append("❌ Select at least one replacement or deletion action")
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
    manual_review_layer: str = "webanno.custom.ManualReview",
    id_prefix: str = "http://snomed.info/id/",
    id_feature: str = "id",
    annotators=(),
) -> None:
    if any(not annotator_in_scope(item.get("annotator", ""), annotators) for item in reviewed_decisions):
        st.error("Review contains decisions outside the current annotator scope. Reload or regenerate matching decisions.")
        return
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
                help="Save review choices and progress to restore later with matching suggestions. This does not export a project.",
            )
            st.caption("Save this JSON to restore the current review state later.")
    _render_inception_apply_upload_controls(
        project_source=project_source,
        reviewed_decisions=reviewed_decisions,
        decisions_text=decisions_text,
        selected_count=selected_count,
        has_invalid_selected_rows=has_invalid_selected_rows,
        manual_review_layer=manual_review_layer,
        id_prefix=id_prefix,
        id_feature=id_feature,
        annotators=annotators,
    )

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
                manual_review_layer=manual_review_layer.strip() or "webanno.custom.ManualReview",
                id_prefix=id_prefix,
                id_feature=id_feature,
                annotator_filter=set(annotators) or None,
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


def _render_inception_apply_upload_controls(
    *,
    project_source: Any,
    reviewed_decisions: list[dict[str, Any]],
    decisions_text: str,
    selected_count: int,
    has_invalid_selected_rows: bool,
    manual_review_layer: str,
    id_prefix: str,
    id_feature: str,
    annotators=(),
) -> None:
    if any(not annotator_in_scope(item.get("annotator", ""), annotators) for item in reviewed_decisions):
        st.error("Deployment contains decisions outside the current annotator scope.")
        return
    st.subheader("Apply decisions and upload to INCEpTION")
    st.caption(
        "One-step deployment workflow: original project ZIP + reviewed decisions → schema shell ZIP "
        "→ repaired flattened CAS artifacts → INCEpTION dry-run or upload. The original ZIP is not modified."
    )
    disabled = project_source is None or selected_count == 0 or has_invalid_selected_rows
    with st.expander("INCEpTION deployment settings", expanded=False):
        with st.form("inception_pipeline_form"):
            project_name = st.text_input(
                "Sanitized project name",
                value="",
                key="inception_pipeline_project_name",
                help="Optional. Leave empty to derive a sanitized name from the source project metadata.",
            )
            project_slug = st.text_input(
                "Sanitized project slug",
                value="",
                key="inception_pipeline_project_slug",
                help="Optional. Leave empty to derive a valid sanitized slug.",
            )
            inception_url = st.text_input(
                "INCEpTION URL",
                value=st.session_state.get("inception_pipeline_url", ""),
                key="inception_pipeline_url",
                placeholder="http://localhost:8080",
                help="Base URL of the target INCEpTION server, including any deployment path.",
            )
            col1, col2 = st.columns(2)
            with col1:
                username = st.text_input("Username", key="inception_pipeline_username")
            with col2:
                password = st.text_input("Password", type="password", key="inception_pipeline_password")
            annotation_user = st.text_input(
                "Annotation user",
                value=st.session_state.get("inception_pipeline_annotation_user", ""),
                key="inception_pipeline_annotation_user",
                help="Optional. Defaults to the username. Flattened uploads are assigned to this user.",
            )
            check_connection = st.checkbox(
                "Check connection during dry-run",
                value=False,
                key="inception_pipeline_check_connection",
                help="Contact INCEpTION to check connectivity during dry-run; no project or annotations are uploaded.",
            )
            no_verify_tls = st.checkbox(
                "Disable TLS verification",
                value=True,
                key="inception_pipeline_no_verify_tls",
                help="Skip HTTPS certificate checks. This weakens connection security; prefer configuring trusted certificates.",
            )
            apply_remote = st.checkbox(
                "Apply to INCEpTION now (imports project and uploads artifacts)",
                value=False,
                key="inception_pipeline_apply_remote",
                help="Leave unchecked for offline preparation / dry-run. Check only when you are ready to write to INCEpTION.",
            )
            force = st.checkbox(
                "Overwrite temporary pipeline outputs if needed",
                value=True,
                key="inception_pipeline_force",
                help="Allow overwriting generated files in the temporary output folder; not a remote-project overwrite setting.",
            )
            clicked = st.form_submit_button(
                "Run INCEpTION deployment pipeline",
                help="Prepare deployment artifacts. Remote import/upload occurs only when Apply to INCEpTION now is checked.",
                disabled=disabled,
                type="primary",
                width="stretch",
            )
    if disabled:
        st.info("Load a project ZIP, select valid reviewed actions, then run the INCEpTION deployment pipeline.")
    if not clicked:
        return
    try:
        with st.status("Running INCEpTION deployment pipeline...", expanded=True) as status:
            st.write("Saving original project ZIP and reviewed decisions JSON...")
            input_project = save_uploaded_file(project_source, ".zip")
            output_dir = pathlib.Path(tempfile.mkdtemp(prefix="snomed_gui_inception_pipeline_"))
            decisions_path = output_dir / "reviewed_sanitization_decisions.json"
            decisions_path.write_text(decisions_text, encoding="utf-8")
            st.write("Building shell project ZIP and repaired upload artifacts...")
            result = apply_decisions_and_upload_to_inception(
                source_project=input_project,
                decisions_path=decisions_path,
                output_dir=output_dir,
                project_name=project_name.strip() or None,
                project_slug=project_slug.strip() or None,
                manual_review_layer=manual_review_layer.strip() or "webanno.custom.ManualReview",
                id_prefix=id_prefix,
                id_feature=id_feature,
                inception_url=inception_url.strip() or None,
                username=username.strip() or None,
                password=password or None,
                annotation_user=annotation_user.strip() or None,
                apply=bool(apply_remote),
                check_connection=bool(check_connection),
                verify_tls=not no_verify_tls,
                force=force,
                annotator_filter=tuple(annotators),
            )
            status.update(label="INCEpTION deployment pipeline finished.", state="complete", expanded=False)
        issue_count = sum(artifact.remote_upload_issue_count for artifact in result.artifacts_result.artifacts)
        if result.deployment_result.errors:
            st.error(f"Pipeline finished with {len(result.deployment_result.errors)} error(s). See report below.")
        elif result.applied:
            st.success(f"Uploaded {result.deployment_result.planned_upload_count} artifact(s) to INCEpTION.")
        else:
            st.success(f"Dry-run complete. Planned uploads: {result.deployment_result.planned_upload_count}.")
        st.caption(f"Remote-upload compatibility issues remaining: {issue_count}")
        if result.deployment_result.warnings:
            st.warning("\n".join(f"- {warning}" for warning in result.deployment_result.warnings))
        _render_inception_pipeline_downloads(result)
    except Exception as exc:
        st.error(f"INCEpTION deployment pipeline failed: {exc}")


def _render_inception_pipeline_downloads(result: Any) -> None:
    st.download_button(
        "Download shell project ZIP",
        help="Project structure prepared for import; repaired annotation payloads are downloaded separately.",
        data=result.shell_project.read_bytes(),
        file_name=result.shell_project.name,
        mime="application/zip",
    )
    artifacts_zip = _zip_directory_bytes(result.upload_artifacts_dir)
    st.download_button(
        "Download repaired upload artifacts ZIP",
        help="Repaired, flattened CAS files prepared for upload to INCEpTION.",
        data=artifacts_zip,
        file_name="inception-upload-artifacts.zip",
        mime="application/zip",
    )
    st.download_button(
        "Download pipeline report JSON",
        help="Deployment results, planned uploads and diagnostics; not a saved review state.",
        data=result.pipeline_report_path.read_bytes(),
        file_name=result.pipeline_report_path.name,
        mime="application/json",
    )


def _zip_directory_bytes(directory: pathlib.Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for path in sorted(pathlib.Path(directory).rglob("*")):
            if path.is_file():
                zip_file.writestr(path.relative_to(directory).as_posix(), path.read_bytes())
    return buffer.getvalue()


def _uploaded_file_key(uploaded_file: Any) -> tuple[str, int | None]:
    return (getattr(uploaded_file, "name", ""), getattr(uploaded_file, "size", None))


def _selected_file_key(selected_file: Any) -> tuple[str, int | None]:
    if isinstance(selected_file, pathlib.Path):
        try:
            return (str(selected_file.resolve()), selected_file.stat().st_size)
        except OSError:
            return (str(selected_file), None)
    return _uploaded_file_key(selected_file)


def _selected_file_name(selected_file: Any) -> str:
    if isinstance(selected_file, pathlib.Path):
        return selected_file.name
    return getattr(selected_file, "name", "")


def _project_document_text_lookup(project_source: Any, *, annotators=()) -> dict[str, str]:
    if project_source is None:
        logger.debug("Context extraction skipped: no project ZIP selected.")
        return {}
    upload_key = (_selected_file_key(project_source), normalize_annotators(annotators))
    cache_key = "sanitization_project_text_lookup_key"
    if st.session_state.get(cache_key) == upload_key:
        return st.session_state.get("sanitization_project_text_lookup", {})
    try:
        if isinstance(project_source, pathlib.Path):
            data = project_source.read_bytes()
            source_name = project_source.name
        else:
            data = project_source.getvalue()
            source_name = getattr(project_source, "name", None)
        lookup = _extract_project_document_texts(data, source_name, annotators=annotators)
    except Exception:
        logger.exception("Could not extract review context from the selected project ZIP.")
        lookup = {}
    if not lookup:
        logger.warning(
            "Review context lookup is empty for the selected project ZIP. "
            "Extraction failures are logged above; reselect/reload the project to retry."
        )
    st.session_state[cache_key] = upload_key
    st.session_state["sanitization_project_text_lookup"] = lookup
    return lookup


def _extract_project_document_texts(project_zip_bytes: bytes, file_name: str | None, *, annotators=()) -> dict[str, str]:
    annotators = normalize_annotators(annotators)
    lookup: dict[str, str] = {}
    documents_seen = documents_loaded = cas_failures = empty_texts = 0
    with zipfile.ZipFile(io.BytesIO(project_zip_bytes)) as zip_file:
        project_documents = _read_project(zip_file, file_name or "uploaded project")
        for document_name, cas_paths in _yield_matching_files(
            project_documents,
            zip_file,
            file_name=file_name,
            allowed_extensions=[".json", ".xmi"],
        ):
            cas_paths = [path for path in cas_paths if annotator_in_scope(
                _annotator_name_from_cas_path(path, fallback_flat_layout=project_documents is None), annotators)]
            if not cas_paths:
                continue
            documents_seen += 1
            for cas_path in cas_paths:
                stage = "typesystem loading"
                try:
                    typesystem = _load_typesystem_from_zip(zip_file, cas_path)
                    stage = "CAS loading"
                    cas = _load_cas_from_zip_member(zip_file, cas_path, typesystem=typesystem)
                    stage = "sofa text extraction"
                    text = _cas_document_text(cas)
                except Exception:
                    cas_failures += 1
                    logger.exception(
                        "Context extraction failed during %s: document=%r, CAS member=%r",
                        stage, document_name, cas_path,
                    )
                    continue
                if text:
                    _store_document_text_aliases(lookup, document_name, cas_path, text)
                    documents_loaded += 1
                    break
                empty_texts += 1
                logger.warning("CAS has no document text: document=%r, CAS member=%r", document_name, cas_path)
            else:
                logger.warning("No usable context found for document=%r", document_name)
    logger.warning(
        "Review context extraction summary: documents discovered=%d, loaded=%d, "
        "failed CAS attempts=%d, empty-text CAS=%d, lookup aliases=%d",
        documents_seen, documents_loaded, cas_failures, empty_texts, len(lookup),
    )
    if not documents_seen:
        logger.warning("No matching JSON/XMI documents found in the selected project ZIP; check its archive layout.")
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
        logger.exception("Could not read sofa text from CAS via get_sofa().")
    return ""


def _log_missing_context_documents(
    suggestions: list[Any],
    document_texts: dict[str, str],
    metadata_contexts: dict,
) -> None:
    """Report missing context once per distinct result, not on every rerun."""
    missing = sorted({
        str(getattr(suggestion.finding, "document", ""))
        for suggestion in suggestions
        if not _lookup_document_text(document_texts, str(getattr(suggestion.finding, "document", "")))
        and not metadata_contexts.get(_finding_context_key(suggestion.finding))
    })
    signature = tuple(missing)
    key = "sanitization_missing_context_log_signature"
    if st.session_state.get(key) == signature:
        return
    st.session_state[key] = signature
    if missing:
        logger.warning(
            "Review context unavailable for %d document(s): %r. "
            "No matching project text or saved context snippet was found. "
            "Check the selected ZIP and exact document names (lookup aliases=%d).",
            len(missing), missing, len(document_texts),
        )


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
    st.session_state[f"sanitization_human_reviewed_{_safe_key(document)}"] = True
    st.session_state["sanitization_keep_document_open"] = document


def _mark_document_reviewed(document: str) -> None:
    st.session_state[f"sanitization_human_reviewed_{_safe_key(document)}"] = True
    st.session_state[_document_reviewed_key(document)] = True
    st.session_state.pop("sanitization_keep_document_open", None)


def _save_current_document_review_state(document: str, manual_row_numbers: list[int]) -> None:
    if st.session_state.get(_document_reviewed_key(document), False):
        _save_manual_choice_form(document, manual_row_numbers)
        st.session_state[_document_reviewed_key(document)] = True


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
    st.markdown("**Open document sections**")
    st.caption("Opening controls only—not filters. All documents and review choices remain available.")
    focus = st.session_state.get("sanitization_review_focus", "Collapse all")
    opening_help = {
        "All": "Open every document section, including reviewed sections. Does not select or apply any decisions.",
        "Needs choice": "Open unreviewed sections with an unresolved multi-choice row. Applied replacements, deletions and manual-edit selections count as resolved choices.",
        "No replacement": "Open unreviewed sections with a row showing 'no replacement selected'. Candidates may still be available; this is not a zero-candidate filter.",
        "Unreviewed": "Open sections not marked as reviewed. Reviewed sections remain available but closed.",
        "Collapse all": "Close every document section without removing documents or changing review choices.",
    }
    for column, (label, help_text) in zip(st.columns(len(opening_help)), opening_help.items()):
        column.button(label, key=f"sanitization_open_sections_{label}", help=help_text,
                      type="primary" if focus == label else "secondary", width="stretch",
                      on_click=_set_document_section_focus, args=(label,))

    for document, document_rows in grouped_rows.items():
        reviewed_key = _document_reviewed_key(document)
        reviewed = bool(st.session_state.get(reviewed_key, False))
        focus_match = _document_matches_focus(document, document_rows, focus)
        keep_open = st.session_state.get("sanitization_keep_document_open") == document
        title = _document_review_title(document, document_rows, reviewed)
        # A new keyed container reapplies expansion even after a manual toggle or
        # repeated button click. Inner widget keys stay stable, preserving choices.
        revision = st.session_state.get("sanitization_section_opening_revision", 0)
        with st.container(key=f"sanitization_section_{_safe_key(document)}_{revision}"), st.expander(
            title, expanded=focus_match or (keep_open and not reviewed)
        ):
            if reviewed:
                st.success("This document section is marked as reviewed.")
            _render_document_metrics(document_rows)

            manual_rows = [row for row in document_rows if row.get("_needs_choice")]
            single_choice_rows = [row for row in document_rows if not row.get("_needs_choice")]

            if manual_rows:
                st.markdown("#### Manual choices")
                decisions.extend(_render_manual_choice_cards(manual_rows, document))

            if single_choice_rows:
                st.markdown(
                    "#### Single/no-choice suggestions",
                    help="At most one replacement is offered per row. Select Apply or use Automatic conditions; a suggestion is not approval."
                )
                review_df = pd.DataFrame(single_choice_rows).drop(
                    columns=["Document", "_offset", "_layer", "_status_raw", "_bm25_candidates", "_retrieval_limits"],
                    errors="ignore",
                )
                preferred_columns = [
                    "#",
                    "Apply",
                    "Delete annotation",
                    "Needs manual edit",
                    "Covered text",
                    "Finding context",
                    "Suggested replacement",
                    "Annotator",
                    "Source code",
                    "Policy issue",
                    "Why suggested",
                    "Original FSN",
                    "Status",
                    "_valid_choices",
                    "_choice_hints",
                    "_needs_choice",
                ]
                review_df = review_df[
                    [column for column in preferred_columns if column in review_df.columns]
                    + [column for column in review_df.columns if column not in preferred_columns]
                ]
                with st.form(f"single_choice_form_{_safe_key(document)}"):
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
                        column_config={
                            "Apply": st.column_config.CheckboxColumn(
                                "Apply",
                                help="Toggle whether this replacement should be applied in the sanitization run.",
                            ),
                            "Delete annotation": st.column_config.CheckboxColumn(
                                "Delete",
                                help="Remove this matched annotation from the sanitized project copy instead of replacing its concept ID.",
                            ),
                            "Needs manual edit": st.column_config.CheckboxColumn(
                                "Manual edit",
                                help="Keep the original annotation and add a marker on the manual-review layer in the sanitized project.",
                            ),
                            "Policy issue": st.column_config.TextColumn(
                                "Policy issue",
                                help="Whether the original finding came from the inclusion-list or exclusion-list policy check.",
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
                    submit_col1, submit_col2 = st.columns(2)
                    with submit_col1:
                        st.form_submit_button(
                            "Save single/no-choice selections",
                            help="Save this table's checkbox choices without changing CAS files.",
                            on_click=_keep_document_open,
                            args=(document,),
                            width="stretch",
                        )
                    with submit_col2:
                        st.form_submit_button(
                            "Save and mark document reviewed",
                            help="Save this table's choices and mark review progress. This does not select every replacement.",
                            on_click=_mark_document_reviewed,
                            args=(document,),
                            width="stretch",
                        )
                decisions.extend(
                    _review_rows_to_decisions(edited.to_dict("records"), single_choice_rows, {})
                )

            all_manual_row_numbers = [int(row["#"]) for row in manual_rows]
            st.checkbox(
                "Document reviewed",
                key=reviewed_key,
                help=(
                    "Marks review progress and saves current manual-choice widget state. "
                    "If you have unsaved edits inside a form, use that form's 'Save and mark document reviewed' button."
                ),
                on_change=_save_current_document_review_state,
                args=(document, all_manual_row_numbers),
            )
    return decisions


def _render_document_metrics(document_rows: list[dict[str, Any]]) -> None:
    selected = sum(1 for row in document_rows if _row_apply_selected(row))
    deletes = sum(1 for row in document_rows if _row_delete_selected(row))
    manual_edits = sum(1 for row in document_rows if _row_manual_edit_selected(row))
    manual_total = sum(1 for row in document_rows if row.get("_needs_choice"))
    manual_selected = sum(
        1 for row in document_rows if row.get("_needs_choice") and _row_manual_choice_resolved(row)
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
        f"{selected} replacement(s) selected · {deletes} deletion(s) selected · "
        f"{manual_edits} manual-edit marker(s) selected · {manual_text} · "
        f"{no_replacement} without replacement"
    )


def _condition_source(suggestions) -> str:
    payload = [sanitization_suggestion_to_dict(item) for item in suggestions]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _prepare_automatic_condition_source(suggestions) -> None:
    source = _condition_source(suggestions)
    previous = st.session_state.get("sanitization_conditions_source")
    if previous is not None and previous != source:
        automatic = st.session_state.pop("sanitization_automatic_decisions", {})
        for index, item in automatic.items():
            if not st.session_state.get(f"sanitization_human_reviewed_{_safe_key(item['document'])}"):
                st.session_state[_manual_apply_key(index + 1)] = False
                st.session_state.pop(_choice_key(index + 1), None)
                st.session_state.pop(_previous_choice_key(index + 1), None)
        for document in st.session_state.pop("sanitization_automatic_reviewed_documents", set()):
            if not st.session_state.get(f"sanitization_human_reviewed_{_safe_key(document)}"):
                st.session_state[_document_reviewed_key(document)] = False
        st.session_state.pop("sanitization_conditions_undo", None)
        if automatic:
            st.session_state["sanitization_conditions_message"] = "Suggestions changed; automatic selections were cleared. Apply conditions again if needed."
        _bump_review_state_revision()
    st.session_state["sanitization_conditions_source"] = source


def _sync_condition_result(result, documents) -> None:
    old_reviewed = {doc for doc in documents if st.session_state.get(_document_reviewed_key(doc), False)}
    owned = set(st.session_state.get("sanitization_automatic_reviewed_documents", set()))
    st.session_state["sanitization_automatic_reviewed_documents"] = (
        (owned | (result.reviewed_documents - old_reviewed)) & result.reviewed_documents
    )
    for document in documents:
        st.session_state[_document_reviewed_key(document)] = document in result.reviewed_documents
    for item in result.decisions:
        if "suggestion_index" not in item:
            continue
        number = item["suggestion_index"] + 1
        st.session_state[_choice_key(number)] = item.get("replacement_choice") or NO_REPLACEMENT_LABEL
        st.session_state[_previous_choice_key(number)] = st.session_state[_choice_key(number)]
        st.session_state[_manual_apply_key(number)] = bool(item.get("apply"))
        st.session_state[_manual_delete_key(number)] = bool(item.get("delete_annotation"))
        st.session_state[_manual_edit_key(number)] = bool(item.get("manual_edit"))
    st.session_state["sanitization_automatic_decisions"] = {
        item["suggestion_index"]: item for item in result.decisions
        if "suggestion_index" in item and item.get("automatic_condition")
    }
    st.session_state["sanitization_review_decisions"] = result.decisions
    _bump_review_state_revision()


def _render_automatic_conditions(suggestions, rows, rule_decisions) -> None:
    st.markdown("#### Automatic conditions")
    st.caption(
        "Only inclusion-list source findings qualify. Exclusion-list findings remain manual. "
        "Historical relationships and BM25 gaps are not guarantees of clinical equivalence. No CAS files change here."
    )
    with st.form("sanitization_conditions_form"):
        associations = st.multiselect(
            "Historical association types", options=SUPPORTED_ASSOCIATION_TYPES,
            default=list(DEFAULT_CONDITION_ASSOCIATIONS), key="sanitization_condition_associations",
            format_func=lambda value: f"{value} — {ASSOCIATION_TYPE_DESCRIPTIONS[value]}",
            help="Select when chosen relationships yield one distinct target. Leave empty to disable the historical condition.",
        )
        bm25_enabled = st.checkbox(
            "Enable BM25 automatic selection (heuristic)", value=True, key="sanitization_condition_bm25",
            help="Select a leading BM25 target when both gap thresholds pass. Requires at least three distinct, comparable targets.",
        )
        threshold_columns = st.columns(2)
        with threshold_columns[0]:
            min_dominance = st.number_input(
                "Minimum BM25 gap dominance", min_value=0.0, max_value=1.0, value=2 / 3,
                step=0.05, format="%.3f", key="sanitization_condition_bm25_dominance",
                help="D = first gap / (first gap + largest later gap). The default 2/3 requires a first gap at least twice every later gap.",
            )
        with threshold_columns[1]:
            min_relative_lead = st.number_input(
                "Minimum BM25 relative lead", min_value=0.0, max_value=1.0, value=0.20,
                step=0.05, format="%.3f", key="sanitization_condition_bm25_lead",
                help="M = first gap / top score. A threshold of 0.20 requires a lead of at least 20% of the top score.",
            )
        st.caption(
            "Historical OR enabled BM25 conditions can select a row. BM25 uses all saved distinct targets; "
            "mixed score channels are skipped. Thresholds are unvalidated heuristics. "
            "Existing selections are not cleared by stricter settings; use Undo to reverse the last changed run."
        )
        apply = st.form_submit_button(
            "Apply Conditions",
            help="Stage matching inclusion-list selections, preserving manual choices. Earlier selections are not cleared; CAS files are unchanged.",
        )
    visible_indices = sorted(int(row["#"]) - 1 for row in rows)
    assessments = {visible_indices[index]: item for index, item in bm25_assessments(
        [suggestions[index] for index in visible_indices], min_dominance, min_relative_lead).items()}
    if assessments:
        with st.expander("BM25 score-gap assessment", expanded=False):
            st.caption("Qualifies indicates the score/source condition only, before manual-choice protection. BM25 selection is opt-in.")
            st.dataframe(pd.DataFrame([{
                "#": index + 1, "Document": suggestions[index].finding.document,
                "Source SCTID": suggestions[index].finding.code,
                "Distinct targets": item["candidate_count"], "Scores": item.get("scores", []),
                "D": item.get("dominance"), "M": item.get("relative_lead"),
                "Qualifies if enabled": item["eligible"], "Reason": item["reason"],
            } for index, item in assessments.items()]), hide_index=True, width="stretch")
    undo = st.button(
        "Undo Automatic Conditions", disabled=not st.session_state.get("sanitization_conditions_undo"),
        help="Undo the last Apply Conditions changes, preserving later manual saves. CAS files are unchanged.",
    )
    if st.session_state.get("sanitization_conditions_message"):
        st.info(st.session_state.pop("sanitization_conditions_message"))
    if not apply and not undo:
        return
    current = list(rule_decisions) + _review_rows_to_decisions(rows, rows, {})
    documents = {item["document"] for item in current}
    reviewed = {doc for doc in documents if st.session_state.get(_document_reviewed_key(doc), False)}
    if apply:
        restored = st.session_state.get("sanitization_restored_decisions_by_index", {})
        protected = {index for index, item in restored.items() if not item.get("automatic_condition")}
        choices = {row["#"] - 1: row.get("_valid_choices", ()) for row in rows}
        result = apply_conditions(
            suggestions, current, associations, choices, reviewed, protected,
            bm25_enabled=bm25_enabled, bm25_min_dominance=min_dominance, bm25_min_relative_lead=min_relative_lead,
        )
        if result.undo is not None:
            st.session_state["sanitization_conditions_undo"] = result.undo
        message = (f"Conditions updated {result.changed} row(s); left {result.skipped} unchanged; "
                   f"newly reviewed {len(result.reviewed_documents - reviewed)} document(s).")
    else:
        protected_documents = {doc for doc in documents if st.session_state.get(f"sanitization_human_reviewed_{_safe_key(doc)}")}
        result = undo_automatic_conditions(current, reviewed, st.session_state.pop("sanitization_conditions_undo"), protected_documents)
        message = f"Undid {result.changed} automatic selection(s); preserved {result.skipped} changed/manual selection(s)."
    _sync_condition_result(result, documents)
    st.session_state["sanitization_conditions_message"] = message
    st.rerun()


def _save_manual_choice_form(document: str, row_numbers: list[int]) -> None:
    _keep_document_open(document)
    for row_number in row_numbers:
        choice = st.session_state.get(_choice_key(row_number), NO_REPLACEMENT_LABEL)
        previous_choice_key = _previous_choice_key(row_number)
        previous_choice = st.session_state.get(previous_choice_key)
        if st.session_state.get(_manual_edit_key(row_number)):
            st.session_state[_manual_apply_key(row_number)] = False
            st.session_state[_manual_delete_key(row_number)] = False
        elif st.session_state.get(_manual_delete_key(row_number)):
            st.session_state[_manual_apply_key(row_number)] = False
        elif choice == NO_REPLACEMENT_LABEL:
            st.session_state[_manual_apply_key(row_number)] = False
        elif previous_choice is not None and previous_choice != choice:
            st.session_state[_manual_apply_key(row_number)] = True
        st.session_state[previous_choice_key] = choice


def _save_manual_choice_form_and_mark_reviewed(document: str, row_numbers: list[int]) -> None:
    _save_manual_choice_form(document, row_numbers)
    _mark_document_reviewed(document)


def _candidate_ranks(candidates) -> list[int]:
    """Competition ranks for an ordered list: equal BM25 scores share 1, 1, 3 ranks."""
    ranks = []
    rank, group_score = 0, None
    for position, candidate in enumerate(candidates, start=1):
        score = getattr(candidate, "score", None)
        if score is None or group_score is None or not math.isclose(score, group_score, rel_tol=1e-9, abs_tol=1e-9):
            rank, group_score = position, score
        ranks.append(rank)
    return ranks


def _bm25_tie_count(candidates) -> int:
    if not candidates:
        return 0
    best = max(candidate.score for candidate in candidates)
    return len({candidate.code for candidate in candidates
                if math.isclose(candidate.score, best, rel_tol=1e-9, abs_tol=1e-9)})


def _browser_identity(row) -> str:
    identity = [row.get(key) for key in ("Document", "Annotator", "_layer", "_offset", "Source code", "Covered text", "Policy issue")]
    return "sanitization_bm25_browser_" + hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]


def _stage_browser_selection(table_key, codes, pending_key) -> None:
    rows = st.session_state.get(table_key, {}).get("selection", {}).get("rows", [])
    if len(rows) == 1 and 0 <= rows[0] < len(codes):
        # Map against the rendered table snapshot, never a subsequently filtered row position.
        st.session_state[pending_key] = codes[rows[0]]


def _use_browser_choice(row, pending_key) -> None:
    code = st.session_state.get(pending_key)
    labels = { _code_from_label(label): label for label in row["_valid_choices"] }
    if code not in labels:
        return
    number = int(row["#"])
    label = labels[code]
    if st.session_state.get(_choice_key(number)) != label:
        st.session_state[_manual_apply_key(number)] = False
    st.session_state[_choice_key(number)] = label
    st.session_state[_document_reviewed_key(row["Document"])] = False
    st.session_state["sanitization_keep_document_open"] = row["Document"]


@st.fragment
def _render_bm25_candidate_browser(row) -> None:
    candidates = row["_bm25_candidates"]
    ranks = {candidate.code: rank for candidate, rank in zip(candidates, _candidate_ranks(candidates))}
    base = _browser_identity(row)
    pending_key = base + "_selected_code"
    with st.expander(f"Browse BM25 candidates ({len(candidates)}) — #{row['#']} · {row['Source code']}", expanded=False):
        st.caption(f"Annotation: {row['Covered text']}")
        ties = _bm25_tie_count(candidates)
        qualifier = "At least " if row["_retrieval_limits"] else ""
        st.info(f"{qualifier}{ties} candidates share the top score. No clear lexical leader; extra wording is not distinguished by this query.")
        if row["_retrieval_limits"]:
            st.warning("Retrieval limits reached; additional candidates may exist: " + ", ".join(row["_retrieval_limits"]))
        query = st.text_input("Search SCTID or FSN", key=base + "_query").strip().casefold()
        shown = [candidate for candidate in candidates if not query or query in candidate.code.casefold() or query in candidate.fsn.casefold()]
        st.caption(f"Showing {len(shown)} of {len(candidates)} saved candidates. Scroll to inspect more; equal rank is not clinical equivalence.")
        if shown:
            snapshot = [(candidate.code, candidate.fsn, candidate.score) for candidate in shown]
            table_key = base + "_table_" + hashlib.sha256(json.dumps(snapshot).encode()).hexdigest()[:16]
            st.dataframe(
                pd.DataFrame([{"Rank": ranks[item.code], "SCTID": item.code, "FSN": item.fsn, "BM25 score": item.score} for item in shown]),
                key=table_key, hide_index=True, width="stretch", height=240,
                selection_mode="single-row",
                on_select=partial(_stage_browser_selection, table_key, tuple(item.code for item in shown), pending_key),
                column_config={"Rank": st.column_config.NumberColumn("Rank", format="%d",
                                   help="Equal scores share the same rank (1, 1, 3). Filtering does not renumber candidates."),
                               "SCTID": st.column_config.TextColumn("SCTID"),
                               "FSN": st.column_config.TextColumn("FSN", width="large"),
                               "BM25 score": st.column_config.NumberColumn("BM25 score", format="%.9f",
                                   help="Ties use full-precision scores with numerical tolerance, not rounded display values.")},
            )
        else:
            st.info("No saved candidates match this filter.")
        labels = {_code_from_label(label): label for label in row["_valid_choices"]}
        selected = st.session_state.get(pending_key)
        if selected in labels:
            st.caption("Selected: " + labels[selected])
        if st.button(
            "Use selected candidate", key=base + "_use", disabled=selected not in labels,
            help="Stage this SCTID in the review form below. Save that form to apply it; no CAS files change here.",
            on_click=_use_browser_choice, args=(row, pending_key),
        ):
            st.rerun()


def _render_manual_choice_cards(rows: list[dict[str, Any]], document: str) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    st.caption(
        "These rows need an explicit replacement choice before they can be applied. "
        "Dropdown and checkbox edits are batched; click Save to update the page."
    )
    row_numbers = [int(row["#"]) for row in rows]
    for row in rows:
        if _bm25_tie_count(row.get("_bm25_candidates", ())) > 5:
            _render_bm25_candidate_browser(row)
    with st.form(f"manual_choice_form_{_safe_key(document)}"):
        for row in rows:
            row_number = int(row["#"])
            options = list(row.get("_valid_choices", ()))
            if not options:
                options = [NO_REPLACEMENT_LABEL]
            current_choice = st.session_state.get(_choice_key(row_number), row.get("Suggested replacement"))
            ties = _bm25_tie_count(row.get("_bm25_candidates", ()))
            if ties > 1:
                if ties > 5:
                    # Keep the form compact; the outside-form browser can stage any saved SCTID.
                    options = [current_choice] if current_choice in options else []
                options = [NO_REPLACEMENT_LABEL] + [item for item in options if item != NO_REPLACEMENT_LABEL]
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
                if ties > 1:
                    st.caption(f"{ties} saved candidates tie for first place; no replacement is selected by default.")
                if ties > 5:
                    st.caption("Use the candidate browser above, then save choices in this form.")
                if row.get("_retrieval_limits"):
                    st.warning("Retrieval limits reached; additional BM25 candidates may exist.")
                choice_hints = row.get("_choice_hints", {})
                choice = st.selectbox(
                    "Replacement candidate",
                    options=options,
                    key=_choice_key(row_number),
                    **({"index": options.index(current_choice)} if _choice_key(row_number) not in st.session_state else {}),
                    format_func=lambda option, hints=choice_hints: _format_choice_option(option, hints),
                    help="Choose a selectable target, then save this form. Diagnostic candidates are not offered.",
                )
                if choice_hint := choice_hints.get(choice):
                    st.caption(f"Selected candidate rationale: {choice_hint}")
                manual_edit = st.checkbox(
                    "Needs manual edit",
                    key=_manual_edit_key(row_number),
                    **({"value": bool(row.get("Needs manual edit"))} if _manual_edit_key(row_number) not in st.session_state else {}),
                    help="Keep the original annotation and add a marker on the manual-review layer in the sanitized project.",
                )
                delete_annotation = st.checkbox(
                    "Delete this annotation",
                    key=_manual_delete_key(row_number),
                    **({"value": bool(row.get("Delete annotation")) and not manual_edit}
                       if _manual_delete_key(row_number) not in st.session_state else {}),
                    disabled=manual_edit,
                    help="Remove this annotation from the sanitized project copy instead of replacing its concept ID.",
                )
                apply = st.checkbox(
                    "Apply this replacement",
                    key=_manual_apply_key(row_number),
                    **({"value": bool(row.get("Apply")) and choice != NO_REPLACEMENT_LABEL and not delete_annotation and not manual_edit}
                       if _manual_apply_key(row_number) not in st.session_state else {}),
                    # Form edits do not rerun Python: enabled state must not
                    # depend on an earlier dropdown/action value in this batch.
                    disabled=not row.get("_valid_choices"),
                    help="Select a candidate and check Apply, then save this form. A valid target is required; deletion or manual edit takes precedence. CAS files change only during export/upload.",
                )
            decisions.extend(
                _review_rows_to_decisions(
                    [{**row, "Apply": apply, "Delete annotation": delete_annotation, "Needs manual edit": manual_edit, "Suggested replacement": choice}],
                    [row],
                    {row_number: choice},
                )
            )
        submit_col1, submit_col2 = st.columns(2)
        with submit_col1:
            st.form_submit_button(
                "Save choices",
                help="Save dropdown and checkbox edits for this document.",
                on_click=_save_manual_choice_form,
                args=(document, row_numbers),
                width="stretch",
            )
        with submit_col2:
            st.form_submit_button(
                "Save and mark document reviewed",
                help="Save dropdown and checkbox edits, then mark this document section as reviewed.",
                on_click=_save_manual_choice_form_and_mark_reviewed,
                args=(document, row_numbers),
                width="stretch",
            )
    return decisions


def _set_document_section_focus(focus: str) -> None:
    st.session_state["sanitization_review_focus"] = focus
    st.session_state["sanitization_section_opening_revision"] = st.session_state.get("sanitization_section_opening_revision", 0) + 1
    st.session_state.pop("sanitization_keep_document_open", None)


def _document_matches_focus(
    document: str, document_rows: list[dict[str, Any]], focus: str
) -> bool:
    if focus == "All":
        return True
    if focus == "Collapse all":
        return False
    reviewed = bool(st.session_state.get(_document_reviewed_key(document), False))
    if focus == "Needs choice":
        return not reviewed and any(row.get("_needs_choice") and not _row_manual_choice_resolved(row) for row in document_rows)
    if focus == "No replacement":
        if reviewed:
            return False
        return any(
            row.get("Suggested replacement") == NO_REPLACEMENT_LABEL
            for row in document_rows
        )
    if focus == "Unreviewed":
        return not reviewed
    return False


def _document_review_title(
    document: str, document_rows: list[dict[str, Any]], reviewed: bool
) -> str:
    selected = sum(1 for row in document_rows if _row_apply_selected(row))
    deletes = sum(1 for row in document_rows if _row_delete_selected(row))
    manual_edits = sum(1 for row in document_rows if _row_manual_edit_selected(row))
    manual_total = sum(1 for row in document_rows if row.get("_needs_choice"))
    manual_selected = sum(
        1 for row in document_rows if row.get("_needs_choice") and _row_manual_choice_resolved(row)
    )
    no_replacement = sum(
        1 for row in document_rows if row.get("Suggested replacement") == NO_REPLACEMENT_LABEL
    )
    prefix = "✅" if reviewed else "📝"
    details = [
        f"{len(document_rows)} finding(s)",
        f"{selected} replacement(s) selected",
        f"{deletes} deletion(s) selected",
        f"{manual_edits} manual-edit marker(s) selected",
    ]
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


def _row_apply_selected(row: dict[str, Any]) -> bool:
    if _row_manual_edit_selected(row) or _row_delete_selected(row):
        return False
    if not row.get("_needs_choice"):
        return bool(row.get("Apply"))
    row_number = int(row["#"])
    choice = st.session_state.get(_choice_key(row_number), row.get("Suggested replacement"))
    return (
        bool(st.session_state.get(_manual_apply_key(row_number), row.get("Apply")))
        and choice != NO_REPLACEMENT_LABEL
    )


def _row_delete_selected(row: dict[str, Any]) -> bool:
    if _row_manual_edit_selected(row):
        return False
    row_number = int(row["#"])
    if row.get("_needs_choice"):
        return bool(st.session_state.get(_manual_delete_key(row_number), row.get("Delete annotation")))
    return bool(row.get("Delete annotation"))


def _row_manual_edit_selected(row: dict[str, Any]) -> bool:
    row_number = int(row["#"])
    if row.get("_needs_choice"):
        return bool(st.session_state.get(_manual_edit_key(row_number), row.get("Needs manual edit")))
    return bool(row.get("Needs manual edit"))


def _row_manual_choice_resolved(row: dict[str, Any]) -> bool:
    return _row_manual_edit_selected(row) or _row_apply_selected(row) or _row_delete_selected(row)


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
    single_choice_replacements = sum(
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
    metric_cols[2].metric("Single/no-choice", single_choice_replacements)
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
        "manual_review_layer": st.session_state.get("manual_review_layer", "webanno.custom.ManualReview"),
        "id_prefix": st.session_state.get("snomed_annotation_id_prefix", "http://snomed.info/id/"),
        "id_feature": st.session_state.get("snomed_annotation_id_feature", "id"),
        "document_count": len(documents),
        "reviewed_documents": reviewed_documents,
        "automatic_reviewed_documents": sorted(set(st.session_state.get("sanitization_automatic_reviewed_documents", set())) & set(reviewed_documents)),
    }


def _validate_restored_suggestion_indices(decisions, suggestions):
    if not suggestions:
        return
    for item in decisions:
        if "suggestion_index" not in item:
            continue
        index = int(item["suggestion_index"])
        if not 0 <= index < len(suggestions):
            raise ValueError("Reviewed decisions do not match these suggestions. Load their matching suggestions JSON before restoring review.")
        finding = suggestions[index].finding
        identity = (finding.document, finding.annotator, finding.layer, tuple(finding.offset), finding.code or "")
        if decision_key(item) != identity:
            raise ValueError("Reviewed decisions do not match these suggestions. Load their matching suggestions JSON before restoring review.")


def _restore_decision_state(decisions: list[dict[str, Any]], metadata: dict[str, Any], *, annotators=()) -> None:
    annotators = normalize_annotators(annotators)
    decisions = [item for item in decisions if annotator_in_scope(item.get("annotator", ""), annotators)]
    _validate_restored_suggestion_indices(decisions, st.session_state.get("sanitization_suggestions") or [])
    from snomed_post_processing.sanitization.concept_rules import ConceptRule, validate_rules
    documents = {item["document"] for item in decisions} | {
        item["document"] for item in st.session_state.get("sanitization_review_decisions", [])
    }
    for document in documents:
        st.session_state[_document_reviewed_key(document)] = False
        st.session_state[f"sanitization_human_reviewed_{_safe_key(document)}"] = any(
            item.get("reviewed_by_human") for item in decisions if item["document"] == document
        )
    rules = metadata.get("concept_rules", []) if isinstance(metadata, dict) else []
    if rules:
        st.session_state["concept_rules"] = validate_rules(ConceptRule(**rule) for rule in rules)
    st.session_state["concept_rule_decisions"] = [decision for decision in decisions if decision.get("concept_rule")]
    st.session_state.pop("concept_rule_decisions_source", None)
    st.session_state["concept_rule_needs_validation"] = True
    st.session_state["concept_rule_scope"] = metadata.get("concept_rule_scope", {})
    st.session_state.pop("concept_rule_preview", None)
    st.session_state["concept_rules_editor_revision"] = st.session_state.get("concept_rules_editor_revision", 0) + 1
    st.session_state["concept_rule_review_revision"] = st.session_state.get("concept_rule_review_revision", 0) + 1
    st.session_state.pop("sanitization_conditions_undo", None)
    st.session_state["sanitization_automatic_decisions"] = {
        int(item["suggestion_index"]): item for item in decisions
        if "suggestion_index" in item and item.get("automatic_condition")
    }
    included_documents = {item.get("document") for item in decisions}
    st.session_state["sanitization_automatic_reviewed_documents"] = set(metadata.get("automatic_reviewed_documents", [])) & included_documents
    st.session_state["sanitization_conditions_source"] = _condition_source(st.session_state.get("sanitization_suggestions") or [])
    st.session_state["sanitization_review_decisions"] = decisions
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
        manual_edit = bool(decision.get("manual_edit")) or decision.get("action") == "manual_edit"
        st.session_state[_manual_apply_key(row_number)] = bool(decision.get("apply")) and not manual_edit
        st.session_state[_manual_delete_key(row_number)] = bool(decision.get("delete_annotation")) and not manual_edit
        st.session_state[_manual_edit_key(row_number)] = manual_edit
    if isinstance(metadata, dict) and metadata.get("manual_review_layer"):
        st.session_state["manual_review_layer"] = str(metadata["manual_review_layer"])
    pending_ids = {}
    if isinstance(metadata, dict) and "id_prefix" in metadata:
        pending_ids["snomed_annotation_id_prefix"] = str(metadata.get("id_prefix") or "")
    if isinstance(metadata, dict) and "id_feature" in metadata:
        pending_ids["snomed_annotation_id_feature"] = str(metadata.get("id_feature") or "id") or "id"
    if pending_ids:
        st.session_state["sanitization_pending_id_settings"] = pending_ids
    reviewed_documents = metadata.get("reviewed_documents", []) if isinstance(metadata, dict) else []
    for document in reviewed_documents:
        if document in included_documents:
            st.session_state[_document_reviewed_key(str(document))] = True
    st.session_state["sanitization_decisions_metadata"] = metadata


def _render_suggestion_settings(metadata: dict[str, Any]) -> None:
    settings = metadata.get("settings") if isinstance(metadata, dict) else None
    if not isinstance(settings, dict):
        st.caption("No sanitization-generation settings found in the loaded suggestions JSON.")
        return
    st.json(
        {
            "annotators": metadata.get("annotators", []),
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
    suggestions: list[Any],
    document_texts: dict[str, str] | None = None,
    metadata_contexts: dict[tuple[str, str, str, tuple[int, int]], str] | None = None,
    *, annotators=(),
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    restored_by_index = st.session_state.get("sanitization_restored_decisions_by_index", {})
    for idx, suggestion in enumerate(suggestions):
        if not annotator_in_scope(suggestion.finding.annotator, annotators):
            continue
        row_number = idx + 1
        restored_decision = restored_by_index.get(idx, {})
        replacement_options, replacement_hints = _replacement_options_and_hints(suggestion)
        replacement_label = _replacement_label(suggestion)
        needs_choice = _needs_row_specific_choice(suggestion, replacement_options)
        apply_by_default = False
        selected_label = st.session_state.get(
            _choice_key(row_number),
            restored_decision.get("replacement_choice")
            or (NO_REPLACEMENT_LABEL if hasattr(suggestion, "score")
                and _bm25_tie_count(getattr(suggestion, "candidates", ()) or ()) > 1 else (replacement_options[0] if replacement_options else NO_REPLACEMENT_LABEL)),
        )
        manual_edit_selected = bool(
            st.session_state.get(
                _manual_edit_key(row_number),
                bool(restored_decision.get("manual_edit"))
                or restored_decision.get("action") == "manual_edit",
            )
        )
        delete_selected = bool(
            st.session_state.get(
                _manual_delete_key(row_number),
                bool(restored_decision.get("delete_annotation")),
            )
        ) and not manual_edit_selected
        apply_selected = bool(
            st.session_state.get(
                _manual_apply_key(row_number),
                bool(restored_decision.get("apply", apply_by_default)),
            )
        ) and not delete_selected and not manual_edit_selected
        rows.append(
            {
                "#": row_number,
                "Apply": apply_selected,
                "Delete annotation": delete_selected,
                "Needs manual edit": manual_edit_selected,
                "Document": suggestion.finding.document,
                "Annotator": suggestion.finding.annotator,
                "Source code": suggestion.finding.code or "",
                "Covered text": suggestion.finding.covered_text,
                "Policy issue": _policy_issue_label(suggestion.finding),
                "Finding context": _finding_context_label(
                    suggestion.finding,
                    document_texts or {},
                    metadata_contexts or {},
                ),
                "Suggested replacement": selected_label if needs_choice else replacement_label,
                "Why suggested": replacement_hints.get(
                    selected_label if needs_choice else replacement_label, ""
                ),
                "Original FSN": suggestion.finding.fsn or "",
                "Status": _status_label_for_suggestion(suggestion),
                "_status_raw": _status_value(suggestion.status),
                "_offset": tuple(suggestion.finding.offset),
                "_layer": suggestion.finding.layer,
                "_valid_choices": tuple(replacement_options),
                "_choice_hints": replacement_hints,
                "_needs_choice": needs_choice,
                "_bm25_candidates": tuple(getattr(suggestion, "candidates", ())) if hasattr(suggestion, "score") else (),
                "_retrieval_limits": tuple(getattr(suggestion, "retrieval_limits", ())),
            }
        )
    return rows


def _review_rows_to_decisions(
    edited_rows: list[dict[str, Any]],
    original_rows: list[dict[str, Any]],
    ambiguous_choices: dict[int, str],
) -> list[dict[str, Any]]:
    original_by_number = {row["#"]: row for row in original_rows}
    previous = dict(st.session_state.get("sanitization_restored_decisions_by_index", {}))
    previous.update({item["suggestion_index"]: item for item in st.session_state.get("sanitization_review_decisions", []) if "suggestion_index" in item})
    decisions = []
    for edited in edited_rows:
        row_number = int(edited["#"])
        original = original_by_number.get(row_number, {})
        choice = ambiguous_choices.get(row_number) or edited.get("Suggested replacement") or NO_REPLACEMENT_LABEL
        valid_choices = tuple(original.get("_valid_choices", ()))
        valid_choice = choice in valid_choices
        manual_edit = bool(edited.get("Needs manual edit"))
        delete_annotation = bool(edited.get("Delete annotation")) and not manual_edit
        apply_replacement = bool(edited.get("Apply")) and not delete_annotation and not manual_edit
        action = "manual_edit" if manual_edit else ("delete" if delete_annotation else ("replace" if apply_replacement and valid_choice else "none"))
        decision = {
            "suggestion_index": row_number - 1,
            "reviewed_by_human": bool(st.session_state.get(f"sanitization_human_reviewed_{_safe_key(str(original.get('Document', '')))}", False)),
            "action": action,
            "apply": apply_replacement,
            "delete_annotation": delete_annotation,
            "manual_edit": manual_edit,
            "annotator": edited.get("Annotator", ""),
            "document": original.get("Document", ""),
            "source_code": edited.get("Source code", ""),
            "covered_text": edited.get("Covered text", ""),
            "offset": list(original.get("_offset", ())),
            "layer": original.get("_layer"),
            "replacement_choice": choice,
            "replacement_code": _code_from_label(choice) if valid_choice else None,
            "replacement_fsn": _fsn_from_label(choice) if valid_choice else None,
            "suggestion_status": original.get("Status", ""),
            "review_note": original.get("Why suggested", ""),
            "valid_choice": valid_choice,
            "resolved": (apply_replacement and valid_choice) or delete_annotation,
        }
        prior = previous.get(row_number - 1, {})
        if decision_key(prior) == decision_key(decision) and prior.get("reviewed_by_human"):
            decision["reviewed_by_human"] = True
        automatic = st.session_state.get("sanitization_automatic_decisions", {}).get(row_number - 1)
        if automatic and not decision["reviewed_by_human"] and decision_selection(decision) == decision_selection(automatic):
            decision["automatic_condition"] = automatic["automatic_condition"]
        if not original.get("_needs_choice"):
            # Persist saved grid choices before condition actions recreate its widget.
            st.session_state[_manual_apply_key(row_number)] = apply_replacement
            st.session_state[_manual_delete_key(row_number)] = delete_annotation
            st.session_state[_manual_edit_key(row_number)] = manual_edit
        decisions.append(decision)
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

    # ``context_candidates`` are diagnostic/provenance context only, e.g.
    # ancestors rejected because they are outside the configured distance limit.
    # They must not be selectable replacement choices.
    candidates = getattr(suggestion, "candidates", ()) or ()
    for candidate, rank in zip(candidates, _candidate_ranks(candidates)):
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
        return "Reason: on exclusion list"
    if list_type == "whitelist":
        return "Reason: not on inclusion list"
    return f"Reason: {reason}" if reason else "Reason: policy finding"


def _finding_context_label(
    finding: Any,
    document_texts: dict[str, str],
    metadata_contexts: dict[tuple[str, str, str, tuple[int, int]], str] | None = None,
) -> str:
    document_text = _lookup_document_text(document_texts, str(getattr(finding, "document", "")))
    offset = getattr(finding, "offset", None)
    if document_text and offset and len(offset) == 2:
        return _offset_context(document_text, int(offset[0]), int(offset[1]))
    metadata_context = (metadata_contexts or {}).get(_finding_context_key(finding))
    if metadata_context:
        return metadata_context
    covered_text = _compact_text(getattr(finding, "covered_text", ""), max_length=80)
    if covered_text:
        return f"No full document context loaded."
    return "No document text context available."


def _finding_context_key(finding: Any) -> tuple[str, str, str, tuple[int, int]]:
    offset = tuple(int(value) for value in (getattr(finding, "offset", None) or ()))
    if len(offset) != 2:
        offset = (-1, -1)
    return (
        str(getattr(finding, "document", "") or ""),
        str(getattr(finding, "annotator", "") or ""),
        str(getattr(finding, "code", "") or ""),
        offset,
    )


def _metadata_finding_context_lookup(metadata: dict[str, Any]) -> dict[tuple[str, str, str, tuple[int, int]], str]:
    lookup: dict[tuple[str, str, str, tuple[int, int]], str] = {}
    for item in metadata.get("finding_contexts", ()) or ():
        try:
            offset = tuple(int(value) for value in item.get("offset", ()))
            if len(offset) != 2:
                continue
            key = (
                str(item.get("document", "") or ""),
                str(item.get("annotator", "") or ""),
                str(item.get("code", "") or ""),
                offset,
            )
            context = str(item.get("context", "") or "")
        except Exception:
            continue
        if context:
            lookup[key] = context
    return lookup


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
        if getattr(candidate, "source", "snomed_fsn") == "snogit":
            matched_term = getattr(candidate, "matched_term", None)
            parts.append("SNOGIT" + (f": {_compact_text(matched_term, max_length=60)}" if matched_term else ""))
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
    } or len(replacement_options) > 1


def _needs_top_k_choice(suggestion: Any) -> bool:
    return _status_value(suggestion.status) in {
        SanitizationStatus.AMBIGUOUS_REPLACEMENT.value,
    }


def _choice_key(row_number: int) -> str:
    return f"sanitization_replacement_choice_{row_number}"


def _manual_apply_key(row_number: int) -> str:
    return f"sanitization_manual_apply_{row_number}"


def _manual_delete_key(row_number: int) -> str:
    return f"sanitization_manual_delete_{row_number}"


def _manual_edit_key(row_number: int) -> str:
    return f"sanitization_manual_edit_{row_number}"


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
    return label.split(" —", 1)[0]


def _fsn_from_label(label: str) -> str | None:
    if not label or label == NO_REPLACEMENT_LABEL or " — " not in label:
        return None
    return label.split(" — ", 1)[1] or None


def _status_label_for_suggestion(suggestion: Any) -> str:
    label = _status_label(getattr(suggestion, "status", ""))
    if (
        _status_value(getattr(suggestion, "status", ""))
        == SanitizationStatus.SEMANTIC_BM25_REPLACEMENT.value
        and _bm25_suggestion_uses_snogit(suggestion)
    ):
        return f"{label} (SNOGIT)"
    return label


def _bm25_suggestion_uses_snogit(suggestion: Any) -> bool:
    replacement_code = str(getattr(suggestion, "replacement_code", "") or "")
    for candidate in getattr(suggestion, "candidates", ()) or ():
        if getattr(candidate, "source", "snomed_fsn") != "snogit":
            continue
        candidate_code = str(getattr(candidate, "code", "") or "")
        if not replacement_code or candidate_code == replacement_code:
            return True
    return False


def _status_label(status: Any) -> str:
    labels = {
        SanitizationStatus.HISTORICAL_ASSOCIATION_REPLACEMENT.value: "Historical association",
        SanitizationStatus.SEMANTIC_BM25_REPLACEMENT.value: "BM25 suggestion",
        SanitizationStatus.NEAREST_TARGET_ANCESTOR.value: "Nearest active ancestor",
        SanitizationStatus.NEAREST_HISTORICAL_ANCESTOR.value: "Nearest historical ancestor",
        SanitizationStatus.AMBIGUOUS_REPLACEMENT.value: "Ambiguous replacement",
        SanitizationStatus.AMBIGUOUS_ANCESTOR.value: "Ambiguous ancestor",
        SanitizationStatus.NO_POLICY_ACCEPTABLE_CANDIDATE.value: "No acceptable candidate",
        SanitizationStatus.NO_HISTORICAL_ASSOCIATION.value: "No historical association",
        SanitizationStatus.BLACKLISTED_NO_AUTO_SANITIZATION.value: "Excluded/no automatic sanitization",
    }
    value = _status_value(status)
    return labels.get(value, value.replace("_", " ").title())


def _status_value(status: Any) -> str:
    if isinstance(status, SanitizationStatus):
        return status.value
    return str(status)
