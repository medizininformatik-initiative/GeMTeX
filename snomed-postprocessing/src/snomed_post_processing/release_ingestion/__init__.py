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
from .hdf5_writer import write_snapshot_hdf5_from_rf2_zip
from .models import Rf2IngestionSummary, Rf2ReleaseMembers, Rf2SnapshotMembers

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
]
