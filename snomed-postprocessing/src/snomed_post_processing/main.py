"""Backward-compatible CLI entrypoint module.

Command implementations live in :mod:`snomed_post_processing.cli.app`.
"""

from __future__ import annotations

from .cli.app import (  # noqa: F401
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
    "suggest_sanitization_cli",
    "list_branches",
    "help_me",
]


if __name__ == "__main__":
    help_me(["--help"])
