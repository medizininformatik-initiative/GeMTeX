"""In-memory GUI suggestion generation using the existing resolver and rule engines."""
from dataclasses import asdict, dataclass
from io import StringIO
import math

import h5py

from snomed_post_processing.hdf5_handling.metadata import inspect_hdf5_metadata
from snomed_post_processing.hdf5_handling.policy import read_blacklist_rule_file, resolve_blacklist_rule_indices
from snomed_post_processing.review_context import ReviewContext
from snomed_post_processing.sanitization import (
    SUPPORTED_ASSOCIATION_TYPES, SanitizationResolver, apply_semantic_bm25_fallback,
    sanitization_suggestions_json_text, write_sanitization_markdown_report,
)
from snomed_post_processing.uima_processing.scope import annotator_in_scope, normalize_annotators, scope_covers

DEFAULT_ASSOCIATIONS = tuple(name for name in SUPPORTED_ASSOCIATION_TYPES if name not in {"MOVED_FROM", "REFERS_TO"})


@dataclass(frozen=True)
class SuggestionSettings:
    target_view: str = "policy"
    release_blacklist_mode: str = "none"
    allowed_association_types: tuple[str, ...] = DEFAULT_ASSOCIATIONS
    historical_ancestor_fallback: bool = True
    ancestor_max_distance: int | None = 3
    ancestor_max_relative_distance: float | None = 0.35
    semantic_bm25_fallback: bool = True
    blacklist_bm25_suggestions: bool = True
    bm25_min_score: float = 1.5
    bm25_min_lexical_score: float = 0.0
    bm25_max_candidates: int = 5
    bm25_semantic_tag_boost_percent: float = 10.0
    snogit_bm25: bool = True

    def validate(self):
        if self.target_view not in {"policy", "release"} or self.release_blacklist_mode not in {"none", "embedded", "custom", "embedded+custom"}:
            raise ValueError("Select valid replacement requirements.")
        if set(self.allowed_association_types) - set(SUPPORTED_ASSOCIATION_TYPES):
            raise ValueError("Unsupported historical association type.")
        for value, lower, upper in ((self.bm25_min_score, 0, math.inf), (self.bm25_min_lexical_score, 0, 1),
                                     (self.bm25_semantic_tag_boost_percent, 0, 100)):
            if not math.isfinite(value) or not lower <= value <= upper:
                raise ValueError("Invalid BM25 threshold.")
        if type(self.bm25_max_candidates) is not int or not 1 <= self.bm25_max_candidates <= 50:
            raise ValueError("Retain between 1 and 50 candidates (cutoff ties are preserved).")
        if self.ancestor_max_distance is not None and (type(self.ancestor_max_distance) is not int or not 1 <= self.ancestor_max_distance <= 20):
            raise ValueError("Invalid absolute ancestor limit.")
        if self.ancestor_max_relative_distance is not None and (not math.isfinite(self.ancestor_max_relative_distance) or not 0 <= self.ancestor_max_relative_distance <= 1):
            raise ValueError("Invalid relative ancestor limit.")


def replacement_constraints(hdf5, settings, custom=None):
    embedded = settings.target_view == "release" and settings.release_blacklist_mode in {"embedded", "embedded+custom"}
    runtime = frozenset()
    if settings.target_view == "release" and settings.release_blacklist_mode in {"custom", "embedded+custom"}:
        if custom is None:
            raise ValueError("Select a custom exclusion-list rule file.")
        with h5py.File(hdf5, "r") as handle:
            runtime = resolve_blacklist_rule_indices(handle, read_blacklist_rule_file(custom))
    return dict(target_view=settings.target_view, release_exclude_blacklist=embedded, runtime_blacklist_indices=runtime)


@dataclass(frozen=True)
class GenerationResult:
    json: str
    markdown: str
    suggestions: tuple
    binding: str


