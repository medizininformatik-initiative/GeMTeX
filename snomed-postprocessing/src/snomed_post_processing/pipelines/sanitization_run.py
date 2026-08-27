"""Sanitization-run pipeline for applying reviewed suggestions to UIMA/CAS files."""

from __future__ import annotations

import dataclasses
import io
import pathlib
import zipfile
from typing import Any, Optional

from ..uima_processing.io import (
    _annotator_name_from_cas_path,
    _load_cas_from_zip_member,
    _load_typesystem_from_zip,
    _prefer_non_ser_files,
    _read_project,
    _yield_flat_archive_files,
    _yield_matching_files,
)


@dataclasses.dataclass(frozen=True)
class SanitizationRunResult:
    output_project: pathlib.Path
    decision_count: int
    applied_decision_count: int
    changed_annotation_count: int
    changed_member_count: int
    unmatched_decisions: tuple[dict[str, Any], ...]
    skipped_decisions: tuple[dict[str, Any], ...]


class SanitizationRunError(RuntimeError):
    """Raised when the sanitization run cannot be completed."""


def run_sanitization(
    input_project: pathlib.Path,
    decisions: list[dict[str, Any]],
    output_project: pathlib.Path,
    *,
    annotator_filter: Optional[set[str]] = None,
    id_prefix: str = "http://snomed.info/id/",
    manual_review_layer: str = "webanno.custom.ManualReview",
    sanitized_project_suffix: str = "sanitized",
) -> SanitizationRunResult:
    """Apply reviewed sanitization decisions to copied INCEpTION/UIMA project ZIP.

    The original project is never modified. Only JSON CAS and XMI members are
    rewritten; unsupported ``.ser`` files are copied unchanged. Decisions are
    matched conservatively by document, annotator, layer, span, and source code.
    """
    input_project = pathlib.Path(input_project)
    output_project = pathlib.Path(output_project)
    if not input_project.exists() or not input_project.is_file():
        raise FileNotFoundError(f"Input project does not exist: {input_project}")
    if input_project.resolve() == output_project.resolve():
        raise SanitizationRunError("Output project must be different from input project.")

    manual_review_layer = str(manual_review_layer or "").strip() or "webanno.custom.ManualReview"
    sanitized_project_suffix = str(sanitized_project_suffix or "").strip() or "sanitized"
    applicable_decisions = [decision for decision in decisions if _is_applicable_decision(decision)]
    skipped_decisions = [decision for decision in decisions if not _is_applicable_decision(decision)]
    decisions_by_key = _group_decisions_by_document_annotator(applicable_decisions)
    matched_decision_indices: set[int] = set()
    changed_member_count = 0
    changed_annotation_count = 0

    output_project.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(input_project, "r") as in_zip:
        project_documents = _read_project(in_zip, input_project.name)
        typesystem = _load_typesystem_from_zip(in_zip)
        typesystem_by_parent = {}
        matching_document_files = list(
            _yield_matching_files(
                project_documents,
                in_zip,
                input_project.name,
                allowed_extensions=[".json", ".xmi", ".ser"],
            )
        )
        fallback_flat_layout = project_documents is None
        if matching_document_files and all(
            cas_path.lower().endswith(".ser")
            for _, matching_files in matching_document_files
            for cas_path in matching_files
        ):
            flat_document_files = _prefer_non_ser_files(
                list(_yield_flat_archive_files(in_zip, allowed_extensions=[".json", ".xmi", ".ser"]))
            )
            if flat_document_files:
                matching_document_files = flat_document_files
                fallback_flat_layout = True
        elif not matching_document_files:
            matching_document_files = _prefer_non_ser_files(
                list(_yield_flat_archive_files(in_zip, allowed_extensions=[".json", ".xmi", ".ser"]))
            )
            fallback_flat_layout = True

        member_to_doc_annotator: dict[str, tuple[str, str]] = {}
        for document, matching_files in matching_document_files:
            seen_doc_paths = set()
            matching_files = [
                cas_path
                for cas_path in matching_files
                if not (cas_path in seen_doc_paths or seen_doc_paths.add(cas_path))
            ]
            non_ser_files = [cas_path for cas_path in matching_files if not cas_path.lower().endswith(".ser")]
            if non_ser_files:
                matching_files = non_ser_files
            for cas_path in matching_files:
                annotator = _annotator_name_from_cas_path(cas_path, fallback_flat_layout=fallback_flat_layout)
                if annotator_filter is not None and annotator.lower() not in annotator_filter:
                    continue
                member_to_doc_annotator[cas_path] = (document, annotator)

        with zipfile.ZipFile(output_project, "w", compression=zipfile.ZIP_DEFLATED) as out_zip:
            for info in in_zip.infolist():
                if info.filename.lower().endswith(".ser"):
                    continue
                data = in_zip.read(info.filename)
                replacement_data = data
                has_manual_edit_decisions = any(_is_manual_edit_decision(decision) for decision in applicable_decisions)
                if info.filename == "exportedproject.json":
                    replacement_data = _sanitized_project_json(
                        data,
                        sanitized_project_suffix=sanitized_project_suffix,
                        manual_review_layer=manual_review_layer,
                        include_manual_review_layer=has_manual_edit_decisions,
                    )
                elif has_manual_edit_decisions and pathlib.PurePosixPath(info.filename).name == "TypeSystem.xml":
                    replacement_data = _typesystem_xml_with_manual_review_layer(data, manual_review_layer)
                if not info.is_dir() and info.filename in member_to_doc_annotator:
                    document, annotator = member_to_doc_annotator[info.filename]
                    key = (document, annotator)
                    member_decisions = decisions_by_key.get(key, [])
                    if member_decisions and not info.filename.lower().endswith(".ser"):
                        parent = str(pathlib.PurePosixPath(info.filename).parent)
                        cas_typesystem = typesystem_by_parent.get(parent)
                        if cas_typesystem is None:
                            cas_typesystem = _load_typesystem_from_zip(in_zip, info.filename) or typesystem
                            typesystem_by_parent[parent] = cas_typesystem
                        cas = _load_cas_from_zip_member(in_zip, info.filename, typesystem=cas_typesystem)
                        changed = _apply_decisions_to_cas(
                            cas,
                            member_decisions,
                            matched_decision_indices,
                            id_prefix=id_prefix,
                            manual_review_layer=manual_review_layer,
                        )
                        if changed:
                            replacement_data = _serialize_cas_for_member(cas, info.filename)
                            changed_member_count += 1
                            changed_annotation_count += changed
                out_zip.writestr(_copy_zip_info(info), replacement_data)

    unmatched_decisions = tuple(
        decision
        for idx, decision in enumerate(applicable_decisions)
        if idx not in matched_decision_indices
    )
    return SanitizationRunResult(
        output_project=output_project,
        decision_count=len(decisions),
        applied_decision_count=len(applicable_decisions),
        changed_annotation_count=changed_annotation_count,
        changed_member_count=changed_member_count,
        unmatched_decisions=unmatched_decisions,
        skipped_decisions=tuple(skipped_decisions),
    )


