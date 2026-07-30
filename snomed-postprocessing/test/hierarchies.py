"""Reusable local hierarchy fixtures for tests.

The fixture mirrors important SNOMED CT hierarchy properties without requiring
network access or a Snowstorm instance:

- directed acyclic is-a graph;
- at least five levels of ancestry;
- multiple inheritance for several concepts;
- one disconnected concept.
"""

from __future__ import annotations

import json
import pathlib


FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"
SNOMED_LIKE_HIERARCHY_PATH = FIXTURE_DIR / "snomed_like_hierarchy.json"


def load_snomed_like_hierarchy() -> tuple[dict[str, str], dict[str, set[str]]]:
    data = json.loads(SNOMED_LIKE_HIERARCHY_PATH.read_text(encoding="utf-8"))
    id_to_fsn = dict(data["codes"])
    parent_map = {
        child: set(parents) for child, parents in data.get("parents", {}).items()
    }
    return id_to_fsn, parent_map