def generate_suggestions(hdf5, findings, metadata, policy, settings, *, binding, project=None, cache=None, custom=None):
    settings.validate()
    scope = normalize_annotators(policy.annotators)
    source_scope = metadata.get("annotators", [])
    if not isinstance(source_scope, (list, tuple)) or any(not isinstance(name, str) for name in source_scope):
        raise ValueError("Invalid findings annotator scope.")
    if not scope_covers(source_scope, scope):
        raise ValueError("Findings cover a narrower annotator scope. Run policy check again.")
    for name in ("id_feature", "id_prefix"):
        if name in metadata and metadata[name] != getattr(policy, name):
            raise ValueError("Findings ID settings differ from the shared inputs. Recheck or select matching inputs.")
    findings = [finding for finding in findings if annotator_in_scope(finding.annotator, scope)]
    if settings.semantic_bm25_fallback and settings.snogit_bm25 and cache is None:
        raise ValueError("Select or create a processed SNOGIT cache, or explicitly turn SNOGIT off.")
    constraints = replacement_constraints(hdf5, settings, custom)
    resolver = SanitizationResolver(hdf5, allowed_association_types=settings.allowed_association_types,
                                   activate_historical_ancestor_fallback=settings.historical_ancestor_fallback,
                                   ancestor_max_distance=settings.ancestor_max_distance,
                                   ancestor_max_relative_distance=settings.ancestor_max_relative_distance, **constraints)
    suggestions = resolver.suggest_all(findings)
    if settings.semantic_bm25_fallback:
        suggestions = apply_semantic_bm25_fallback(
            suggestions, hdf5, min_score=settings.bm25_min_score,
            min_lexical_score=settings.bm25_min_lexical_score, max_candidates=settings.bm25_max_candidates,
            semantic_tag_boost_percent=settings.bm25_semantic_tag_boost_percent,
            allow_blacklist_findings=settings.blacklist_bm25_suggestions, snogit_sidecar_path=cache, **constraints)
    cache_members = []
    if settings.semantic_bm25_fallback and settings.snogit_bm25 and cache is not None:
        with h5py.File(cache, "r") as handle:
            if "metadata/source_members" in handle:
                cache_members = handle["metadata/source_members"].asstr()[:].tolist()
    summary = inspect_hdf5_metadata(hdf5)
    context = ReviewContext.from_project_path(project, annotators=scope) if project is not None else ReviewContext.from_metadata(metadata)
    contexts = []
    for suggestion in suggestions:
        finding = suggestion.finding
        if not context.missing_documents((finding,)):
            contexts.append(dict(document=finding.document, annotator=finding.annotator, code=finding.code,
                                 offset=list(finding.offset), context=context.label(finding)))
    output_metadata = dict(
        source="nicegui-suggestion-generation", annotators=list(scope), id_prefix=policy.id_prefix,
        id_feature=policy.id_feature, annotation_types=list(policy.annotation_types),
        nicegui_generation_binding=binding, hdf5_file_name=hdf5.name,
        hdf5_release_date=summary.concepts_release_date, hdf5_policy_date=summary.concepts_policy_date,
        hdf5_rf2_view=summary.concepts_rf2_view, finding_count=len(findings), suggestion_count=len(suggestions),
        target_view=settings.target_view, finding_contexts=contexts,
        settings={**asdict(settings), "snogit_cache_path": str(cache) if cache else None,
                  "snogit_members": cache_members, "custom_blacklist_path": str(custom) if custom else None,
                  "enforce_embedded_blacklist": constraints["release_exclude_blacklist"],
                  "custom_blacklist_concepts": len(constraints["runtime_blacklist_indices"]),
                  "bm25_fsn_semantic_tags_excluded": True})
    report = StringIO()
    write_sanitization_markdown_report(suggestions, report)
    return GenerationResult(sanitization_suggestions_json_text(suggestions, metadata=output_metadata),
                            report.getvalue(), tuple(suggestions), binding)
