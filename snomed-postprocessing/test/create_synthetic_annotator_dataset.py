"""Build an offline-only synthetic workflow fixture; never copies clinical CAS data.

Run: .venv/Scripts/python test/create_synthetic_annotator_dataset.py --output NEW_DIRECTORY
The output directory must not contain files with the generated names.
"""
from __future__ import annotations

import argparse
import dataclasses
import io
import json
import pathlib
import re
import zipfile

import cassis
import h5py
import numpy as np

from snomed_post_processing.findings_io import write_critical_findings_json
from snomed_post_processing.sanitization import SanitizationResolver
from snomed_post_processing.sanitization.concept_rules import (
    DEFAULT_CONCEPT_RULES, decision_key, preview_concept_rules, rules_json_text,
)
from snomed_post_processing.sanitization.conditions import (
    DEFAULT_CONDITION_ASSOCIATIONS, apply_conditions, finding_key,
)
from snomed_post_processing.sanitization.decisions_json import sanitization_decisions_json_text
from snomed_post_processing.sanitization.json_io import write_sanitization_suggestions_json
from snomed_post_processing.uima_processing import create_log_from_results, process_inception_zip

LAYER = "webanno.custom.Concept"
PREFIX = "http://snomed.info/id/"
ANNOTATORS = ("alice", "bob")
SENTENCE = "de.tudarmstadt.ukp.dkpro.core.api.segmentation.type.Sentence"
TOKEN = "de.tudarmstadt.ukp.dkpro.core.api.segmentation.type.Token"
DOCUMENTS = {
    "rules.txt": (
        "SYNTHETIC ONLY. Number 42; date 2026-01-15; accepted control.",
        (("42", "410680006"), ("2026-01-15", "410671006"), ("accepted control", "990000002")),
    ),
    "automatic.txt": (
        "SYNTHETIC ONLY. Legacy amber.",
        (("Legacy amber", "990000101"),),
    ),
    "manual-controls.txt": (
        "SYNTHETIC ONLY. Legacy cobalt. Blocked violet. Unknown silver.",
        (("Legacy cobalt", "990000102"), ("Blocked violet", "990000301"), ("Unknown silver", "990000404")),
    ),
}
# code, label, active, included, excluded. The 990... identifiers are toy codes,
# NOT assertions that these SCTIDs/labels exist in any SNOMED CT release.
CONCEPTS = (
    ("410680006", "Number (attribute)", True, False, False),
    ("410671006", "Date (attribute)", True, True, False),
    ("410672004", "Date property (qualifier value)", True, False, False),
    ("990000002", "SYNTHETIC accepted control (finding)", True, True, False),
    ("990000101", "SYNTHETIC legacy amber (finding)", False, False, False),
    ("990000102", "SYNTHETIC legacy cobalt (finding)", False, False, False),
    ("990000201", "SYNTHETIC current amber (finding)", True, True, False),
    ("990000202", "SYNTHETIC current cobalt A (finding)", True, True, False),
    ("990000203", "SYNTHETIC current cobalt B (finding)", True, True, False),
    ("990000301", "SYNTHETIC blocked violet (finding)", True, True, True),
)
GENERATED = ("project.zip", "policy.hdf5", "critical-findings.json", "suggestions.json",
             "concept-rules.json", "staged-decisions.json", "expected.json")


