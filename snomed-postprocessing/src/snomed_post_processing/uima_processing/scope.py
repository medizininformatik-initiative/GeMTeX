"""Shared, case-insensitive annotator scope. An empty selection means all."""
from __future__ import annotations

from typing import Iterable


def normalize_annotators(names: Iterable[str] | None = ()) -> tuple[str, ...]:
    return tuple(sorted({str(name).strip().lower() for name in names or () if str(name).strip()}))


def annotator_in_scope(name: str, annotators: Iterable[str] = ()) -> bool:
    return not annotators or str(name).lower() in annotators


def scope_covers(produced_for: Iterable[str], requested: Iterable[str]) -> bool:
    produced, requested = normalize_annotators(produced_for), normalize_annotators(requested)
    return not produced or bool(requested) and set(requested).issubset(produced)
