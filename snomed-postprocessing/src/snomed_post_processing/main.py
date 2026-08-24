"""Compatibility entrypoint for legacy console-script imports.

The Click command implementations live in :mod:`snomed_post_processing.cli.app`.
This module intentionally re-exports them so older references such as
``snomed_post_processing.main:log_documents`` continue to work.
"""

from __future__ import annotations

from .cli.app import (  # noqa: F401
    build_snogit_cache_cli,
    create_concept_id_dump,
    help_me,
    list_branches,
    log_documents,
    suggest_sanitization_cli,
    summarize_hdf5,
)

__all__ = [
    "log_documents",
    "create_concept_id_dump",
    "summarize_hdf5",
    "build_snogit_cache_cli",
    "suggest_sanitization_cli",
    "list_branches",
    "help_me",
]


if __name__ == "__main__":
    help_me(["--help"])