def _is_applicable_decision(decision: dict[str, Any]) -> bool:
    if _is_manual_edit_decision(decision):
        return True
    if bool(decision.get("delete_annotation")) or decision.get("action") == "delete":
        return True
    return bool(decision.get("apply")) and bool(decision.get("valid_choice")) and bool(decision.get("replacement_code"))


def _is_manual_edit_decision(decision: dict[str, Any]) -> bool:
    return bool(decision.get("manual_edit")) or decision.get("action") == "manual_edit"


def _typesystem_xml_with_manual_review_layer(data: bytes, manual_review_layer: str) -> bytes:
    import cassis

    try:
        typesystem = cassis.load_typesystem(io.BytesIO(data))
        _ensure_manual_review_type_on_typesystem(typesystem, manual_review_layer)
        return typesystem.to_xml().encode("utf-8")
    except Exception:
        return data


def _sanitized_project_json(
    data: bytes,
    *,
    sanitized_project_suffix: str,
    manual_review_layer: str,
    include_manual_review_layer: bool,
) -> bytes:
    import json

    try:
        project = json.loads(data.decode("utf-8"))
    except Exception:
        return data
    _append_sanitized_project_labels(project, sanitized_project_suffix)
    if include_manual_review_layer:
        _ensure_manual_review_layer_in_project(project, manual_review_layer)
    return json.dumps(project, ensure_ascii=False, indent=2).encode("utf-8")


def _append_sanitized_project_labels(project: dict[str, Any], suffix: str) -> None:
    project["name"] = _append_sanitized_name(project.get("name"), suffix)
    project["slug"] = _append_sanitized_slug(project.get("slug"), suffix)
    project["description"] = _append_sanitized_description(project.get("description"), suffix)


