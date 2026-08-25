"""RF2 TSV row readers for SNOMED CT release ingestion."""

from __future__ import annotations

import csv
import re
import zipfile
from io import TextIOWrapper
from typing import Optional

from .constants import ASSOCIATION_REFSET_IDS, FSN_TYPE_ID, IS_A_TYPE_ID


def _iter_rf2_rows(zf: zipfile.ZipFile, member: str, required_columns: set[str]):
    with zf.open(member) as raw:
        text = TextIOWrapper(raw, encoding="utf-8", newline="")
        reader = csv.DictReader(text, delimiter="\t")
        fieldnames = set(reader.fieldnames or [])
        missing = required_columns - fieldnames
        if missing:
            raise ValueError(
                f"RF2 member {member!r} is missing required columns: {sorted(missing)}"
            )
        yield from reader


def _semantic_tag_from_fsn(fsn: str) -> str:
    match = re.search(r"\(([^()]*)\)\s*$", fsn)
    return match.group(1) if match else ""


def _at_or_before(row: dict[str, str], policy_date: Optional[str]) -> bool:
    return policy_date is None or row.get("effectiveTime", "") <= policy_date


def _read_concept_active_state(
    zf: zipfile.ZipFile,
    member: str,
    *,
    policy_date: Optional[str] = None,
    reconstruct_latest: bool = False,
) -> dict[str, bool]:
    concept_rows: dict[str, tuple[str, bool]] = {}
    concept_active: dict[str, bool] = {}
    for row in _iter_rf2_rows(
        zf, member, {"id", "effectiveTime", "active", "moduleId", "definitionStatusId"}
    ):
        if not _at_or_before(row, policy_date):
            continue
        if reconstruct_latest:
            previous = concept_rows.get(row["id"])
            if previous is None or row["effectiveTime"] >= previous[0]:
                concept_rows[row["id"]] = (row["effectiveTime"], row["active"] == "1")
        else:
            concept_active[row["id"]] = row["active"] == "1"
    if reconstruct_latest:
        return {concept_id: active for concept_id, (_, active) in concept_rows.items()}
    return concept_active


def _read_fsns(
    zf: zipfile.ZipFile,
    member: str,
    known_concepts: set[str],
    *,
    policy_date: Optional[str] = None,
    reconstruct_latest: bool = False,
) -> dict[str, str]:
    fsns: dict[str, str] = {}
    fsn_rows: dict[str, tuple[str, bool, str, str]] = {}
    for row in _iter_rf2_rows(
        zf,
        member,
        {
            "id",
            "effectiveTime",
            "active",
            "moduleId",
            "conceptId",
            "languageCode",
            "typeId",
            "term",
            "caseSignificanceId",
        },
    ):
        if row["typeId"] != FSN_TYPE_ID or row["conceptId"] not in known_concepts:
            continue
        if not _at_or_before(row, policy_date):
            continue
        if reconstruct_latest:
            previous = fsn_rows.get(row["id"])
            if previous is None or row["effectiveTime"] >= previous[0]:
                fsn_rows[row["id"]] = (
                    row["effectiveTime"],
                    row["active"] == "1",
                    row["conceptId"],
                    row["term"],
                )
        elif row["active"] == "1":
            fsns[row["conceptId"]] = row["term"]
    if reconstruct_latest:
        active_fsn_rows = [value for value in fsn_rows.values() if value[1]]
        active_fsn_rows.sort(key=lambda value: (value[2], value[0], value[3]))
        for _effective_time, _active, concept_id, term in active_fsn_rows:
            fsns[concept_id] = term
    return fsns


