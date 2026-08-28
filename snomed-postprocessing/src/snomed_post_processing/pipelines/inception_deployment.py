"""Deploy sanitized INCEpTION shell projects and flattened CAS artifacts."""

from __future__ import annotations

import dataclasses
import datetime
import inspect
import io
import json
import os
import pathlib
from typing import Any, Optional

import cassis


SUPPORTED_UPLOAD_FORMATS = {"jsoncas", "xmi"}
DEFAULT_ARTIFACT_REPORT_NAME = "inception-upload-artifacts-report.json"
DEFAULT_DEPLOYMENT_REPORT_NAME = "inception-sanitized-deployment-report.json"


@dataclasses.dataclass(frozen=True)
class InceptionCasCompatibilityReport:
    sentence_count: int
    sentence_overlap_count: int
    sentence_whitespace_count: int
    outside_sentence_annotation_count: int
    cas_metadata_count: int
    document_metadata_count: int

    @property
    def issue_count(self) -> int:
        return (
            self.sentence_overlap_count
            + self.sentence_whitespace_count
            + self.outside_sentence_annotation_count
            + (0 if self.cas_metadata_count else 1)
            + self.document_metadata_count
        )


@dataclasses.dataclass(frozen=True)
class InceptionDeploymentPlanItem:
    source_member: str
    source_document: str
    source_annotator: str
    remote_document_name: str
    artifact_path: pathlib.Path
    cas_format: str
    decision_count: int
    changed_annotation_count: int


@dataclasses.dataclass(frozen=True)
class InceptionDeploymentResult:
    dry_run: bool
    applied: bool
    shell_project: pathlib.Path
    upload_artifacts_dir: pathlib.Path
    artifact_report_path: pathlib.Path
    deployment_report_path: pathlib.Path
    planned_upload_count: int
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    imported_project_id: Optional[int] = None
    imported_project_name: Optional[str] = None


class InceptionDeploymentError(RuntimeError):
    """Raised when sanitized INCEpTION deployment cannot proceed."""


