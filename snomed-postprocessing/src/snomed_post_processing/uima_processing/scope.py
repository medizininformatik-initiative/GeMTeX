"""Shared, case-insensitive annotator scope. An empty selection means all."""
from __future__ import annotations

from typing import Iterable


def normalize_annotators(names: Iterable[str] | None = ()) -> tuple[str, ...]:
    return tuple(sorted({str(name).strip().lower() for name in names or () if str(name).strip()}))


def annotator_in_scope(name: str, annotators: Iterable[str] = ()) -> bool:
    return not annotators or str(name).lower() in annotators


def resolve_annotator_scope(
    available: Iterable[str], included: Iterable[str] = (), excluded: Iterable[str] = ()
) -> tuple[str, ...]:
    """Resolve a UI/CLI filter; a non-empty exclusion list takes precedence."""
    included, excluded = normalize_annotators(included), normalize_annotators(excluded)
    if not excluded:
        return included
    available = normalize_annotators(available)
    unknown = sorted(set(excluded) - set(available))
    if unknown:
        raise ValueError(f"Unknown excluded annotator(s): {', '.join(unknown)}")
    selected = tuple(name for name in available if name not in excluded)
    if not selected:
        raise ValueError("The exclusion list removes all available annotators.")
    return selected


def scope_covers(produced_for: Iterable[str], requested: Iterable[str]) -> bool:
    produced, requested = normalize_annotators(produced_for), normalize_annotators(requested)
    return not produced or bool(requested) and set(requested).issubset(produced)