def write_policy(path):
    string = h5py.string_dtype("utf-8")
    indices = {row[0]: i for i, row in enumerate(CONCEPTS)}
    with h5py.File(path, "w") as h:
        h.attrs["synthetic_fixture"] = True
        concepts = h.create_group("concepts")
        concepts.attrs["release_date"] = "20260101"
        concepts.attrs["policy_date"] = "20260101"
        concepts.attrs["rf2_view"] = "synthetic-not-RF2"
        for name, column in (("codes", 0), ("fsn", 1)):
            concepts.create_dataset(name, data=np.array([r[column] for r in CONCEPTS], dtype=object), dtype=string)
        concepts.create_dataset("active", data=np.array([r[2] for r in CONCEPTS], dtype=bool))
        for name, column in (("whitelist", 3), ("blacklist", 4)):
            h.create_group(f"policy_views/{name}/0").create_dataset(
                "concept_index", data=np.array([i for i, r in enumerate(CONCEPTS) if r[column]], dtype="int64"))
        associations = (("990000101", "990000201"), ("990000102", "990000202"), ("990000102", "990000203"))
        hist = h.create_group("historical_associations")
        for name, values in (
            ("source_index", [indices[a] for a, _ in associations]),
            ("target_index", [indices[b] for _, b in associations]),
            ("association_type_id", [0] * len(associations)),
        ):
            hist.create_dataset(name, data=np.array(values, dtype="int64"))
        hist.create_dataset("active", data=np.ones(len(associations), dtype=bool))
        for name, values in (
            ("association_types", ["REPLACED_BY"]),
            ("effective_time", ["20260101"] * len(associations)),
            ("refset_id", ["900000000000526001"] * len(associations)),
        ):
            hist.create_dataset(name, data=np.array(values, dtype=object), dtype=string)


def _layer(name, *, features=(), built_in=False):
    return dict(name=name, uiName=name.rsplit(".", 1)[-1], type="span", enabled=True,
                built_in=built_in, anchoring_mode="CHARACTERS", cross_sentence=False,
                multiple_tokens=True, allow_stacking=False, overlap_mode="NO_OVERLAP",
                readonly=False, features=[dict(name=f, uiName=f, type="uima.cas.String",
                enabled=True, visible=True, required=False, multi_value_mode="NONE",
                link_mode="NONE", traits="{}") for f in features], traits="{}")


def write_project(path):
    ts = cassis.TypeSystem()
    concept = ts.create_type(LAYER, supertypeName="uima.tcas.Annotation")
    for feature in ("id", "literal", "note"):
        ts.create_feature(concept, feature, "uima.cas.String")
    sentence = ts.create_type(SENTENCE, supertypeName="uima.tcas.Annotation")
    token = ts.create_type(TOKEN, supertypeName="uima.tcas.Annotation")
    metadata = {
        "version": 1, "application_name": "INCEpTION", "application_version": "41.3",
        "name": "SYNTHETIC annotator scope demo", "slug": "synthetic-annotator-scope",
        "description": "Artificial offline fixture; no patients, no real terminology release.",
        "mode": "ANNOTATION", "script_direction": "LTR", "state": "ANNOTATION_IN_PROGRESS",
        "source_documents": [dict(name=name, format="text", state="ANNOTATION_IN_PROGRESS") for name in DOCUMENTS],
        "annotation_documents": [dict(name=name, user=user, state="IN_PROGRESS") for name in DOCUMENTS for user in ANNOTATORS],
        "layers": [_layer(LAYER, features=("id", "literal", "note")), _layer(SENTENCE, built_in=True), _layer(TOKEN, built_in=True)],
        "tag_sets": [], "project_users": [], "project_permissions": [],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        def member(name, content):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, content)
        member("exportedproject.json", json.dumps(metadata, indent=2))
        member("TypeSystem.xml", ts.to_xml())
        for name, (text, spans) in DOCUMENTS.items():
            member(f"source/{name}", text)
            for user in (None, *ANNOTATORS):
                cas = cassis.Cas(typesystem=ts, sofa_string=text)
                cas.add(sentence(begin=0, end=len(text)))
                for match in re.finditer(r"\S+", text):
                    cas.add(token(begin=match.start(), end=match.end()))
                if user:
                    for covered, code in spans:
                        begin = text.index(covered)
                        literal = " 0042 ± " if code == "410680006" else covered
                        cas.add(concept(begin=begin, end=begin + len(covered), id=PREFIX + code,
                                        literal=literal, note=f"SYNTHETIC/{user}/{code}; preserve me"))
                if user == "bob":
                    member(f"annotation/{name}/{user}.xmi", cas.to_xmi())
                else:
                    member(f"annotation/{name}/{user or 'INITIAL_CAS'}.json", cas.to_json())


