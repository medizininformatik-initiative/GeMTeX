"""Text helpers for semantic BM25 sanitization."""

from __future__ import annotations

import re
from typing import Optional

from ..uima_processing import CriticalFinding

_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
_SEMANTIC_TAG_RE = re.compile(r"\(([^()]*)\)\s*$")
_FSN_POSTFIX_SEPARATOR_RE = re.compile(r"\s+-\s+")
FSN_POSTFIX_PRESETS = ("action", "unit of product usage", "dosing instruction fragment", "dosing instruction imperative")


def normalize_fsn_postfixes(values) -> tuple[str, ...]:
    if isinstance(values, str) or not isinstance(values, (list, tuple, set, frozenset)):
        raise ValueError("FSN postfixes must be a list of nonempty literal strings.")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("FSN postfixes must be nonempty literal strings.")
    return tuple(sorted({value.strip().casefold() for value in values}))


def _fsn_text(fsn: Optional[str], excluded_fsn_postfixes=()) -> str:
    """Clean known FSN matching text without changing clinical text or full FSNs."""
    text = _SEMANTIC_TAG_RE.sub("", fsn or "").rstrip()
    if excluded_fsn_postfixes:
        separators = list(_FSN_POSTFIX_SEPARATOR_RE.finditer(text))
        if separators:
            last = separators[-1]
            postfix = text[last.end():].strip().casefold()
            if text[:last.start()].strip() and any(postfix == value.strip().casefold() for value in excluded_fsn_postfixes):
                return text[:last.start()].rstrip()
    return text


def _query_text(finding: CriticalFinding, source_fsn: Optional[str] = None, excluded_fsn_postfixes=()) -> str:
    return " ".join(
        part for part in (finding.covered_text, _fsn_text(source_fsn, excluded_fsn_postfixes)) if part
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