def _append_sanitized_name(value: Any, suffix: str) -> str:
    text = str(value or "").strip()
    if not text:
        text = "Project"
    if suffix.lower() in text.lower():
        return text
    return f"{text} ({suffix})"


def _append_sanitized_slug(value: Any, suffix: str) -> str:
    text = str(value or "").strip() or "project"
    suffix_slug = "".join(char.lower() if char.isalnum() else "-" for char in suffix).strip("-") or "sanitized"
    if text.lower().endswith(f"-{suffix_slug}") or text.lower() == suffix_slug:
        return text
    return f"{text}-{suffix_slug}"


def _append_sanitized_description(value: Any, suffix: str) -> str:
    text = str(value or "").strip()
    note = f"Sanitized export ({suffix})."
    if "sanitized export" in text.lower():
        return text
    if text:
        return f"{text}\n\n{note}"
    return note


def _ensure_manual_review_layer_in_project(project: dict[str, Any], manual_review_layer: str) -> None:
    layers = project.setdefault("layers", [])
    if any(layer.get("name") == manual_review_layer for layer in layers if isinstance(layer, dict)):
        return
    ui_name = manual_review_layer.rsplit(".", 1)[-1] or "ManualReview"
    feature_template = {
        "curatable": True,
        "description": None,
        "enabled": True,
        "hideUnconstraintFeature": False,
        "include_in_hover": True,
        "link_mode": "NONE",
        "link_type_name": None,
        "link_type_role_feature_name": None,
        "link_type_target_feature_name": None,
        "multi_value_mode": "NONE",
        "rank": 0,
        "remember": False,
        "required": False,
        "tag_set": None,
        "traits": '{"multipleRows":false,"dynamicSize":false,"collapsedRows":1,"expandedRows":1,"editorType":"AUTO","keyBindings":[]}',
        "type": "uima.cas.String",
        "visible": True,
    }
    features = []
    for name, ui_name_feature in (
        ("source_code", "Source code"),
        ("covered_text", "Covered text"),
        ("suggestion_status", "Suggestion status"),
        ("suggested_replacement", "Suggested replacement"),
        ("review_note", "Review note"),
    ):
        feature = dict(feature_template)
        feature["name"] = name
        feature["uiName"] = ui_name_feature
        features.append(feature)
    layers.append(
        {
            "allow_stacking": True,
            "anchoring_mode": "CHARACTERS",
            "attach_feature": None,
            "attach_type": None,
            "built_in": False,
            "cross_sentence": True,
            "description": "Markers for SNOMED annotations requiring manual editing after sanitization.",
            "enabled": True,
            "features": features,
            "linked_list_behavior": False,
            "lock_to_token_offset": False,
            "multiple_tokens": True,
            "name": manual_review_layer,
            "on_click_javascript_action": None,
            "overlap_mode": "ANY_OVERLAP",
            "readonly": False,
            "show_hover": True,
            "traits": '{"coloringRules":{"rules":[]}}',
            "type": "span",
            "uiName": ui_name,
            "validation_mode": "ALWAYS",
        }
    )


def _group_decisions_by_document_annotator(decisions: list[dict[str, Any]]) -> dict[tuple[str, str], list[tuple[int, dict[str, Any]]]]:
    grouped: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]] = {}
    for idx, decision in enumerate(decisions):
        grouped.setdefault((str(decision.get("document", "")), str(decision.get("annotator", ""))), []).append((idx, decision))
    return grouped


def _apply_decisions_to_cas(
    cas,
    decisions: list[tuple[int, dict[str, Any]]],
    matched_indices: set[int],
    *,
    id_prefix: str,
    manual_review_layer: str,
) -> int:
    changed = 0
    for decision_idx, decision in decisions:
        for annotation in _matching_annotations(cas, decision, id_prefix=id_prefix):
            if bool(decision.get("manual_edit")) or decision.get("action") == "manual_edit":
                _add_manual_review_marker(cas, annotation, decision, manual_review_layer=manual_review_layer)
            elif bool(decision.get("delete_annotation")) or decision.get("action") == "delete":
                _remove_annotation(cas, annotation)
            else:
                current_id = annotation.get("id")
                annotation.set("id", _replacement_id(current_id, str(decision["replacement_code"]), id_prefix=id_prefix))
            matched_indices.add(decision_idx)
            changed += 1
            break
    return changed