def _read_active_associations(
    zf: zipfile.ZipFile,
    member: Optional[str],
    *,
    policy_date: Optional[str] = None,
    reconstruct_latest: bool = False,
) -> list[tuple[str, str, str, str, str]]:
    if member is None:
        return []
    associations = []
    association_rows: dict[str, dict[str, str]] = {}
    for row in _iter_rf2_rows(
        zf,
        member,
        {
            "id",
            "effectiveTime",
            "active",
            "moduleId",
            "refsetId",
            "referencedComponentId",
            "targetComponentId",
        },
    ):
        if not _at_or_before(row, policy_date):
            continue
        if reconstruct_latest:
            previous = association_rows.get(row["id"])
            if previous is None or row["effectiveTime"] >= previous["effectiveTime"]:
                association_rows[row["id"]] = row
        elif row["active"] == "1":
            associations.append(
                (
                    row["referencedComponentId"],
                    row["targetComponentId"],
                    ASSOCIATION_REFSET_IDS.get(row["refsetId"], row["refsetId"]),
                    row["effectiveTime"],
                    row["refsetId"],
                )
            )
    if reconstruct_latest:
        for row in association_rows.values():
            if row["active"] != "1":
                continue
            associations.append(
                (
                    row["referencedComponentId"],
                    row["targetComponentId"],
                    ASSOCIATION_REFSET_IDS.get(row["refsetId"], row["refsetId"]),
                    row["effectiveTime"],
                    row["refsetId"],
                )
            )
    return associations


def _read_is_a_relationship_rows(
    zf: zipfile.ZipFile,
    member: Optional[str],
    *,
    policy_date: Optional[str] = None,
    reconstruct_latest: bool = False,
) -> list[tuple[str, str, bool, str]]:
    """Read current is-a relationship rows, preserving active state."""
    if member is None:
        return []
    relationships = []
    relationship_rows: dict[str, dict[str, str]] = {}
    for row in _iter_rf2_rows(
        zf,
        member,
        {
            "id",
            "effectiveTime",
            "active",
            "moduleId",
            "sourceId",
            "destinationId",
            "relationshipGroup",
            "typeId",
            "characteristicTypeId",
            "modifierId",
        },
    ):
        if row["typeId"] != IS_A_TYPE_ID or not _at_or_before(row, policy_date):
            continue
        if reconstruct_latest:
            previous = relationship_rows.get(row["id"])
            if previous is None or row["effectiveTime"] >= previous["effectiveTime"]:
                relationship_rows[row["id"]] = row
        else:
            relationships.append(
                (
                    row["sourceId"],
                    row["destinationId"],
                    row["active"] == "1",
                    row["effectiveTime"],
                )
            )
    if reconstruct_latest:
        for row in relationship_rows.values():
            relationships.append(
                (
                    row["sourceId"],
                    row["destinationId"],
                    row["active"] == "1",
                    row["effectiveTime"],
                )
            )
    return relationships


def _read_active_parent_map(
    zf: zipfile.ZipFile,
    member: Optional[str],
    active_concepts: set[str],
    *,
    policy_date: Optional[str] = None,
    reconstruct_latest: bool = False,
) -> dict[str, set[str]]:
    if member is None:
        return {}
    parent_map: dict[str, set[str]] = {}
    relationship_rows: dict[str, dict[str, str]] = {}
    for row in _iter_rf2_rows(
        zf,
        member,
        {
            "id",
            "effectiveTime",
            "active",
            "moduleId",
            "sourceId",
            "destinationId",
            "relationshipGroup",
            "typeId",
            "characteristicTypeId",
            "modifierId",
        },
    ):
        if not _at_or_before(row, policy_date):
            continue
        if reconstruct_latest:
            previous = relationship_rows.get(row["id"])
            if previous is None or row["effectiveTime"] >= previous["effectiveTime"]:
                relationship_rows[row["id"]] = row
        elif row["active"] == "1" and row["typeId"] == IS_A_TYPE_ID:
            if row["sourceId"] in active_concepts and row["destinationId"] in active_concepts:
                parent_map.setdefault(row["sourceId"], set()).add(row["destinationId"])
    if reconstruct_latest:
        for row in relationship_rows.values():
            if row["active"] != "1" or row["typeId"] != IS_A_TYPE_ID:
                continue
            if row["sourceId"] in active_concepts and row["destinationId"] in active_concepts:
                parent_map.setdefault(row["sourceId"], set()).add(row["destinationId"])
    return parent_map
