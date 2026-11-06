"""Explicit concept rules, independent of policy findings and lexical fallback."""
from __future__ import annotations

import dataclasses
import json
import pathlib
import zipfile
from typing import Any, Iterable

import h5py

from ..hdf5_handling.policy import decode_array, read_candidate_validity_sets
from ..uima_processing.io import (
    _annotator_name_from_cas_path, _load_cas_from_zip_member,
    _load_typesystem_from_zip, _read_project, _yield_matching_files, _yield_flat_archive_files,
)
from ..uima_processing.extraction import _normalize_annotation_id, _normalized_id_prefix


@dataclasses.dataclass(frozen=True)
class ConceptRule:
    rule_id: str
    name: str
    source_code: str
    action: str
    target_code: str = ""
    enabled: bool = True
    override_policy: bool = True


DEFAULT_CONCEPT_RULES = (
    ConceptRule("number-clear-id", "Number (attribute)", "410680006", "clear_id"),
    ConceptRule("date-property", "Date (attribute)", "410671006", "replace", "410672004"),
)


def validate_rules(rules: Iterable[ConceptRule]) -> tuple[ConceptRule, ...]:
    rules = tuple(rules)
    ids, sources = set(), set()
    for rule in rules:
        if not all(isinstance(value, str) for value in (rule.rule_id, rule.name, rule.source_code, rule.action, rule.target_code)):
            raise ValueError("Concept-rule identifiers, names, actions, and SCTIDs must be strings.")
        if not rule.rule_id.strip() or rule.rule_id in ids:
            raise ValueError("Each concept rule needs a unique, non-empty rule ID.")
        ids.add(rule.rule_id)
        if not isinstance(rule.enabled, bool) or not isinstance(rule.override_policy, bool):
            raise ValueError(f"Rule {rule.rule_id}: enabled and override_policy must be boolean.")
        if not rule.source_code.isdigit() or rule.action not in {"clear_id", "replace"}:
            raise ValueError(f"Rule {rule.rule_id}: numeric source SCTID and a supported action are required.")
        if rule.action == "clear_id" and rule.target_code:
            raise ValueError(f"Rule {rule.rule_id}: Remove ID only cannot have a target.")
        if rule.action == "replace" and (not rule.target_code.isdigit() or rule.target_code == rule.source_code):
            raise ValueError(f"Rule {rule.rule_id}: a different numeric target SCTID is required.")
        if rule.enabled and rule.source_code in sources:
            raise ValueError(f"Conflicting enabled rules for source SCTID {rule.source_code}.")
        if rule.enabled:
            sources.add(rule.source_code)
    return rules


def rules_json_text(rules: Iterable[ConceptRule]) -> str:
    return json.dumps({
        "schema": "snomed-post-processing.concept-rules", "schema_version": 1,
        "rules": [dataclasses.asdict(rule) for rule in validate_rules(rules)],
    }, ensure_ascii=False, indent=2)


def read_rules_json(source) -> tuple[ConceptRule, ...]:
    payload = json.load(source)
    if payload.get("schema") != "snomed-post-processing.concept-rules" or payload.get("schema_version") != 1:
        raise ValueError("Unsupported concept-rules JSON schema/version.")
    return validate_rules(ConceptRule(**row) for row in payload["rules"])


def decision_key(decision: dict[str, Any]) -> tuple:
    """Stable review identity, intentionally independent of suggestion indices."""
    return (
        decision.get("document", ""), decision.get("annotator", ""),
        decision.get("layer"), tuple(decision.get("offset") or ()),
        decision.get("source_code", ""),
    )


def validate_rule_targets(
    hdf5_path, rules, *, target_view="policy", release_exclude_blacklist=False,
    runtime_blacklist_indices=(),
):
    """Validate active replacement targets; policy overrides never bypass activity."""
    targets = {}
    with h5py.File(hdf5_path, "r") as h5:
        validity = read_candidate_validity_sets(
            h5, mode=target_view, exclude_blacklist=release_exclude_blacklist,
            runtime_blacklist_indices=runtime_blacklist_indices,
        )
        codes = decode_array(h5["concepts/codes"][:])
        fsns = decode_array(h5["concepts/fsn"][:])
        by_code = {code: idx for idx, code in enumerate(codes)}
        for rule in validate_rules(rules):
            if not rule.enabled or rule.action != "replace":
                continue
            idx = by_code.get(rule.target_code)
            if idx is None or not validity.check_index(idx).active:
                raise ValueError(f"Rule {rule.rule_id}: target {rule.target_code} must exist and be active.")
            acceptable = validity.check_index(idx).acceptable
            if not acceptable and not rule.override_policy:
                raise ValueError(f"Rule {rule.rule_id}: target {rule.target_code} violates the selected policy; override is off.")
            targets[rule.rule_id] = (fsns[idx], not acceptable)
    return targets


