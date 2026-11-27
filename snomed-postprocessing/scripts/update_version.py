#!/usr/bin/env python3
"""Update the project version in release-related files."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = r"[0-9A-Za-z][0-9A-Za-z.+_-]*"
TARGETS = {
    "log-inception-docs.sh": re.compile(rf'(?m)^(?P<prefix>CURRENT_VERSION=")(?P<version>{VERSION})(?P<suffix>"\r?)$'),
    "start-gui.sh": re.compile(rf'(?m)^(?P<prefix>CURRENT_VERSION=")(?P<version>{VERSION})(?P<suffix>"\r?)$'),
    "README.md": re.compile(
        rf'(?P<prefix>ghcr\.io/medizininformatik-initiative/gemtex/snomed-postprocessing:)(?P<version>{VERSION})'
    ),
    "pyproject.toml": re.compile(rf'(?m)^(?P<prefix>version = ")(?P<version>{VERSION})(?P<suffix>"\r?)$'),
    "uv.lock": re.compile(
        rf'(?m)(?P<prefix>^name = "snomed-post-processing"\r?\nversion = ")(?P<version>{VERSION})(?P<suffix>"\r?)$'
    ),
}


def update_versions(old: str, new: str) -> None:
    loaded: dict[Path, tuple[str, re.Pattern[str], list[re.Match[str]]]] = {}
    errors = []

    for relative, pattern in TARGETS.items():
        path = ROOT / relative
        text = path.read_bytes().decode("utf-8")
        matches = list(pattern.finditer(text))
        if not matches:
            errors.append(f"{relative}: version location not found")
        else:
            versions = sorted({match.group("version") for match in matches})
            unexpected = [version for version in versions if version not in {old, new}]
            if unexpected:
                errors.append(f"{relative}: expected {old} or {new}, found {', '.join(unexpected)}")
        loaded[path] = text, pattern, matches

    if errors:
        raise SystemExit("Version update aborted:\n- " + "\n- ".join(errors))

    for path, (text, pattern, matches) in loaded.items():
        changed = sum(match.group("version") == old for match in matches)
        updated = pattern.sub(
            lambda match: match.group("prefix")
            + (new if match.group("version") == old else match.group("version"))
            + match.groupdict().get("suffix", ""),
            text,
        )
        if changed:
            path.write_bytes(updated.encode("utf-8"))
            print(f"Updated {path.relative_to(ROOT)} ({changed} occurrence{'s' if changed != 1 else ''})")
        else:
            print(f"Already current: {path.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update the SNOMED Postprocessing project version.")
    parser.add_argument("old_version")
    parser.add_argument("new_version")
    args = parser.parse_args()
    if args.old_version == args.new_version:
        parser.error("old_version and new_version must differ")
    update_versions(args.old_version, args.new_version)


if __name__ == "__main__":
    main()
