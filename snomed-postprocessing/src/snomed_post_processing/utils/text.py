"""Small text and JSON formatting helpers."""

from __future__ import annotations

import json
import re


def flexible_whitespace_pattern(s: str) -> str:
    """Build a regex pattern where any whitespace sequence matches ``\\s+``."""
    escaped_parts = []
    i = 0
    while i < len(s):
        if s[i].isspace():
            while i < len(s) and s[i].isspace():
                i += 1
            escaped_parts.append(r"\s+")
        else:
            char = s[i]
            if char in r".^$*+?{}[]\|()":
                escaped_parts.append(re.escape(char))
            else:
                escaped_parts.append(char)
            i += 1
    return "".join(escaped_parts)


# Backwards-compatible private helper name.
_flexible_whitespace_pattern = flexible_whitespace_pattern


def pprint_json(json_data):
    print(json.dumps(json_data, indent=2))


def is_numeric(text: str) -> bool:
    """Check if the provided text is numeric (integer or decimal)."""
    return bool(re.fullmatch(r"(\d+([.,]\d+)?)", text.strip()))
