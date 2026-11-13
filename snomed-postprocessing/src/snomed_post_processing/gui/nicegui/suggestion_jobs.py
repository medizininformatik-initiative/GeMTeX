"""Worker snapshots for suggestions, explicit rules and SNOGIT cache creation."""
from dataclasses import asdict, dataclass, replace
import hashlib
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from snomed_post_processing.findings_io import read_critical_findings_json_with_metadata
from snomed_post_processing.pipelines.policy_check import PolicyResult, PolicySettings
from snomed_post_processing.pipelines.suggestion_generation import GenerationResult, SuggestionSettings, generate_suggestions, replacement_constraints
from snomed_post_processing.sanitization.concept_rules import preview_concept_rules, validate_rule_targets
from snomed_post_processing.sanitization.snogit_sidecar import build_snogit_sidecar, list_snogit_zip_members
from .file_sources import SourceFile
from .suggestions import MAX_SUGGESTIONS_BYTES, load_suggestions_preview


def restore_suggestions(content, filename):
    from snomed_post_processing.sanitization import write_sanitization_markdown_report
    from snomed_post_processing.uima_processing.scope import annotator_in_scope
    preview = load_suggestions_preview(content, filename)
    suggestions = tuple(item for item in preview.source_suggestions
                        if annotator_in_scope(item.finding.annotator, preview.source_annotators))
    report = StringIO()
    write_sanitization_markdown_report(suggestions, report)
    result = GenerationResult(content.decode("utf-8-sig"), report.getvalue(), suggestions,
                              preview.metadata.get("nicegui_generation_binding", ""))
    return result, preview


def stamps(sources):
    return tuple(source.stamp() for source in sources)


@dataclass(frozen=True)
class SuggestionJob:
    project: SourceFile | None
    lists: SourceFile
    policy: PolicySettings
    settings: SuggestionSettings
    custom: SourceFile | None = None
    cache: SourceFile | None = None
    findings_file: SourceFile | None = None
    session_result: PolicyResult | None = None
    session_stamps: tuple | None = None
    findings_stamp: tuple | None = None

    @property
    def sources(self):
        return tuple(source for source in (self.project, self.lists, self.custom, self.cache, self.findings_file) if source is not None)

    def for_process(self):
        """Send paths/data, not unpicklable temporary-directory owners, to spawn workers.

        The awaiting controller retains the original job and its upload owners.
        Policy report bodies are unused by generation and stay in the parent.
        """
        sources = {}
        for name in ("project", "lists", "custom", "cache", "findings_file"):
            source = getattr(self, name)
            sources[name] = replace(source, owner=None) if source is not None else None
        result = replace(self.session_result, reports={}) if self.session_result is not None else None
        return replace(self, **sources, session_result=result)

    def binding(self):
        primary = [(str(source.path.resolve()), source.stamp()) if source else None
                   for source in (self.project, self.lists, self.custom)]
        policy = asdict(self.policy)
        identity = {name: policy[name] for name in ("annotators", "annotation_types", "id_feature", "id_prefix")}
        payload = [primary, identity, self.settings.target_view, self.settings.release_blacklist_mode]
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def run_generation(job):
    before = stamps(job.sources)
    binding = job.binding()
    if job.findings_file is None:
        if job.session_result is None or job.project is None or stamps((job.project, job.lists)) != job.session_stamps:
            raise ValueError("Run a current policy check, or select saved CriticalFindings JSON.")
        findings = job.session_result.findings
        metadata = dict(annotators=list(job.session_result.settings.annotators),
                        id_feature=job.session_result.settings.id_feature, id_prefix=job.session_result.settings.id_prefix)
    else:
        if job.findings_stamp is not None and job.findings_file.stamp() != job.findings_stamp:
            raise ValueError("Restored findings changed. Load them again in tab 1.")
        if job.findings_file.stamp()[2] > MAX_SUGGESTIONS_BYTES:
            raise ValueError("CriticalFindings JSON exceeds the 50 MiB processing limit.")
        with job.findings_file.path.open(encoding="utf-8-sig") as stream:
            findings, metadata = read_critical_findings_json_with_metadata(stream)
    result = generate_suggestions(job.lists.path, findings, metadata, job.policy, job.settings, binding=binding,
                                  project=job.project.path if job.project else None,
                                  cache=job.cache.path if job.cache else None, custom=job.custom.path if job.custom else None)
    # Build review off-thread too; publication is a separate explicit user action.
    preview = load_suggestions_preview(result.json.encode("utf-8"), "generated-suggestions.json")
    if before != stamps(job.sources) or binding != job.binding():
        raise ValueError("Source files changed during generation.")
    return result, preview, before


def run_rules(job, rules):
    if job.project is None:
        raise ValueError("Select a project ZIP for rule scanning.")
    before = stamps(job.sources)
    binding = job.binding()
    constraints = replacement_constraints(job.lists.path, job.settings, job.custom.path if job.custom else None)
    decisions = preview_concept_rules(job.project.path, job.lists.path, rules,
                                     annotation_types=job.policy.annotation_types, annotators=job.policy.annotators,
                                     id_feature=job.policy.id_feature, id_prefix=job.policy.id_prefix, **constraints)
    if before != stamps(job.sources) or binding != job.binding():
        raise ValueError("Source files changed during rule scanning.")
    return decisions, binding, before


def validate_preserved_rules(job, decisions):
    from snomed_post_processing.sanitization.concept_rules import ConceptRule, decision_key
    edited = [item for item in decisions if item.get("rule_reviewed_by_human")]
    if not edited:
        return  # Fresh decisions were already validated by the original-annotation scan.
    constraints = replacement_constraints(job.lists.path, job.settings, job.custom.path if job.custom else None)
    rules = {}
    for item in decisions:
        rule = ConceptRule(**item["concept_rule"])
        if rule.rule_id in rules and rules[rule.rule_id] != rule:
            raise ValueError("Preserved manual rule choices disagree with changed definitions. Clear old decisions first.")
        rules[rule.rule_id] = rule
    targets = validate_rule_targets(job.lists.path, rules.values(), **constraints)
    expected = preview_concept_rules(job.project.path, job.lists.path, rules.values(),
                                    annotation_types=job.policy.annotation_types, annotators=job.policy.annotators,
                                    id_feature=job.policy.id_feature, id_prefix=job.policy.id_prefix, **constraints)
    by_key = {decision_key(item): item for item in expected}
    for item in edited:
        original = by_key.get(decision_key(item))
        if original is None or any(item.get(name) != original.get(name)
                                   for name in ("covered_text", "action", "replacement_code", "concept_rule")):
            raise ValueError("A preserved rule choice does not match the current original annotations and definition.")
        item["replacement_fsn"], item["policy_overridden"] = targets.get(item["concept_rule"]["rule_id"], (None, False))


def inspect_members(source):
    before = source.stamp()
    result = list_snogit_zip_members(source.path)
    if before != source.stamp():
        raise ValueError("SNOGIT source changed during inspection.")
    return result, before


def create_cache(lists, source, members):
    before = stamps((lists, source))
    owner = TemporaryDirectory(prefix="snomed-nicegui-cache-")
    output = SourceFile(Path(owner.name) / "snogit-cache.hdf5", owner)
    build_snogit_sidecar(hdf5_path=lists.path, snogit_zip_path=source.path, output_path=output.path, members=members)
    if before != stamps((lists, source)):
        raise ValueError("Inputs changed during cache creation.")
    return output
