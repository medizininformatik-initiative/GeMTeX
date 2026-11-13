"""Read-only policy checking and in-memory reports, independent of either GUI."""
from dataclasses import dataclass, replace
from io import StringIO
import json
from pathlib import Path

from snomed_post_processing.findings_io.json_io import critical_findings_json_text
from snomed_post_processing.uima_processing import (
    CriticalFinding, create_log_from_results, get_annotator_names, process_inception_zip,
)
from snomed_post_processing.uima_processing.scope import normalize_annotators


@dataclass(frozen=True)
class PolicySettings:
    annotators: tuple[str, ...] = ()
    annotation_types: tuple[str, ...] = ("gemtex.Concept", "webanno.custom.Concept")
    ignore_overlap_types: tuple[str, ...] = ()
    ignore_overlap_mode: str = "overlap"
    id_prefix: str = "http://snomed.info/id/"
    id_feature: str = "id"


@dataclass(frozen=True)
class PolicyResult:
    settings: PolicySettings
    findings: tuple[CriticalFinding, ...]
    critical_documents: int
    reports: dict[str, str]


def project_annotators(project: Path) -> dict[str, str]:
    names, only_ser = get_annotator_names(project)
    if only_ser:
        raise ValueError("Java serialized CAS is unsupported; export JSON CAS or XMI instead.")
    if not names:
        raise ValueError("No supported annotations found in the project ZIP.")
    return {name.strip().lower(): name for name in sorted(names)}


def check_policy(project: Path, lists: Path, settings: PolicySettings) -> PolicyResult:
    """Use the existing policy engine; never write alongside the source files."""
    settings = replace(settings, annotators=normalize_annotators(settings.annotators))
    if not settings.id_feature.strip():
        raise ValueError("An annotation ID feature is required.")
    project_annotators(project)
    corpus = process_inception_zip(
        project, annotator_filter=list(settings.annotators) or None,
        annotation_types=list(settings.annotation_types) or ["gemtex.Concept"],
        ignore_overlap_types=list(settings.ignore_overlap_types),
        ignore_overlap_mode=settings.ignore_overlap_mode,
        id_prefix=settings.id_prefix, id_feature=settings.id_feature,
    )
    if corpus is None:
        raise ValueError("Project processing failed.")
    markdown, masked = StringIO(), StringIO()
    report, findings = {}, []
    count = create_log_from_results(corpus, markdown, masked, lists,
                                   dump_dict=report, critical_findings=findings)
    metadata = dict(source="nicegui-policy-check", annotators=list(settings.annotators),
                    lists_path=str(lists), annotation_types=list(settings.annotation_types) or ["gemtex.Concept"],
                    ignore_overlap_types=list(settings.ignore_overlap_types),
                    ignore_overlap_mode=settings.ignore_overlap_mode,
                    id_prefix=settings.id_prefix, id_feature=settings.id_feature)
    return PolicyResult(settings, tuple(findings), count, {
        "critical-findings.json": critical_findings_json_text(findings, metadata=metadata),
        "policy-report.md": markdown.getvalue(),
        "policy-report.masked.md": masked.getvalue(),
        "policy-report.json": json.dumps(report, ensure_ascii=False, indent=2),
    })