def preview_concept_rules(
    project_path: pathlib.Path, hdf5_path: pathlib.Path, rules: Iterable[ConceptRule], *,
    annotation_types: Iterable[str], documents: Iterable[str] = (), annotators: Iterable[str] = (),
    id_prefix: str = "http://snomed.info/id/", id_feature: str = "id",
    target_view: str = "policy", release_exclude_blacklist: bool = False,
    runtime_blacklist_indices: Iterable[int] = (),
) -> list[dict[str, Any]]:
    """Scan original annotations once; never chain rules or modify the source CAS.

    A bad CAS or ambiguous annotation identity aborts the preview rather than
    silently returning a partially successful set of automatic decisions.
    """
    rules = validate_rules(rules)
    enabled = {rule.source_code: rule for rule in rules if rule.enabled}
    layers = tuple(dict.fromkeys(annotation_types))
    if not layers:
        raise ValueError("Select at least one annotation layer for concept rules.")
    documents, annotators = set(documents), {name.lower() for name in annotators}
    targets = validate_rule_targets(
        hdf5_path, enabled.values(), target_view=target_view,
        release_exclude_blacklist=release_exclude_blacklist,
        runtime_blacklist_indices=runtime_blacklist_indices,
    )

    decisions, seen = [], set()
    with zipfile.ZipFile(project_path) as archive:
        project = _read_project(archive, project_path.name)
        files = list(_yield_matching_files(project, archive, project_path.name, [".json", ".xmi"]))
        flat_layout = project is None
        if not files:
            files = list(_yield_flat_archive_files(archive, [".json", ".xmi"]))
            flat_layout = True
        if not files and enabled:
            raise ValueError("No JSONCAS/XMI members found for concept-rule scanning; serialized CAS is not supported.")
        for document, paths in files:
            if documents and document not in documents:
                continue
            for path in paths:
                annotator = _annotator_name_from_cas_path(path, fallback_flat_layout=flat_layout)
                if annotators and annotator.lower() not in annotators:
                    continue
                try:
                    cas = _load_cas_from_zip_member(archive, path, typesystem=_load_typesystem_from_zip(archive, path))
                except Exception as exc:
                    raise ValueError(f"Could not scan concept rules in CAS member {path!r} ({type(exc).__name__}).") from exc
                member_seen = set()
                for layer in layers:
                    if not cas.typesystem.contains_type(layer):
                        continue
                    for annotation in cas.select(layer):
                        # Selecting both a base type and its subtype must not duplicate decisions.
                        if annotation.xmiID in member_seen:
                            continue
                        member_seen.add(annotation.xmiID)
                        code = _normalize_annotation_id(annotation.get(id_feature), id_prefix=_normalized_id_prefix(id_prefix))
                        rule = enabled.get(code)
                        if rule is None:
                            continue
                        target_fsn, overridden = targets.get(rule.rule_id, (None, False))
                        decision = {
                            "action": rule.action, "apply": True, "valid_choice": True,
                            "document": document, "annotator": annotator,
                            "layer": annotation.type.name,
                            "offset": [int(annotation.begin), int(annotation.end)],
                            "covered_text": annotation.get_covered_text(), "source_code": code,
                            "replacement_code": rule.target_code or None, "replacement_fsn": target_fsn,
                            "suggestion_status": "Explicit concept rule", "resolved": True,
                            "concept_rule": dataclasses.asdict(rule), "policy_overridden": overridden,
                            "review_note": f"Explicit concept rule: {rule.rule_id}; preserve literal and all other features.",
                        }
                        key = decision_key(decision)
                        if key in seen:
                            raise ValueError(f"Ambiguous annotation identity for concept rule {rule.rule_id} in document {document!r}.")
                        seen.add(key)
                        decisions.append(decision)
    return decisions


def preserve_rule_edits(automatic, previous):
    """Keep explicitly edited rule choices when accepting again or undoing automation."""
    edited = {decision_key(item): item for item in previous if item.get("rule_reviewed_by_human")}
    return [item for item in automatic if decision_key(item) not in edited] + list(edited.values())


def split_rule_conflicts(rule_decisions, manual_decisions, reviewed_documents=()):
    """Do not overwrite explicit manual actions or already reviewed keep decisions."""
    protected = {
        decision_key(item) for item in manual_decisions
        if not item.get("concept_rule") and (
            item.get("action") not in {None, "none"} or item.get("apply")
            or item.get("manual_edit") or item.get("delete_annotation") or item.get("reviewed_by_human")
            or item.get("document") in reviewed_documents
        )
    }
    conflicts = [item for item in rule_decisions if decision_key(item) in protected]
    safe = [item for item in rule_decisions if decision_key(item) not in protected]
    return safe, conflicts