def deploy_inception_sanitized_project(
    *,
    shell_project: pathlib.Path,
    upload_artifacts_dir: pathlib.Path,
    deployment_report: Optional[pathlib.Path] = None,
    inception_url: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    password_env: Optional[str] = None,
    annotation_user: Optional[str] = None,
    apply: bool = False,
    check_connection: bool = False,
    verify_tls: bool = True,
) -> InceptionDeploymentResult:
    """Validate or apply sanitized deployment into INCEpTION.

    By default this is a dry-run: it validates the shell ZIP and flattened
    artifact report/files, writes a deployment plan report, and performs no
    network writes. With ``apply=True`` it imports the shell project and uploads
    each flattened artifact as an annotation on a newly created plain-text source
    document.
    """

    shell_project = pathlib.Path(shell_project)
    upload_artifacts_dir = pathlib.Path(upload_artifacts_dir)
    artifact_report_path = upload_artifacts_dir / DEFAULT_ARTIFACT_REPORT_NAME
    deployment_report_path = pathlib.Path(
        deployment_report or upload_artifacts_dir / DEFAULT_DEPLOYMENT_REPORT_NAME
    )
    warnings: list[str] = []
    errors: list[str] = []

    plan = _validate_deployment_inputs(
        shell_project=shell_project,
        upload_artifacts_dir=upload_artifacts_dir,
        artifact_report_path=artifact_report_path,
        warnings=warnings,
        errors=errors,
    )

    imported_project_id: Optional[int] = None
    imported_project_name: Optional[str] = None
    upload_results: list[dict[str, Any]] = []
    applied = False

    if errors:
        report = _deployment_report_payload(
            dry_run=not apply,
            applied=False,
            shell_project=shell_project,
            upload_artifacts_dir=upload_artifacts_dir,
            artifact_report_path=artifact_report_path,
            plan=plan,
            warnings=warnings,
            errors=errors,
            imported_project_id=None,
            imported_project_name=None,
            upload_results=upload_results,
        )
        _write_report(deployment_report_path, report)
        return InceptionDeploymentResult(
            dry_run=not apply,
            applied=False,
            shell_project=shell_project,
            upload_artifacts_dir=upload_artifacts_dir,
            artifact_report_path=artifact_report_path,
            deployment_report_path=deployment_report_path,
            planned_upload_count=len(plan),
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    if check_connection or apply:
        if not inception_url:
            errors.append("INCEpTION URL is required for --check-connection or --apply.")
        password = _resolve_password(password=password, password_env=password_env)
        if not username:
            errors.append("INCEpTION username is required for --check-connection or --apply.")
        if not password:
            errors.append("INCEpTION password is required for --check-connection or --apply.")
        if not annotation_user:
            annotation_user = username

    if errors:
        report = _deployment_report_payload(
            dry_run=not apply,
            applied=False,
            shell_project=shell_project,
            upload_artifacts_dir=upload_artifacts_dir,
            artifact_report_path=artifact_report_path,
            plan=plan,
            warnings=warnings,
            errors=errors,
            imported_project_id=None,
            imported_project_name=None,
            upload_results=upload_results,
        )
        _write_report(deployment_report_path, report)
        return InceptionDeploymentResult(
            dry_run=not apply,
            applied=False,
            shell_project=shell_project,
            upload_artifacts_dir=upload_artifacts_dir,
            artifact_report_path=artifact_report_path,
            deployment_report_path=deployment_report_path,
            planned_upload_count=len(plan),
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    if check_connection and not apply:
        try:
            client = _pycaprio_client(inception_url, username, password, verify_tls=verify_tls)
            projects = client.api.projects()
            warnings.append(f"Connection check succeeded; accessible projects: {len(projects)}.")
        except Exception as exc:  # pragma: no cover - depends on remote INCEpTION
            errors.append(f"Connection check failed: {exc}")

    if apply and not errors:
        try:
            client = _pycaprio_client(inception_url, username, password, verify_tls=verify_tls)
            with shell_project.open("rb") as shell_file:
                project = client.api.import_project(shell_file)
            imported_project_id = getattr(project, "project_id", None)
            imported_project_name = getattr(project, "project_name", None)
            for item in plan:
                document_name = _document_name_without_cas_suffix(item.remote_document_name)
                artifact_bytes = item.artifact_path.read_bytes()
                repaired_cas_bytes = (
                    prepare_remote_upload_cas_bytes(artifact_bytes, item.cas_format)
                    if item.cas_format == "jsoncas"
                    else artifact_bytes
                )
                with io.BytesIO(repaired_cas_bytes) as source_content:
                    source_content.name = item.remote_document_name
                    document_kwargs: dict[str, Any] = {
                        "project": project,
                        "document_name": document_name,
                        "content": source_content,
                        "document_format": item.cas_format,
                    }
                    if "filename" in inspect.signature(client.api.create_document).parameters:
                        document_kwargs["filename"] = item.remote_document_name
                    document = client.api.create_document(**document_kwargs)
                with io.BytesIO(repaired_cas_bytes) as annotation_content:
                    annotation_content.name = item.remote_document_name
                    annotation = client.api.create_annotation(
                        project,
                        document,
                        annotation_user,
                        annotation_content,
                        annotation_format=item.cas_format,
                    )
                upload_results.append(
                    {
                        "remote_document_name": item.remote_document_name,
                        "document_name": document_name,
                        "document_id": getattr(document, "document_id", None),
                        "annotation_user": annotation_user,
                        "annotation_state": getattr(annotation, "annotation_state", None),
                        "status": "uploaded",
                    }
                )
            applied = True
        except Exception as exc:  # pragma: no cover - depends on remote INCEpTION
            errors.append(f"Apply failed: {exc}")

    report = _deployment_report_payload(
        dry_run=not apply,
        applied=applied,
        shell_project=shell_project,
        upload_artifacts_dir=upload_artifacts_dir,
        artifact_report_path=artifact_report_path,
        plan=plan,
        warnings=warnings,
        errors=errors,
        imported_project_id=imported_project_id,
        imported_project_name=imported_project_name,
        upload_results=upload_results,
    )
    _write_report(deployment_report_path, report)
    return InceptionDeploymentResult(
        dry_run=not apply,
        applied=applied,
        shell_project=shell_project,
        upload_artifacts_dir=upload_artifacts_dir,
        artifact_report_path=artifact_report_path,
        deployment_report_path=deployment_report_path,
        planned_upload_count=len(plan),
        warnings=tuple(warnings),
        errors=tuple(errors),
        imported_project_id=imported_project_id,
        imported_project_name=imported_project_name,
    )


def _validate_deployment_inputs(
    *,
    shell_project: pathlib.Path,
    upload_artifacts_dir: pathlib.Path,
    artifact_report_path: pathlib.Path,
    warnings: list[str],
    errors: list[str],
) -> list[InceptionDeploymentPlanItem]:
    plan: list[InceptionDeploymentPlanItem] = []
    if not shell_project.exists() or not shell_project.is_file():
        errors.append(f"Shell project ZIP does not exist: {shell_project}")
    elif shell_project.suffix.lower() != ".zip":
        warnings.append(f"Shell project does not have .zip suffix: {shell_project}")
    if not upload_artifacts_dir.exists() or not upload_artifacts_dir.is_dir():
        errors.append(f"Upload artifacts directory does not exist: {upload_artifacts_dir}")
        return plan
    if not artifact_report_path.exists() or not artifact_report_path.is_file():
        errors.append(f"Artifact report does not exist: {artifact_report_path}")
        return plan

    try:
        artifact_report = json.loads(artifact_report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Could not read artifact report: {exc}")
        return plan

    if artifact_report.get("mode") != "flattened-documents":
        errors.append(f"Unsupported artifact report mode: {artifact_report.get('mode')!r}")
    uploads = artifact_report.get("uploads")
    if not isinstance(uploads, list):
        errors.append("Artifact report must contain an uploads list.")
        return plan
    if not uploads:
        warnings.append("Artifact report contains no uploads.")

    seen_remote_names: set[str] = set()
    for idx, upload in enumerate(uploads):
        if not isinstance(upload, dict):
            errors.append(f"Upload #{idx + 1} is not an object.")
            continue
        remote_name = str(upload.get("remote_document_name", "")).strip()
        if not remote_name:
            errors.append(f"Upload #{idx + 1} has no remote_document_name.")
            continue
        if remote_name in seen_remote_names:
            errors.append(f"Duplicate remote document name: {remote_name}")
        seen_remote_names.add(remote_name)
        if "INITIAL_CAS" in remote_name:
            errors.append(f"INITIAL_CAS must not be uploaded: {remote_name}")
        cas_format = str(upload.get("format", "")).strip().lower()
        if cas_format not in SUPPORTED_UPLOAD_FORMATS:
            errors.append(f"Unsupported format for {remote_name}: {cas_format!r}")
        artifact_path = _resolve_artifact_path(upload, upload_artifacts_dir)
        if not artifact_path.exists() or not artifact_path.is_file():
            errors.append(f"Artifact file for {remote_name} does not exist: {artifact_path}")
        plan.append(
            InceptionDeploymentPlanItem(
                source_member=str(upload.get("source_member", "")),
                source_document=str(upload.get("source_document", "")),
                source_annotator=str(upload.get("source_annotator", "")),
                remote_document_name=remote_name,
                artifact_path=artifact_path,
                cas_format=cas_format,
                decision_count=int(upload.get("decision_count", 0) or 0),
                changed_annotation_count=int(upload.get("changed_annotation_count", 0) or 0),
            )
        )
    return plan


def _resolve_artifact_path(upload: dict[str, Any], upload_artifacts_dir: pathlib.Path) -> pathlib.Path:
    output_path = upload.get("output_path")
    if output_path:
        candidate = pathlib.Path(str(output_path))
        if candidate.is_absolute() or candidate.exists():
            return candidate
        nested_candidate = upload_artifacts_dir / candidate
        if nested_candidate.exists():
            return nested_candidate
    return upload_artifacts_dir / str(upload.get("remote_document_name", ""))


def _deployment_report_payload(
    *,
    dry_run: bool,
    applied: bool,
    shell_project: pathlib.Path,
    upload_artifacts_dir: pathlib.Path,
    artifact_report_path: pathlib.Path,
    plan: list[InceptionDeploymentPlanItem],
    warnings: list[str],
    errors: list[str],
    imported_project_id: Optional[int],
    imported_project_name: Optional[str],
    upload_results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": "snomed-post-processing.inception-sanitized-deployment",
        "schema_version": 1,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mode": "flattened-documents",
        "dry_run": dry_run,
        "applied": applied,
        "shell_project": str(shell_project),
        "upload_artifacts_dir": str(upload_artifacts_dir),
        "artifact_report": str(artifact_report_path),
        "imported_project_id": imported_project_id,
        "imported_project_name": imported_project_name,
        "planned_upload_count": len(plan),
        "would_import_shell_project": str(shell_project),
        "would_create_documents": [item.remote_document_name for item in plan],
        "would_upload_annotations": len(plan),
        "uploads": [dataclasses.asdict(item) | {"artifact_path": str(item.artifact_path)} for item in plan],
        "upload_results": upload_results,
        "warnings": list(warnings),
        "errors": list(errors),
    }


def _write_report(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_password(*, password: Optional[str], password_env: Optional[str]) -> Optional[str]:
    if password:
        return password
    if password_env:
        return os.getenv(password_env)
    return None


def _pycaprio_client(inception_url: str, username: str, password: str, *, verify_tls: bool):
    from pycaprio import Pycaprio

    kwargs: dict[str, Any] = {
        "inception_host": inception_url,
        "authentication": (username, password),
    }
    signature = inspect.signature(Pycaprio)
    if "verify" in signature.parameters:
        kwargs["verify"] = verify_tls
    return Pycaprio(**kwargs)


def prepare_remote_upload_cas_bytes(cas_bytes: bytes, cas_format: str, typesystem=None) -> bytes:
    cas = _load_deployment_cas(cas_bytes, cas_format, typesystem=typesystem)
    _remove_document_metadata(cas)
    _ensure_cas_metadata(cas)
    _normalize_sentence_boundaries(cas)
    _ensure_non_whitespace_text_sentence_coverage(cas)
    _ensure_annotation_sentence_coverage(cas)
    if cas_format == "jsoncas":
        return cas.to_json().encode("utf-8")
    if cas_format == "xmi":
        return cas.to_xmi().encode("utf-8")
    raise InceptionDeploymentError(f"Unsupported CAS format: {cas_format}")


def inspect_remote_upload_cas_compatibility(cas_bytes: bytes, cas_format: str, typesystem=None) -> InceptionCasCompatibilityReport:
    cas = _load_deployment_cas(cas_bytes, cas_format, typesystem=typesystem)
    sentence_type_name = "de.tudarmstadt.ukp.dkpro.core.api.segmentation.type.Sentence"
    sentences = []
    if cas.typesystem.contains_type(sentence_type_name):
        sentences = sorted((int(s.begin or 0), int(s.end or 0)) for s in cas.select(sentence_type_name))
    text = cas.sofa_string or ""
    overlaps = sum(1 for previous, current in zip(sentences, sentences[1:]) if current[0] < previous[1])
    whitespace = sum(
        1
        for begin, end in sentences
        if begin >= end
        or begin < 0
        or end > len(text)
        or text[begin].isspace()
        or text[end - 1].isspace()
    )
    outside = 0
    sentence_spans = set(sentences)
    for ann in list(_project_layer_annotations(cas)):
        if ann.begin is None or ann.end is None or ann.begin >= ann.end:
            continue
        if not _span_boundaries_inside_sentences(int(ann.begin), int(ann.end), sentence_spans):
            outside += 1
    cas_metadata_type = "de.tudarmstadt.ukp.clarin.webanno.api.type.CASMetadata"
    document_metadata_type = "de.tudarmstadt.ukp.dkpro.core.api.metadata.type.DocumentMetaData"
    cas_metadata_count = (
        len(list(cas.select(cas_metadata_type))) if cas.typesystem.contains_type(cas_metadata_type) else 0
    )
    document_metadata_count = (
        len(list(cas.select(document_metadata_type)))
        if cas.typesystem.contains_type(document_metadata_type)
        else 0
    )
    return InceptionCasCompatibilityReport(
        sentence_count=len(sentences),
        sentence_overlap_count=overlaps,
        sentence_whitespace_count=whitespace,
        outside_sentence_annotation_count=outside,
        cas_metadata_count=cas_metadata_count,
        document_metadata_count=document_metadata_count,
    )


_prepare_remote_upload_cas_bytes = prepare_remote_upload_cas_bytes


def _load_deployment_cas(cas_bytes: bytes, cas_format: str, typesystem=None):
    with io.BytesIO(cas_bytes) as fi:
        if cas_format == "jsoncas":
            return cassis.load_cas_from_json(fi, typesystem=typesystem)
        if cas_format == "xmi":
            return cassis.load_cas_from_xmi(fi, typesystem=typesystem, lenient=True)
    raise InceptionDeploymentError(f"Unsupported CAS format: {cas_format}")


def _remove_document_metadata(cas) -> None:
    type_name = "de.tudarmstadt.ukp.dkpro.core.api.metadata.type.DocumentMetaData"
    if not cas.typesystem.contains_type(type_name):
        return
    for fs in list(cas.select(type_name)):
        cas.remove(fs)


def _ensure_cas_metadata(cas) -> None:
    type_name = "de.tudarmstadt.ukp.clarin.webanno.api.type.CASMetadata"
    if not cas.typesystem.contains_type(type_name):
        metadata_type = cas.typesystem.create_type(type_name, supertypeName="uima.tcas.Annotation")
        for feature_name, range_type in (
            ("projectId", "uima.cas.Long"),
            ("projectName", "uima.cas.String"),
            ("sourceDocumentId", "uima.cas.Long"),
            ("sourceDocumentName", "uima.cas.String"),
            ("username", "uima.cas.String"),
            ("lastChangedOnDisk", "uima.cas.Long"),
        ):
            try:
                cas.typesystem.create_feature(metadata_type, feature_name, range_type)
            except ValueError:
                pass
    if list(cas.select(type_name)):
        return
    CASMetadata = cas.typesystem.get_type(type_name)
    marker = CASMetadata(begin=0, end=0)
    for feature_name, value in (
        ("projectId", 0),
        ("projectName", ""),
        ("sourceDocumentId", 0),
        ("sourceDocumentName", ""),
        ("username", ""),
        ("lastChangedOnDisk", -1),
    ):
        try:
            marker.set(feature_name, value)
        except Exception:
            pass
    cas.add(marker)


def _normalize_sentence_boundaries(cas) -> None:
    sentence_type_name = "de.tudarmstadt.ukp.dkpro.core.api.segmentation.type.Sentence"
    if not cas.typesystem.contains_type(sentence_type_name):
        return
    text = cas.sofa_string or ""
    for sentence in list(cas.select(sentence_type_name)):
        begin = int(sentence.begin or 0)
        end = int(sentence.end or 0)
        while begin < end and text[begin].isspace():
            begin += 1
        while end > begin and text[end - 1].isspace():
            end -= 1
        if begin >= end:
            cas.remove(sentence)
            continue
        sentence.begin = begin
        sentence.end = end


def _ensure_non_whitespace_text_sentence_coverage(cas) -> None:
    sentence_type_name = "de.tudarmstadt.ukp.dkpro.core.api.segmentation.type.Sentence"
    if not cas.typesystem.contains_type(sentence_type_name):
        sentence_type = cas.typesystem.create_type(
            sentence_type_name, supertypeName="uima.tcas.Annotation"
        )
    else:
        sentence_type = cas.typesystem.get_type(sentence_type_name)
    text = cas.sofa_string or ""
    existing_spans = sorted((int(s.begin or 0), int(s.end or 0)) for s in cas.select(sentence_type_name))
    supplemental_spans: list[tuple[int, int]] = []
    cursor = 0
    for begin, end in existing_spans:
        supplemental_spans.extend(_non_whitespace_gap_spans(text, cursor, begin))
        cursor = max(cursor, end)
    supplemental_spans.extend(_non_whitespace_gap_spans(text, cursor, len(text)))
    for span in _merge_non_overlapping_sentence_spans(set(existing_spans), supplemental_spans):
        if span not in set(existing_spans):
            cas.add(sentence_type(begin=span[0], end=span[1]))
            existing_spans.append(span)


def _non_whitespace_gap_spans(text: str, begin: int, end: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = max(0, begin)
    end = min(len(text), end)
    while cursor < end:
        while cursor < end and text[cursor].isspace():
            cursor += 1
        span_begin = cursor
        while cursor < end and not text[cursor].isspace():
            cursor += 1
        # Keep adjacent words in the same uncovered heading/line segment until a
        # blank-line/newline boundary. This creates visible rows for headings
        # without extending over surrounding whitespace.
        while cursor < end:
            whitespace_begin = cursor
            while cursor < end and text[cursor].isspace() and text[cursor] not in "\n\r":
                cursor += 1
            if cursor >= end or text[cursor] in "\n\r":
                cursor = whitespace_begin
                break
            while cursor < end and not text[cursor].isspace():
                cursor += 1
        span_end = cursor
        while span_end > span_begin and text[span_end - 1].isspace():
            span_end -= 1
        if span_begin < span_end:
            spans.append((span_begin, span_end))
        while cursor < end and text[cursor].isspace():
            cursor += 1
    return spans


def _ensure_annotation_sentence_coverage(cas) -> None:
    sentence_type_name = "de.tudarmstadt.ukp.dkpro.core.api.segmentation.type.Sentence"
    if not cas.typesystem.contains_type(sentence_type_name):
        sentence_type = cas.typesystem.create_type(
            sentence_type_name, supertypeName="uima.tcas.Annotation"
        )
    else:
        sentence_type = cas.typesystem.get_type(sentence_type_name)
    sentence_spans = {(s.begin, s.end) for s in cas.select(sentence_type_name)}
    supplemental_spans: list[tuple[int, int]] = []
    for ann in list(_project_layer_annotations(cas)):
        if ann.begin is None or ann.end is None or ann.begin >= ann.end:
            continue
        known_spans = sentence_spans | set(supplemental_spans)
        if _span_boundaries_inside_sentences(ann.begin, ann.end, known_spans):
            continue
        supplemental_spans.append(_expand_to_sentence_like_span(cas.sofa_string or "", ann.begin, ann.end))
    for span in _merge_non_overlapping_sentence_spans(sentence_spans, supplemental_spans):
        if span not in sentence_spans:
            cas.add(sentence_type(begin=span[0], end=span[1]))
            sentence_spans.add(span)


def _merge_non_overlapping_sentence_spans(
    existing_spans: set[tuple[int, int]], supplemental_spans: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    if not supplemental_spans:
        return []
    existing = sorted(existing_spans)
    merged: list[tuple[int, int]] = []
    for begin, end in sorted(supplemental_spans):
        if begin >= end:
            continue
        # Clip against existing sentence spans. Supplemental spans should only
        # fill gaps; they must not overlap existing segmentation.
        clipped_parts = [(begin, end)]
        for ex_begin, ex_end in existing:
            next_parts: list[tuple[int, int]] = []
            for part_begin, part_end in clipped_parts:
                if ex_end <= part_begin or ex_begin >= part_end:
                    next_parts.append((part_begin, part_end))
                    continue
                if part_begin < ex_begin:
                    next_parts.append((part_begin, ex_begin))
                if ex_end < part_end:
                    next_parts.append((ex_end, part_end))
            clipped_parts = next_parts
            if not clipped_parts:
                break
        for part in clipped_parts:
            if merged and part[0] <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], part[1]))
            else:
                merged.append(part)
    return merged


def _project_layer_annotations(cas):
    for type_ in cas.typesystem.get_types():
        type_name = type_.name
        if type_name in {
            "uima.tcas.Annotation",
            "uima.tcas.DocumentAnnotation",
            "de.tudarmstadt.ukp.dkpro.core.api.segmentation.type.Sentence",
            "de.tudarmstadt.ukp.dkpro.core.api.segmentation.type.Token",
            "de.tudarmstadt.ukp.clarin.webanno.api.type.CASMetadata",
        }:
            continue
        if not (
            type_name.startswith("webanno.custom.")
            or type_name.startswith("webanno.")
            or type_name.startswith("de.tudarmstadt.ukp.dkpro.core.api.ner.")
        ):
            continue
        try:
            yield from cas.select(type_name)
        except Exception:
            continue


def _span_boundaries_inside_sentences(begin: int, end: int, sentence_spans: set[tuple[int, int]]) -> bool:
    return any(s_begin <= begin <= s_end for s_begin, s_end in sentence_spans) and any(
        s_begin <= end <= s_end for s_begin, s_end in sentence_spans
    )


def _expand_to_sentence_like_span(text: str, begin: int, end: int) -> tuple[int, int]:
    left = max(0, begin)
    right = min(len(text), end)
    while left > 0 and text[left - 1] not in "\n\r.!?":
        left -= 1
    while right < len(text) and text[right] not in "\n\r.!?":
        right += 1
    while left < right and text[left].isspace():
        left += 1
    while right > left and text[right - 1].isspace():
        right -= 1
    if left >= right:
        return max(0, begin), min(len(text), end)
    return left, right


def _extract_sofa_text(artifact_path: pathlib.Path, cas_format: str) -> str:
    with artifact_path.open("rb") as fi:
        if cas_format == "jsoncas":
            cas = cassis.load_cas_from_json(fi)
        elif cas_format == "xmi":
            cas = cassis.load_cas_from_xmi(fi, lenient=True)
        else:
            raise InceptionDeploymentError(f"Unsupported CAS format: {cas_format}")
    return cas.sofa_string or ""


def _document_name_without_cas_suffix(remote_document_name: str) -> str:
    name = pathlib.PurePosixPath(remote_document_name).name
    for suffix in (".json", ".xmi"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return name