def _add_manual_review_marker(cas, source_annotation, decision: dict[str, Any], *, manual_review_layer: str) -> None:
    marker_type = _ensure_manual_review_type(cas, manual_review_layer)
    replacement = decision.get("replacement_code") or ""
    replacement_fsn = decision.get("replacement_fsn") or ""
    if replacement and replacement_fsn:
        suggested_replacement = f"{replacement} — {replacement_fsn}"
    else:
        suggested_replacement = str(replacement or replacement_fsn or "")
    marker = marker_type(
        begin=int(source_annotation.begin),
        end=int(source_annotation.end),
        source_code=str(decision.get("source_code", "") or ""),
        covered_text=str(decision.get("covered_text", "") or ""),
        suggestion_status=str(decision.get("suggestion_status", "") or ""),
        suggested_replacement=suggested_replacement,
        review_note=str(decision.get("review_note", "") or ""),
    )
    cas.add(marker)


def _ensure_manual_review_type(cas, manual_review_layer: str):
    typesystem = getattr(cas, "typesystem", None)
    if typesystem is None:
        raise SanitizationRunError("CAS implementation does not expose a type system.")
    return _ensure_manual_review_type_on_typesystem(typesystem, manual_review_layer)


def _ensure_manual_review_type_on_typesystem(typesystem, manual_review_layer: str):
    if not typesystem.contains_type(manual_review_layer):
        marker_type = typesystem.create_type(manual_review_layer, supertypeName="uima.tcas.Annotation")
    else:
        marker_type = typesystem.get_type(manual_review_layer)
    for feature_name in (
        "source_code",
        "covered_text",
        "suggestion_status",
        "suggested_replacement",
        "review_note",
    ):
        _ensure_string_feature(typesystem, marker_type, feature_name)
    return marker_type


def _ensure_string_feature(typesystem, type_, feature_name: str) -> None:
    if any(getattr(feature, "name", "") == feature_name for feature in getattr(type_, "features", ())):
        return
    try:
        typesystem.create_feature(type_, feature_name, "uima.cas.String")
    except Exception:
        # If another CAS implementation reports existing features differently,
        # tolerate duplicate-feature errors and let annotation creation validate.
        pass


def _remove_annotation(cas, annotation) -> None:
    if hasattr(cas, "remove"):
        cas.remove(annotation)
        return
    if hasattr(cas, "_current_view") and hasattr(cas._current_view, "remove_annotation"):
        cas._current_view.remove_annotation(annotation)
        return
    raise SanitizationRunError("CAS implementation does not support annotation removal.")


def _matching_annotations(cas, decision: dict[str, Any], *, id_prefix: str):
    layer = decision.get("layer")
    if not layer:
        return
    try:
        annotations = cas.select(str(layer))
    except Exception:
        return
    offset = tuple(decision.get("offset") or ())
    source_code = str(decision.get("source_code", ""))
    covered_text = str(decision.get("covered_text", ""))
    for annotation in annotations:
        if len(offset) == 2 and (int(annotation.begin), int(annotation.end)) != (int(offset[0]), int(offset[1])):
            continue
        current_code = _normalize_snomed_id(annotation.get("id"), id_prefix=id_prefix)
        if source_code and current_code != source_code.lower():
            continue
        if covered_text:
            try:
                if annotation.get_covered_text() != covered_text:
                    continue
            except Exception:
                pass
        yield annotation


def _normalize_snomed_id(value: Any, *, id_prefix: str) -> str:
    if value is None:
        return ""
    prefix = id_prefix if id_prefix.endswith("/") else id_prefix + "/"
    return str(value).strip().lower().removeprefix(prefix.lower()).strip()


def _replacement_id(current_id: Any, replacement_code: str, *, id_prefix: str) -> str:
    if current_id is not None and str(current_id).strip().lower().startswith(id_prefix.lower()):
        prefix = id_prefix if id_prefix.endswith("/") else id_prefix + "/"
        return prefix + replacement_code
    return replacement_code


def _serialize_cas_for_member(cas, member_name: str) -> bytes:
    if member_name.lower().endswith(".json"):
        return cas.to_json().encode("utf-8")
    if member_name.lower().endswith(".xmi"):
        return cas.to_xmi().encode("utf-8")
    raise SanitizationRunError(f"Unsupported writable CAS format: {member_name}")


def _copy_zip_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    copied = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    copied.comment = info.comment
    copied.extra = info.extra
    copied.internal_attr = info.internal_attr
    copied.external_attr = info.external_attr
    copied.create_system = info.create_system
    return copied