def collect_findings(project, policy, annotators=None):
    corpus = process_inception_zip(project, annotator_filter=annotators, annotation_types=[LAYER], ignore_overlap_types=[])
    findings = []
    create_log_from_results(corpus, io.StringIO(), io.StringIO(), policy, critical_findings=findings)
    return findings


def stage_decisions(suggestions, rules):
    reserved = {decision_key(item) for item in rules}
    decisions, choices = [], {}
    for index, item in enumerate(suggestions):
        if finding_key(item.finding) in reserved:
            continue
        f = item.finding
        labels = tuple(f"{c.code} — {c.fsn}" for c in item.candidates)
        choices[index] = labels
        candidate = item.candidates[0] if len(item.candidates) == 1 else None
        decisions.append(dict(suggestion_index=index, document=f.document, annotator=f.annotator,
            layer=f.layer, offset=list(f.offset), source_code=f.code, covered_text=f.covered_text,
            action="none", apply=False, delete_annotation=False, manual_edit=False,
            reviewed_by_human=False, resolved=False, valid_choice=candidate is not None,
            replacement_code=candidate.code if candidate else None,
            replacement_fsn=candidate.fsn if candidate else None,
            replacement_choice=labels[0] if candidate else "— no replacement selected —"))
    return apply_conditions(suggestions, decisions + rules, DEFAULT_CONDITION_ASSOCIATIONS, choices)


def build_dataset(output):
    output = pathlib.Path(output)
    # Refuse to overwrite even one existing fixture asset.
    existing = [str(output / name) for name in GENERATED if (output / name).exists()]
    if existing:
        raise FileExistsError("Choose a new output directory; files already exist: " + ", ".join(existing))
    output.mkdir(parents=True, exist_ok=True)
    project, policy = output / "project.zip", output / "policy.hdf5"
    write_project(project)
    write_policy(policy)
    metadata = {"synthetic": True, "fixture": "synthetic-annotator-scope", "annotators": [],
                "annotation_types": [LAYER], "id_prefix": PREFIX, "id_feature": "id"}
    findings = collect_findings(project, policy)
    write_critical_findings_json(findings, output / "critical-findings.json", metadata=metadata)
    suggestions = SanitizationResolver(policy).suggest_all(findings)
    write_sanitization_suggestions_json(suggestions, output / "suggestions.json", metadata=metadata)
    rules = preview_concept_rules(project, policy, DEFAULT_CONCEPT_RULES, annotation_types=[LAYER])
    (output / "concept-rules.json").write_text(rules_json_text(DEFAULT_CONCEPT_RULES), encoding="utf-8")
    automatic = stage_decisions(suggestions, rules)
    review_metadata = dict(metadata, concept_rules=[dataclasses.asdict(r) for r in DEFAULT_CONCEPT_RULES],
        concept_rule_scope={"layers": LAYER, "documents": "", "annotators": ""},
        reviewed_documents=sorted(automatic.reviewed_documents),
        automatic_reviewed_documents=sorted(automatic.reviewed_documents),
        manual_review_layer="webanno.custom.ManualReview",
        note="Rules and historical condition staged; negative controls deliberately remain unreviewed.")
    (output / "staged-decisions.json").write_text(
        sanitization_decisions_json_text(automatic.decisions, metadata=review_metadata), encoding="utf-8")
    expected = dict(synthetic=True, annotators=list(ANNOTATORS), document_count=3,
        annotation_count=14, critical_finding_count=10, inclusion_findings=8, exclusion_findings=2,
        rule_decision_count=4, actual_policy_overrides=2, automatic_condition_selections=2,
        selected_decisions=6, pending_manual_decisions=6, automatically_reviewed_documents=["automatic.txt"],
        alice_only=dict(annotation_count=7, critical_finding_count=5, rule_decision_count=2,
                        automatic_condition_selections=1, selected_decisions=3, upload_artifact_count=3),
        all_upload_artifact_count=6)
    (output / "expected.json").write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    return expected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_dataset(args.output), indent=2))
