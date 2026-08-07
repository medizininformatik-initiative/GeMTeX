"""SNOMED CT release ingestion utilities.

This package reads SNOMED CT RF2 release ZIPs directly without extracting them
and writes enriched HDF5 policy files used by postprocessing and sanitization.
"""

from __future__ import annotations

from .constants import ASSOCIATION_REFSET_IDS, CSV_FIELD_SIZE_LIMIT, FSN_TYPE_ID, IS_A_TYPE_ID
from .discovery import (
    discover_full_members,
    discover_release_members,
    discover_snapshot_members,
)
from .hdf5_writer import (
    _categorical_ids,
    _descendants_or_self,
    _replace_group,
    _write_int_dataset,
    _write_legacy_policy_group,
    _write_policy_view,
    _write_string_dataset,
    write_snapshot_hdf5_from_rf2_zip,
)
from .models import Rf2IngestionSummary, Rf2ReleaseMembers, Rf2SnapshotMembers
from .readers import (
    _iter_rf2_rows,
    _read_active_associations,
    _read_active_parent_map,
    _read_concept_active_state,
    _read_fsns,
    _semantic_tag_from_fsn,
)

__all__ = [
    "Rf2ReleaseMembers",
    "Rf2SnapshotMembers",
    "Rf2IngestionSummary",
    "ASSOCIATION_REFSET_IDS",
    "CSV_FIELD_SIZE_LIMIT",
    "FSN_TYPE_ID",
    "IS_A_TYPE_ID",
    "discover_release_members",
    "discover_snapshot_members",
    "discover_full_members",
    "write_snapshot_hdf5_from_rf2_zip",
    # Backwards-compatible private helpers used by older tests/callers.
    "_iter_rf2_rows",
    "_read_concept_active_state",
    "_read_fsns",
    "_read_active_associations",
    "_read_active_parent_map",
    "_semantic_tag_from_fsn",
    "_write_string_dataset",
    "_write_int_dataset",
    "_descendants_or_self",
    "_categorical_ids",
    "_write_legacy_policy_group",
    "_write_policy_view",
    "_replace_group",
]
