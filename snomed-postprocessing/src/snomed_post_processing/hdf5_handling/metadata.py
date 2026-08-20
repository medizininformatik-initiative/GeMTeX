"""Concise metadata summaries for SNOMED postprocessing HDF5 files."""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Any, Optional, Union

import h5py
import numpy as np

from .policy import decode_array


@dataclasses.dataclass(frozen=True)
class BlacklistRuleMetadata:
    raw: str
    kind: str


@dataclasses.dataclass(frozen=True)
class BlacklistMetadata:
    view_name: str
    source_name: Optional[str]
    format_version: Optional[str]
    rules: tuple[BlacklistRuleMetadata, ...]


@dataclasses.dataclass(frozen=True)
class Hdf5MetadataSummary:
    path: pathlib.Path
    has_concepts: bool
    concept_count: Optional[int] = None
    active_concept_count: Optional[int] = None
    semantic_tag_count: Optional[int] = None
    concepts_policy_date: Optional[str] = None
    concepts_release_date: Optional[str] = None
    concepts_rf2_view: Optional[str] = None
    has_ancestors: bool = False
    has_depth_to_root: bool = False
    known_max_depth_to_root: Optional[int] = None
    has_historical_associations: bool = False
    historical_association_count: Optional[int] = None
    has_historical_is_a: bool = False
    historical_is_a_count: Optional[int] = None
    historical_association_type_counts: tuple[tuple[str, int], ...] = ()
    policy_view_counts: tuple[tuple[str, str, int], ...] = ()
    legacy_group_counts: tuple[tuple[str, str, int], ...] = ()
    blacklist_metadata: tuple[BlacklistMetadata, ...] = ()

    @property
    def sanitization_ready(self) -> bool:
        return (
            self.has_concepts
            and self.concept_count is not None
            and self.active_concept_count is not None
            and self.has_historical_associations
            and self.historical_association_count is not None
            and any(policy == "whitelist" for policy, _, _ in self.policy_view_counts)
            and any(policy == "blacklist" for policy, _, _ in self.policy_view_counts)
        )


def inspect_hdf5_metadata(path: Union[str, pathlib.Path]) -> Hdf5MetadataSummary:
    path = pathlib.Path(path)
    with h5py.File(path, "r") as h5_file:
        has_concepts = "concepts" in h5_file
        concept_count = None
        active_concept_count = None
        semantic_tag_count = None
        concepts_policy_date = None
        concepts_release_date = None
        concepts_rf2_view = None
        has_ancestors = False
        has_depth_to_root = False
        known_max_depth_to_root = None

        if has_concepts:
            concepts = h5_file["concepts"]
            if "codes" in concepts:
                concept_count = int(concepts["codes"].shape[0])
            if "active" in concepts:
                active_concept_count = int(np.count_nonzero(concepts["active"][:]))
            if "semantic_tags" in concepts:
                semantic_tag_count = int(concepts["semantic_tags"].shape[0])
            concepts_policy_date = _attr(concepts, "policy_date")
            concepts_release_date = _attr(concepts, "release_date")
            concepts_rf2_view = _attr(concepts, "rf2_view")
            has_ancestors = all(
                name in concepts
                for name in ("ancestors_index", "ancestor_concept_index", "ancestor_distance")
            )
            has_depth_to_root = all(
                name in concepts for name in ("min_depth_to_root", "max_depth_to_root")
            )
            known_max_depth_to_root = None
            if has_depth_to_root:
                max_depths = np.asarray(concepts["max_depth_to_root"][:], dtype=np.int64)
                known_depths = max_depths[max_depths >= 0]
                if known_depths.size:
                    known_max_depth_to_root = int(np.max(known_depths))

        policy_view_counts = []
        if "policy_views" in h5_file:
            policy_views = h5_file["policy_views"]
            for policy in sorted(policy_views.keys()):
                for view_name in sorted(policy_views[policy].keys()):
                    view = policy_views[policy][view_name]
                    if "concept_index" in view:
                        policy_view_counts.append(
                            (policy, view_name, int(view["concept_index"].shape[0]))
                        )

        legacy_group_counts = []
        for policy in ("whitelist", "blacklist"):
            if policy in h5_file:
                group = h5_file[policy]
                for view_name in sorted(group.keys()):
                    view = group[view_name]
                    if "codes" in view:
                        legacy_group_counts.append(
                            (policy, view_name, int(view["codes"].shape[0]))
                        )

        has_historical_associations = "historical_associations" in h5_file
        historical_association_count = None
        historical_association_type_counts = []
        if has_historical_associations:
            hist = h5_file["historical_associations"]
            if "source_index" in hist:
                historical_association_count = int(hist["source_index"].shape[0])
            if "association_types" in hist and "association_type_id" in hist:
                association_types = decode_array(hist["association_types"][:])
                type_ids = hist["association_type_id"][:]
                counts = np.bincount(type_ids.astype(np.int64), minlength=len(association_types))
                historical_association_type_counts = tuple(
                    (association_type, int(counts[idx]))
                    for idx, association_type in enumerate(association_types)
                    if int(counts[idx]) > 0
                )

        blacklist_metadata = []
        if "metadata" in h5_file and "blacklists" in h5_file["metadata"]:
            blacklists_group = h5_file["metadata/blacklists"]
            for view_name in sorted(blacklists_group.keys()):
                view = blacklists_group[view_name]
                raw_rules = decode_array(view["rules_raw"][:]) if "rules_raw" in view else []
                rule_kinds = decode_array(view["rules_kind"][:]) if "rules_kind" in view else []
                if len(rule_kinds) < len(raw_rules):
                    rule_kinds = [*rule_kinds, *("unknown" for _ in range(len(raw_rules) - len(rule_kinds)))]
                blacklist_metadata.append(
                    BlacklistMetadata(
                        view_name=view_name,
                        source_name=_attr(view, "source_name"),
                        format_version=_attr(view, "format_version"),
                        rules=tuple(
                            BlacklistRuleMetadata(raw=raw, kind=kind)
                            for raw, kind in zip(raw_rules, rule_kinds)
                        ),
                    )
                )

        has_historical_is_a = "historical_is_a" in h5_file
        historical_is_a_count = None
        if has_historical_is_a:
            historical_is_a_group = h5_file["historical_is_a"]
            if "source_index" in historical_is_a_group:
                historical_is_a_count = int(historical_is_a_group["source_index"].shape[0])

    return Hdf5MetadataSummary(
        path=path,
        has_concepts=has_concepts,
        concept_count=concept_count,
        active_concept_count=active_concept_count,
        semantic_tag_count=semantic_tag_count,
        concepts_policy_date=concepts_policy_date,
        concepts_release_date=concepts_release_date,
        concepts_rf2_view=concepts_rf2_view,
        has_ancestors=has_ancestors,
        has_depth_to_root=has_depth_to_root,
        known_max_depth_to_root=known_max_depth_to_root,
        has_historical_associations=has_historical_associations,
        historical_association_count=historical_association_count,
        has_historical_is_a=has_historical_is_a,
        historical_is_a_count=historical_is_a_count,
        historical_association_type_counts=historical_association_type_counts,
        policy_view_counts=tuple(policy_view_counts),
        legacy_group_counts=tuple(legacy_group_counts),
        blacklist_metadata=tuple(blacklist_metadata),
    )


