"""Text helpers for semantic BM25 sanitization."""

from __future__ import annotations

import re
from typing import Optional

from ..uima_processing import CriticalFinding

_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
_SEMANTIC_TAG_RE = re.compile(r"\(([^()]*)\)\s*$")


def _query_text(finding: CriticalFinding, source_fsn: Optional[str] = None) -> str:
    return " ".join(
        part for part in (finding.covered_text, source_fsn or "") if part
    )


def _tokenize(text: Optional[str]) -> list[str]:
    if not text:
        return []
    return [token.lower() for token in _TOKEN_RE.findall(text) if len(token) > 1]


def _semantic_tag(fsn: Optional[str]) -> Optional[str]:
    if not fsn:
        return None
    match = _SEMANTIC_TAG_RE.search(fsn)
    return match.group(1).lower() if match else None
