#!/usr/bin/env python3
"""Find example whitelist findings for sanitization fallback paths.

The script scans a compact SNOMED post-processing HDF5 file and prints examples
of source codes that would be reported as whitelist findings and can be resolved
by different sanitization mechanisms:

1. Historical association replacements, grouped by association type.
2. Ancestor fallback replacements.
3. Semantic BM25 fallback replacements after historical/ancestor fallback fails.

It is intended as an exploratory test-data helper, not as a strict unit test.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import defaultdict
from typing import Any

import h5py

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from snomed_post_processing.hdf5_handling.policy import (  # noqa: E402
    read_concepts,
    read_historical_associations,
    read_policy_indices,
)
from snomed_post_processing.sanitization.models import (  # noqa: E402
    DEFAULT_ALLOWED_ASSOCIATION_TYPES,
    SUPPORTED_ASSOCIATION_TYPES,
    SanitizationStatus,
)
from snomed_post_processing.sanitization.resolver import SanitizationResolver  # noqa: E402
from snomed_post_processing.sanitization.semantic_bm25 import SemanticBm25Resolver  # noqa: E402
from snomed_post_processing.uima_processing import CriticalFinding  # noqa: E402

DEFAULT_HDF5 = ROOT / "data" / "gemtex_snomedct_codes_release20260401_policy20240401.hdf5"


def make_finding(code: str, fsn: str | None) -> CriticalFinding:
    return CriticalFinding(
        annotator="example-search",
        document="synthetic",
        code=code,
        covered_text=covered_text_from_fsn(fsn) or code,
        offset=(0, len(covered_text_from_fsn(fsn) or code)),
        list_type="whitelist",
        reason="synthetic whitelist finding for sanitization fallback example search",
        fsn=fsn,
    )


def covered_text_from_fsn(fsn: str | None) -> str:
    if not fsn:
        return ""
    # Remove a trailing semantic tag to get annotation-like text for BM25.
    if " (" in fsn and fsn.endswith(")"):
        return fsn.rsplit(" (", 1)[0]
    return fsn


def suggestion_to_dict(source_code: str, source_fsn: str | None, suggestion: Any) -> dict[str, Any]:
    return {
        "source_code": source_code,
        "source_fsn": source_fsn,
        "status": str(suggestion.status.value if hasattr(suggestion.status, "value") else suggestion.status),
        "replacement_code": suggestion.replacement_code,
        "replacement_fsn": suggestion.replacement_fsn,
        "association_type": suggestion.association_type,
        "reason": suggestion.reason,
        "candidate_count": suggestion.candidate_count,
    }


def load_basics(hdf5_path: pathlib.Path):
    with h5py.File(hdf5_path, "r") as h5_file:
        concepts = read_concepts(h5_file)
        whitelist = read_policy_indices(h5_file, "whitelist")
        blacklist = read_policy_indices(h5_file, "blacklist")
        associations = read_historical_associations(h5_file)
    return concepts, whitelist, blacklist, associations


def find_historical_examples(
    hdf5_path: pathlib.Path,
    per_type: int,
    include_association_types: tuple[str, ...],
) -> dict[str, list[dict[str, Any]]]:
    concepts, whitelist, blacklist, associations = load_basics(hdf5_path)
    examples: dict[str, list[dict[str, Any]]] = {name: [] for name in include_association_types}
    seen_sources_by_type: dict[str, set[int]] = defaultdict(set)

    resolver_by_type: dict[str, SanitizationResolver] = {}
    for row_idx, source_idx in enumerate(associations.source_index):
        association_type = associations.association_types[int(associations.association_type_id[row_idx])]
        if association_type not in examples or len(examples[association_type]) >= per_type:
            continue
        if not bool(associations.active[row_idx]):
            continue

        source_idx = int(source_idx)
        target_idx = int(associations.target_index[row_idx])
        if source_idx in seen_sources_by_type[association_type]:
            continue
        if source_idx in whitelist or source_idx in blacklist:
            continue
        if not (0 <= target_idx < len(concepts.codes)):
            continue
        if not (
            bool(concepts.active[target_idx])
            and target_idx in whitelist
            and target_idx not in blacklist
        ):
            continue

        resolver = resolver_by_type.get(association_type)
        if resolver is None:
            resolver = SanitizationResolver(hdf5_path, allowed_association_types=(association_type,))
            resolver_by_type[association_type] = resolver
        source_code = concepts.codes[source_idx]
        source_fsn = concepts.fsn[source_idx]
        suggestion = resolver.suggest(make_finding(source_code, source_fsn))
        if suggestion.status == SanitizationStatus.HISTORICAL_ASSOCIATION_REPLACEMENT:
            examples[association_type].append(suggestion_to_dict(source_code, source_fsn, suggestion))
            seen_sources_by_type[association_type].add(source_idx)

        if all(len(items) >= per_type for items in examples.values()):
            break

    return {key: value for key, value in examples.items() if value}


def find_ancestor_examples(
    hdf5_path: pathlib.Path,
    count: int,
    ancestor_max_distance: int,
) -> list[dict[str, Any]]:
    concepts, whitelist, blacklist, _associations = load_basics(hdf5_path)
    resolver = SanitizationResolver(
        hdf5_path,
        allowed_association_types=DEFAULT_ALLOWED_ASSOCIATION_TYPES,
        activate_historical_ancestor_fallback=True,
        ancestor_max_distance=ancestor_max_distance,
    )
    examples = []
    for source_idx, source_code in enumerate(concepts.codes):
        if source_idx in whitelist or source_idx in blacklist:
            continue
        source_fsn = concepts.fsn[source_idx]
        suggestion = resolver.suggest(make_finding(source_code, source_fsn))
        if suggestion.status in {
            SanitizationStatus.NEAREST_TARGET_ANCESTOR,
            SanitizationStatus.NEAREST_HISTORICAL_ANCESTOR,
        }:
            examples.append(suggestion_to_dict(source_code, source_fsn, suggestion))
            if len(examples) >= count:
                break
    return examples


def find_bm25_examples(
    hdf5_path: pathlib.Path,
    count: int,
    ancestor_max_distance: int,
    max_scan: int,
) -> list[dict[str, Any]]:
    concepts, whitelist, blacklist, _associations = load_basics(hdf5_path)
    structured_resolver = SanitizationResolver(
        hdf5_path,
        allowed_association_types=DEFAULT_ALLOWED_ASSOCIATION_TYPES,
        activate_historical_ancestor_fallback=True,
        ancestor_max_distance=ancestor_max_distance,
    )
    bm25_resolver = SemanticBm25Resolver(hdf5_path)

    examples = []
    scanned = 0
    for source_idx, source_code in enumerate(concepts.codes):
        if scanned >= max_scan:
            break
        if source_idx in whitelist or source_idx in blacklist or not concepts.fsn[source_idx]:
            continue
        scanned += 1
        source_fsn = concepts.fsn[source_idx]
        finding = make_finding(source_code, source_fsn)
        structured_suggestion = structured_resolver.suggest(finding)
        if structured_suggestion.replacement_code is not None:
            continue
        bm25_suggestion = bm25_resolver.suggest(finding)
        if bm25_suggestion.status == SanitizationStatus.SEMANTIC_BM25_REPLACEMENT:
            example = suggestion_to_dict(source_code, source_fsn, bm25_suggestion)
            example["structured_status_before_bm25"] = structured_suggestion.status.value
            example["bm25_score"] = bm25_suggestion.score
            examples.append(example)
            if len(examples) >= count:
                break
    return examples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hdf5", type=pathlib.Path, default=DEFAULT_HDF5)
    parser.add_argument("--per-historical-type", type=int, default=2)
    parser.add_argument("--ancestor-count", type=int, default=2)
    parser.add_argument("--bm25-count", type=int, default=2)
    parser.add_argument("--ancestor-max-distance", type=int, default=3)
    parser.add_argument(
        "--association-type",
        action="append",
        dest="association_types",
        help=(
            "Association type to sample. Can be passed repeatedly. "
            "Defaults to all supported named types, prioritising SAME_AS and REPLACED_BY."
        ),
    )
    parser.add_argument(
        "--max-bm25-scan",
        type=int,
        default=20_000,
        help="Maximum non-whitelisted, non-blacklisted concepts to try for BM25 examples.",
    )
    parser.add_argument("--json-output", type=pathlib.Path)
    args = parser.parse_args()

    hdf5_path = args.hdf5.resolve()
    if not hdf5_path.exists():
        parser.error(f"HDF5 file does not exist: {hdf5_path}")

    if args.association_types:
        association_types = tuple(dict.fromkeys(args.association_types))
    else:
        preferred = ("SAME_AS", "REPLACED_BY")
        association_types = preferred + tuple(
            name for name in SUPPORTED_ASSOCIATION_TYPES if name not in preferred
        )

    result = {
        "hdf5": str(hdf5_path),
        "historical_association_examples": find_historical_examples(
            hdf5_path,
            per_type=args.per_historical_type,
            include_association_types=association_types,
        ),
        "ancestor_fallback_examples": find_ancestor_examples(
            hdf5_path,
            count=args.ancestor_count,
            ancestor_max_distance=args.ancestor_max_distance,
        ),
        "bm25_fallback_examples": find_bm25_examples(
            hdf5_path,
            count=args.bm25_count,
            ancestor_max_distance=args.ancestor_max_distance,
            max_scan=args.max_bm25_scan,
        ),
    }

    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.json_output:
        args.json_output.write_text(text + "\n", encoding="utf-8")
        print(f"\nWrote {args.json_output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