def format_hdf5_metadata_summary(
    summary: Hdf5MetadataSummary,
    *,
    markdown: bool = False,
    include_path: bool = True,
) -> str:
    lines = []
    if markdown:
        lines.append("### HDF5 metadata summary")
    else:
        lines.append("HDF5 metadata summary")
    if include_path:
        lines.append(f"- File: `{summary.path}`" if markdown else f"- File: {summary.path}")
    lines.extend(
        [
            f"- Sanitization-ready: {_yes_no(summary.sanitization_ready)}",
            f"- Concepts: {_count(summary.concept_count)}"
            + (
                f" ({summary.active_concept_count:,} active at policy date)"
                if summary.active_concept_count is not None
                else ""
            ),
            f"- Release date: {summary.concepts_release_date or 'unknown'}",
            f"- Policy date: {summary.concepts_policy_date or 'unknown'}",
            f"- RF2 view: {summary.concepts_rf2_view or 'unknown'}",
            f"- Semantic tags: {_count(summary.semantic_tag_count)}",
            f"- Ancestor data: {_yes_no(summary.has_ancestors)}",
            f"- Depth-to-root data: {_yes_no(summary.has_depth_to_root)}"
            + (
                f" (max known depth {summary.known_max_depth_to_root})"
                if summary.known_max_depth_to_root is not None
                else ""
            ),
            f"- Historical associations: {_count(summary.historical_association_count) if summary.has_historical_associations else 'missing'}",
            f"- Historical is-a fallback edges: {_count(summary.historical_is_a_count) if summary.has_historical_is_a else 'missing'}",
        ]
    )
    if summary.historical_association_type_counts:
        lines.append("- Historical association types:")
        for association_type, count in summary.historical_association_type_counts:
            lines.append(f"  - {association_type}: {count:,}")
    if summary.policy_view_counts:
        lines.append("- Compact policy views:")
        for policy, view_name, count in summary.policy_view_counts:
            lines.append(f"  - {policy}/{view_name}: {count:,} concepts")
    else:
        lines.append("- Compact policy views: missing")
    if summary.legacy_group_counts:
        lines.append("- Legacy groups:")
        for policy, view_name, count in summary.legacy_group_counts:
            lines.append(f"  - {policy}/{view_name}: {count:,} concepts")
    if summary.blacklist_metadata:
        lines.append("- Blacklist rule metadata:")
        for metadata in summary.blacklist_metadata:
            source = f", source: {metadata.source_name}" if metadata.source_name else ""
            lines.append(
                f"  - blacklists/{metadata.view_name}: {len(metadata.rules):,} rule(s){source}"
            )
            for rule in metadata.rules[:10]:
                lines.append(f"    - {_format_blacklist_rule_kind(rule.kind)}: {rule.raw}")
            if len(metadata.rules) > 10:
                lines.append(f"    - ... {len(metadata.rules) - 10:,} more rule(s)")
    return "\n".join(lines) + "\n"


def _format_blacklist_rule_kind(kind: str) -> str:
    if kind == "fsn_tag":
        return "FSN tag"
    if kind == "concept_descendants":
        return "Concept + descendants"
    return kind or "unknown"


def _attr(group: h5py.Group, name: str) -> Optional[str]:
    if name not in group.attrs:
        return None
    value: Any = group.attrs[name]
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8")
    return str(value)


def _count(value: Optional[int]) -> str:
    return "missing" if value is None else f"{value:,}"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
