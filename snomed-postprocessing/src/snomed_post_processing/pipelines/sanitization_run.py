"""Sanitization-run pipeline for applying suggestions to UIMA/CAS files.

This module intentionally starts as a skeleton. The sanitization-check pipeline
produces suggestion reports; this future pipeline will apply reviewed
sanitization decisions to exported INCEpTION/UIMA CAS files.
"""

from __future__ import annotations

import pathlib
from typing import Optional


class SanitizationRunNotImplementedError(NotImplementedError):
    """Raised when the not-yet-implemented sanitization run pipeline is invoked."""


def run_sanitization(
    input_project: pathlib.Path,
    suggestions_path: pathlib.Path,
    output_project: pathlib.Path,
    *,
    dry_run: bool = True,
    annotator_filter: Optional[set[str]] = None,
):
    """Apply reviewed sanitization suggestions to UIMA/CAS files.

    Planned behavior:
    - read a project ZIP or extracted project directory from ``input_project``
    - read reviewed sanitization suggestions from ``suggestions_path``
    - update matching UIMA/CAS annotations safely
    - write the sanitized project to ``output_project``
    - support ``dry_run`` reporting before modifying/writing CAS content

    This is a placeholder until CAS mutation semantics and reviewed suggestion
    input format are finalized.
    """
    raise SanitizationRunNotImplementedError(
        "Sanitization run is not implemented yet. Use the sanitization-check pipeline to generate suggestion reports first."
    )
