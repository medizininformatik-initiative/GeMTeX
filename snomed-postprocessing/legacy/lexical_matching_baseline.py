"""
Lexical grounding baseline for German clinical entity spans.

Design:
  1. Search exact lexical matches in SNOMED German descriptions.
  2. Search exact lexical matches in SNOGIT German interface terms.
  3. Additionally search approximate lexical matches with bounded Levenshtein
     distance after the same deterministic normalization.
  4. Resolve SNOGIT concept IDs back to SNOMED concept metadata:
       - FSN terms
       - SNOMED descriptions
       - description activeness
       - concept activeness if a SNOMED Concept file is provided

Usage:
  python lexical_grounding_baseline.py --config configs/lexical_grounding.yaml
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

# Import rapidfuzz for lightning-fast C++ backed string matching
from rapidfuzz import process, distance


SNOMED_DESCRIPTION_TYPE_IDS = {
    "900000000000003001": "fully_specified_name",
    "900000000000013009": "synonym",
    "900000000000550004": "definition",
}


DEFAULT_CONFIG: Dict[str, Any] = {
    "input_path": None,
    "output_path": None,
    "stats_output_path": None,
    "io": {
        "input_glob": "**/*.json*",
        "output_suffix": ".grounded.jsonl",
    },
    "snomed": {
        "description_path": None,
        "concept_path": None,
        "delimiter": "\t",
        "has_header": True,
        "description_columns": {
            "description_id": "id",
            "concept_id": "conceptId",
            "term": "term",
            "type_id": "typeId",
            "language_code": "languageCode",
            "active": "active",
        },
        "concept_columns": {
            "concept_id": "id",
            "active": "active",
        },
        "active_value": "1",
        "language_values": ["de"],
        "keep_inactive_descriptions": False,
        "keep_inactive_concepts": True,
    },
    "snogit": {
        "path": None,
        "delimiter": "\t",
        "has_header": False,
        "manual_header": [
            "concept_id",
            "term_id",
            "english_term",
            "german_term",
        ],
        "columns": {
            "concept_id": "concept_id",
            "term_id": "term_id",
            "german_term": "german_term",
            "english_term": "english_term",
        },
    },
    "matching": {
        "normalization": {
            "unicode_nfkc": True,
            "casefold": True,
            "punctuation_to_space": True,
            "symbols_to_space": True,
            "collapse_whitespace": True,
            "strip": True,
        },
        "levenshtein": {
            "enabled": True,
            "max_distance": 5,
            "relative_distance": 0.3,
        },
    },
}


@dataclass(frozen=True)
class Config:
    input_path: Path
    output_path: Path
    stats_output_path: Path

    input_glob: str
    output_suffix: str

    snomed_description_path: Path
    snomed_concept_path: Optional[Path]
    snomed_delimiter: str
    snomed_has_header: bool

    snomed_description_id_col: str
    snomed_description_concept_id_col: str
    snomed_description_term_col: str
    snomed_description_type_id_col: Optional[str]
    snomed_description_language_code_col: Optional[str]
    snomed_description_active_col: Optional[str]

    snomed_concept_id_col: str
    snomed_concept_active_col: Optional[str]

    snomed_active_value: str
    snomed_language_values: Optional[Set[str]]
    keep_inactive_descriptions: bool
    keep_inactive_concepts: bool

    snogit_path: Path
    snogit_delimiter: str
    snogit_has_header: bool
    snogit_manual_header: Optional[List[str]]

    snogit_concept_id_col: str
    snogit_term_id_col: Optional[str]
    snogit_german_term_col: str
    snogit_english_term_col: Optional[str]

    unicode_nfkc: bool
    casefold: bool
    punctuation_to_space: bool
    symbols_to_space: bool
    collapse_whitespace: bool
    strip: bool

    levenshtein_enabled: bool
    levenshtein_max_distance: int
    levenshtein_relative_distance: float


@dataclass(frozen=True)
class EntitySpan:
    text: str
    label: str
    start_token: int
    end_token: int
    start_char: Optional[int]
    end_char: Optional[int]
    text_source: str


@dataclass(frozen=True)
class SnomedDescription:
    concept_id: str
    term: str
    description_id: Optional[str]
    type_id: Optional[str]
    description_type: Optional[str]
    language_code: Optional[str]
    active: Optional[str]


@dataclass(frozen=True)
class SnomedConceptInfo:
    concept_id: str
    concept_active: Optional[str]
    fsn_terms: Tuple[str, ...]
    descriptions: Tuple[SnomedDescription, ...]


@dataclass(frozen=True)
class SnogitTerm:
    concept_id: str
    german_term: str
    term_id: Optional[str]
    english_term: Optional[str]


def increase_csv_field_size_limit() -> None:
    max_size = sys.maxsize
    while True:
        try:
            csv.field_size_limit(max_size)
            return
        except OverflowError:
            max_size = int(max_size / 10)


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)

    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def load_config_file(path: Path) -> Dict[str, Any]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")

    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "YAML config requires PyYAML. Install it with:\n"
                "  pip install pyyaml\n"
                "Or use a JSON config instead."
            ) from e

        loaded = yaml.safe_load(text)
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Config must be a mapping/object: {path}")
        return loaded

    if suffix == ".json":
        loaded = json.loads(text)
        if not isinstance(loaded, dict):
            raise ValueError(f"Config must be a JSON object: {path}")
        return loaded

    raise ValueError(
        f"Unsupported config extension '{path.suffix}'. Use .yaml, .yml, or .json."
    )


def require_str(config: Dict[str, Any], key: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or value == "":
        raise ValueError(f"Missing or invalid required config key: {key}")
    return value


def optional_str(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"Expected string or null, got: {value!r}")
    return value


def parse_string_set(value: Any) -> Optional[Set[str]]:
    if value is None:
        return None

    if isinstance(value, str):
        values = [v.strip() for v in value.split(",") if v.strip()]
        return set(values) if values else None

    if isinstance(value, list):
        values = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError(f"Expected list of strings, got: {item!r}")
            item = item.strip()
            if item:
                values.append(item)
        return set(values) if values else None

    raise ValueError("Expected null, string, or list of strings")


def parse_manual_header(value: Any) -> Optional[List[str]]:
    if value is None:
        return None

    if isinstance(value, str):
        cols = [v.strip() for v in value.split(",") if v.strip()]
        return cols if cols else None

    if isinstance(value, list):
        cols = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError(
                    f"manual_header must contain only strings, got: {item!r}"
                )
            item = item.strip()
            if item:
                cols.append(item)
        return cols if cols else None

    raise ValueError("manual_header must be null, string, or list of strings")


def build_config(path: Path) -> Config:
    user_config = load_config_file(path)
    merged = deep_merge(DEFAULT_CONFIG, user_config)

    io_config = merged.get("io", {})

    snomed = merged.get("snomed", {})
    snomed_desc_cols = snomed.get("description_columns", {})
    snomed_concept_cols = snomed.get("concept_columns", {})

    snogit = merged.get("snogit", {})
    snogit_cols = snogit.get("columns", {})

    matching = merged.get("matching", {})
    normalization = matching.get("normalization", {})
    levenshtein = matching.get("levenshtein", {})

    snomed_concept_path_raw = snomed.get("concept_path")
    snomed_concept_path = (
        Path(snomed_concept_path_raw)
        if isinstance(snomed_concept_path_raw, str) and snomed_concept_path_raw
        else None
    )

    snogit_manual_header = parse_manual_header(snogit.get("manual_header"))
    snogit_has_header = bool(snogit.get("has_header", False))

    if not snogit_has_header and snogit_manual_header is None:
        raise ValueError(
            "Config has snogit.has_header=false but snogit.manual_header is missing."
        )

    levenshtein_max_distance = int(levenshtein.get("max_distance", 5))
    levenshtein_relative_distance = float(levenshtein.get("relative_distance", 0.3))

    if levenshtein_max_distance < 0:
        raise ValueError("matching.levenshtein.max_distance must be >= 0")

    if levenshtein_relative_distance < 0:
        raise ValueError("matching.levenshtein.relative_distance must be >= 0")

    return Config(
        input_path=Path(require_str(merged, "input_path")),
        output_path=Path(require_str(merged, "output_path")),
        stats_output_path=Path(require_str(merged, "stats_output_path")),
        input_glob=str(io_config.get("input_glob", "**/*.jsonl")),
        output_suffix=str(io_config.get("output_suffix", ".grounded.jsonl")),
        snomed_description_path=Path(require_str(snomed, "description_path")),
        snomed_concept_path=snomed_concept_path,
        snomed_delimiter=str(snomed.get("delimiter", "\t")),
        snomed_has_header=bool(snomed.get("has_header", True)),
        snomed_description_id_col=require_str(snomed_desc_cols, "description_id"),
        snomed_description_concept_id_col=require_str(
            snomed_desc_cols, "concept_id"
        ),
        snomed_description_term_col=require_str(snomed_desc_cols, "term"),
        snomed_description_type_id_col=optional_str(snomed_desc_cols.get("type_id")),
        snomed_description_language_code_col=optional_str(
            snomed_desc_cols.get("language_code")
        ),
        snomed_description_active_col=optional_str(snomed_desc_cols.get("active")),
        snomed_concept_id_col=require_str(snomed_concept_cols, "concept_id"),
        snomed_concept_active_col=optional_str(snomed_concept_cols.get("active")),
        snomed_active_value=str(snomed.get("active_value", "1")),
        snomed_language_values=parse_string_set(snomed.get("language_values")),
        keep_inactive_descriptions=bool(
            snomed.get("keep_inactive_descriptions", False)
        ),
        keep_inactive_concepts=bool(snomed.get("keep_inactive_concepts", True)),
        snogit_path=Path(require_str(snogit, "path")),
        snogit_delimiter=str(snogit.get("delimiter", "\t")),
        snogit_has_header=snogit_has_header,
        snogit_manual_header=snogit_manual_header,
        snogit_concept_id_col=require_str(snogit_cols, "concept_id"),
        snogit_term_id_col=optional_str(snogit_cols.get("term_id")),
        snogit_german_term_col=require_str(snogit_cols, "german_term"),
        snogit_english_term_col=optional_str(snogit_cols.get("english_term")),
        unicode_nfkc=bool(normalization.get("unicode_nfkc", True)),
        casefold=bool(normalization.get("casefold", True)),
        punctuation_to_space=bool(normalization.get("punctuation_to_space", True)),
        symbols_to_space=bool(normalization.get("symbols_to_space", True)),
        collapse_whitespace=bool(normalization.get("collapse_whitespace", True)),
        strip=bool(normalization.get("strip", True)),
        levenshtein_enabled=bool(levenshtein.get("enabled", True)),
        levenshtein_max_distance=levenshtein_max_distance,
        levenshtein_relative_distance=levenshtein_relative_distance,
    )


def discover_input_files(config: Config) -> List[Path]:
    if config.input_path.is_file():
        return [config.input_path]

    if config.input_path.is_dir():
        files = sorted(
            path for path in config.input_path.glob(config.input_glob) if path.is_file()
        )

        if not files:
            raise ValueError(
                f"No input files found in directory {config.input_path} "
                f"with glob {config.input_glob!r}"
            )

        return files

    raise ValueError(f"Input path does not exist: {config.input_path}")


def output_path_for_input_file(
    *,
    input_file: Path,
    config: Config,
) -> Path:
    if config.input_path.is_file():
        return config.output_path

    relative = input_file.relative_to(config.input_path)
    output_name = relative.with_suffix("").name + config.output_suffix
    output_relative = relative.with_name(output_name)

    return config.output_path / output_relative


def decode_snomed_description_type(type_id: Optional[str]) -> Optional[str]:
    if type_id is None:
        return None
    return SNOMED_DESCRIPTION_TYPE_IDS.get(type_id, "other")


def normalize_for_exact_match(text: str, config: Config) -> str:
    if config.unicode_nfkc:
        text = unicodedata.normalize("NFKC", text)

    if config.casefold:
        text = text.casefold()

    chars: List[str] = []
    for ch in text:
        category = unicodedata.category(ch)
        is_punct = category.startswith("P")
        is_symbol = category.startswith("S")

        if config.punctuation_to_space and is_punct:
            chars.append(" ")
        elif config.symbols_to_space and is_symbol:
            chars.append(" ")
        else:
            chars.append(ch)

    text = "".join(chars)

    if config.collapse_whitespace:
        text = re.sub(r"\s+", " ", text)

    if config.strip:
        text = text.strip()

    return text


def build_length_index(terms: Iterable[str]) -> Dict[int, List[str]]:
    """
    Build length -> normalized terms index.
    """
    index: Dict[int, List[str]] = defaultdict(list)

    for term in terms:
        index[len(term)].append(term)

    return {
        length: sorted(set(values))
        for length, values in index.items()
    }


def find_levenshtein_candidate_terms(
    *,
    query: str,
    length_index: Dict[int, List[str]],
    max_distance: int,
) -> List[Tuple[str, int]]:
    """
    Return normalized candidate terms within Levenshtein distance <= max_distance
    using RapidFuzz instead of pure Python iterations.
    """
    if max_distance <= 0:
        return []

    query_len = len(query)
    min_len = max(0, query_len - max_distance)
    max_len = query_len + max_distance

    # Consolidate our targeted length buckets into a single candidate list
    candidates: List[str] = []
    for length in range(min_len, max_len + 1):
        candidates.extend(length_index.get(length, []))

    if not candidates:
        return []

    # Run rapidfuzz C++ extraction
    matches = process.extract(
        query,
        candidates,
        scorer=distance.Levenshtein.distance,
        score_cutoff=max_distance,
        limit=None
    )

    # matches format is (choice, score, index) 
    # score is the integer Levenshtein distance because of the chosen scorer
    results: List[Tuple[str, int]] = []
    for candidate_term, dist, _ in matches:
        if candidate_term == query:
            continue  # Exclude exact matches as they are handled separately
        results.append((candidate_term, int(dist)))

    return sorted(results, key=lambda x: (x[1], x[0]))


def dynamic_levenshtein_max_distance(
    *,
    normalized_entity: str,
    configured_max_distance: int,
    relative_distance: float,
) -> int:
    return min(
        configured_max_distance,
        int(len(normalized_entity) * relative_distance),
    )


def deduplicate_snomed_descriptions(
    descriptions: Iterable[SnomedDescription],
) -> List[SnomedDescription]:
    seen: Set[Tuple[str, Optional[str], str]] = set()
    result: List[SnomedDescription] = []

    for desc in descriptions:
        key = (desc.concept_id, desc.description_id, desc.term)
        if key in seen:
            continue
        seen.add(key)
        result.append(desc)

    return sorted(
        result,
        key=lambda d: (
            d.concept_id,
            d.term,
            d.description_id or "",
            d.type_id or "",
            d.language_code or "",
        ),
    )


def deduplicate_snogit_terms(
    terms: Iterable[SnogitTerm],
) -> List[SnogitTerm]:
    seen: Set[Tuple[str, Optional[str], str]] = set()
    result: List[SnogitTerm] = []

    for term in terms:
        key = (term.concept_id, term.term_id, term.german_term)
        if key in seen:
            continue
        seen.add(key)
        result.append(term)

    return sorted(
        result,
        key=lambda t: (
            t.concept_id,
            t.german_term,
            t.term_id or "",
            t.english_term or "",
        ),
    )


def optional_col(row: Dict[Any, Any], col: Optional[str]) -> Optional[str]:
    if col is None:
        return None
    value = row.get(col)
    if value is None or value == "":
        return None
    return str(value)


def make_dict_reader(
    f: Any,
    *,
    delimiter: str,
    has_header: bool,
    manual_header: Optional[List[str]] = None,
) -> csv.DictReader:
    if has_header:
        return csv.DictReader(f, delimiter=delimiter)

    if manual_header is None:
        raise ValueError("has_header=false requires manual_header.")

    return csv.DictReader(f, delimiter=delimiter, fieldnames=manual_header)


def validate_columns(
    *,
    reader: csv.DictReader,
    required: List[str],
    optional: List[Optional[str]],
    path: Path,
) -> None:
    if reader.fieldnames is None:
        raise ValueError(f"No header/fieldnames available for file: {path}")

    missing = [col for col in required if col not in reader.fieldnames]
    if missing:
        raise ValueError(
            f"Missing required columns in {path}: {missing}. "
            f"Available columns: {reader.fieldnames}"
        )

    for col in optional:
        if col is not None and col not in reader.fieldnames:
            raise ValueError(
                f"Column '{col}' not found in {path}. "
                f"Available columns: {reader.fieldnames}"
            )


def load_snomed_concept_activeness(config: Config) -> Tuple[Dict[str, str], Dict[str, Any]]:
    if config.snomed_concept_path is None:
        return {}, {
            "concept_path": None,
            "loaded": False,
            "rows_read": 0,
            "rows_kept": 0,
            "note": (
                "No SNOMED Concept file configured; concept_active will be null. "
                "Description active status is not concept active status."
            ),
        }

    concept_active: Dict[str, str] = {}
    rows_read = 0
    rows_kept = 0
    rows_skipped_inactive = 0
    rows_skipped_missing_required = 0

    with config.snomed_concept_path.open("r", encoding="utf-8", newline="") as f:
        reader = make_dict_reader(
            f,
            delimiter=config.snomed_delimiter,
            has_header=True,
        )

        validate_columns(
            reader=reader,
            required=[config.snomed_concept_id_col],
            optional=[config.snomed_concept_active_col],
            path=config.snomed_concept_path,
        )

        for row in reader:
            rows_read += 1

            concept_id = row.get(config.snomed_concept_id_col, "").strip()
            if not concept_id:
                rows_skipped_missing_required += 1
                continue

            active = optional_col(row, config.snomed_concept_active_col)

            if (
                config.snomed_concept_active_col is not None
                and not config.keep_inactive_concepts
                and active != config.snomed_active_value
            ):
                rows_skipped_inactive += 1
                continue

            concept_active[concept_id] = active if active is not None else ""
            rows_kept += 1

    return concept_active, {
        "concept_path": str(config.snomed_concept_path),
        "loaded": True,
        "rows_read": rows_read,
        "rows_kept": rows_kept,
        "rows_skipped_inactive": rows_skipped_inactive,
        "rows_skipped_missing_required": rows_skipped_missing_required,
        "num_concepts_with_active_status": len(concept_active),
    }


def load_snomed_descriptions(
    config: Config,
    concept_active: Dict[str, str],
) -> Tuple[
    Dict[str, List[SnomedDescription]],
    Dict[str, SnomedConceptInfo],
    Dict[str, Any],
]:
    snomed_term_lookup: Dict[str, List[SnomedDescription]] = defaultdict(list)
    descriptions_by_concept: Dict[str, List[SnomedDescription]] = defaultdict(list)

    rows_read = 0
    rows_kept = 0
    rows_skipped_inactive_description = 0
    rows_skipped_language = 0
    rows_skipped_missing_required = 0
    duplicate_description_rows = 0
    rows_with_extra_fields = 0

    rows_by_description_type: Dict[str, int] = defaultdict(int)

    unique_concepts: Set[str] = set()
    unique_raw_terms: Set[str] = set()
    unique_normalized_terms: Set[str] = set()
    seen_rows: Set[Tuple[Optional[str], str, str, str]] = set()

    with config.snomed_description_path.open("r", encoding="utf-8", newline="") as f:
        reader = make_dict_reader(
            f,
            delimiter=config.snomed_delimiter,
            has_header=config.snomed_has_header,
        )

        validate_columns(
            reader=reader,
            required=[
                config.snomed_description_id_col,
                config.snomed_description_concept_id_col,
                config.snomed_description_term_col,
            ],
            optional=[
                config.snomed_description_type_id_col,
                config.snomed_description_language_code_col,
                config.snomed_description_active_col,
            ],
            path=config.snomed_description_path,
        )

        for row in reader:
            rows_read += 1

            if None in row:
                rows_with_extra_fields += 1

            description_id = optional_col(row, config.snomed_description_id_col)
            concept_id = row.get(config.snomed_description_concept_id_col, "").strip()
            term = row.get(config.snomed_description_term_col, "")

            if not concept_id or not term:
                rows_skipped_missing_required += 1
                continue

            active = optional_col(row, config.snomed_description_active_col)
            if (
                config.snomed_description_active_col is not None
                and not config.keep_inactive_descriptions
                and active != config.snomed_active_value
            ):
                rows_skipped_inactive_description += 1
                continue

            language_code = optional_col(row, config.snomed_description_language_code_col)
            if (
                config.snomed_language_values is not None
                and language_code not in config.snomed_language_values
            ):
                rows_skipped_language += 1
                continue

            normalized_term = normalize_for_exact_match(term, config)
            if not normalized_term:
                rows_skipped_missing_required += 1
                continue

            type_id = optional_col(row, config.snomed_description_type_id_col)
            description_type = decode_snomed_description_type(type_id)

            dedup_key = (description_id, concept_id, term, normalized_term)
            if dedup_key in seen_rows:
                duplicate_description_rows += 1
                continue
            seen_rows.add(dedup_key)

            desc = SnomedDescription(
                concept_id=concept_id,
                term=term,
                description_id=description_id,
                type_id=type_id,
                description_type=description_type,
                language_code=language_code,
                active=active,
            )

            snomed_term_lookup[normalized_term].append(desc)
            descriptions_by_concept[concept_id].append(desc)

            rows_kept += 1
            rows_by_description_type[description_type or "unknown"] += 1
            unique_concepts.add(concept_id)
            unique_raw_terms.add(term)
            unique_normalized_terms.add(normalized_term)

    snomed_term_lookup = {
        key: sorted(
            descs,
            key=lambda d: (
                d.concept_id,
                d.term,
                d.description_id or "",
                d.type_id or "",
                d.language_code or "",
            ),
        )
        for key, descs in snomed_term_lookup.items()
    }

    snomed_concepts: Dict[str, SnomedConceptInfo] = {}

    for concept_id, descs in descriptions_by_concept.items():
        sorted_descs = tuple(
            sorted(
                descs,
                key=lambda d: (
                    d.term,
                    d.description_id or "",
                    d.type_id or "",
                    d.language_code or "",
                ),
            )
        )
        fsn_terms = tuple(
            sorted(
                {
                    d.term
                    for d in sorted_descs
                    if d.description_type == "fully_specified_name"
                }
            )
        )
        snomed_concepts[concept_id] = SnomedConceptInfo(
            concept_id=concept_id,
            concept_active=concept_active.get(concept_id),
            fsn_terms=fsn_terms,
            descriptions=sorted_descs,
        )

    stats = {
        "description_path": str(config.snomed_description_path),
        "delimiter": config.snomed_delimiter,
        "has_header": config.snomed_has_header,
        "csv_field_size_limit": csv.field_size_limit(),
        "columns": {
            "description_id": config.snomed_description_id_col,
            "concept_id": config.snomed_description_concept_id_col,
            "term": config.snomed_description_term_col,
            "type_id": config.snomed_description_type_id_col,
            "language_code": config.snomed_description_language_code_col,
            "active": config.snomed_description_active_col,
        },
        "active_value": config.snomed_active_value,
        "language_values": (
            sorted(config.snomed_language_values)
            if config.snomed_language_values
            else None
        ),
        "keep_inactive_descriptions": config.keep_inactive_descriptions,
        "rows_read": rows_read,
        "rows_kept": rows_kept,
        "rows_skipped_inactive_description": rows_skipped_inactive_description,
        "rows_skipped_language": rows_skipped_language,
        "rows_skipped_missing_required": rows_skipped_missing_required,
        "duplicate_description_rows": duplicate_description_rows,
        "rows_with_extra_fields": rows_with_extra_fields,
        "num_unique_concepts_in_descriptions": len(unique_concepts),
        "num_unique_raw_terms": len(unique_raw_terms),
        "num_unique_normalized_terms": len(unique_normalized_terms),
        "rows_by_description_type": dict(sorted(rows_by_description_type.items())),
        "num_concepts_with_fsn": sum(
            1 for info in snomed_concepts.values() if len(info.fsn_terms) > 0
        ),
        "num_concepts_with_concept_active_status": sum(
            1 for info in snomed_concepts.values() if info.concept_active is not None
        ),
    }

    return snomed_term_lookup, snomed_concepts, stats


def load_snogit(
    config: Config,
) -> Tuple[Dict[str, List[SnogitTerm]], Dict[str, Any]]:
    snogit_lookup: Dict[str, List[SnogitTerm]] = defaultdict(list)

    rows_read = 0
    rows_kept = 0
    rows_skipped_missing_required = 0
    duplicate_rows = 0
    rows_with_extra_fields = 0

    unique_concepts: Set[str] = set()
    unique_raw_german_terms: Set[str] = set()
    unique_normalized_german_terms: Set[str] = set()
    seen_rows: Set[Tuple[str, Optional[str], str]] = set()

    with config.snogit_path.open("r", encoding="utf-8", newline="") as f:
        reader = make_dict_reader(
            f,
            delimiter=config.snogit_delimiter,
            has_header=config.snogit_has_header,
            manual_header=config.snogit_manual_header,
        )

        validate_columns(
            reader=reader,
            required=[
                config.snogit_concept_id_col,
                config.snogit_german_term_col,
            ],
            optional=[
                config.snogit_term_id_col,
                config.snogit_english_term_col,
            ],
            path=config.snogit_path,
        )

        for row in reader:
            rows_read += 1

            if None in row:
                rows_with_extra_fields += 1

            concept_id = row.get(config.snogit_concept_id_col, "").strip()
            german_term = row.get(config.snogit_german_term_col, "")
            term_id = optional_col(row, config.snogit_term_id_col)
            english_term = optional_col(row, config.snogit_english_term_col)

            if not concept_id or not german_term:
                rows_skipped_missing_required += 1
                continue

            normalized_term = normalize_for_exact_match(german_term, config)
            if not normalized_term:
                rows_skipped_missing_required += 1
                continue

            dedup_key = (concept_id, term_id, german_term)
            if dedup_key in seen_rows:
                duplicate_rows += 1
                continue
            seen_rows.add(dedup_key)

            snogit_term = SnogitTerm(
                concept_id=concept_id,
                german_term=german_term,
                term_id=term_id,
                english_term=english_term,
            )

            snogit_lookup[normalized_term].append(snogit_term)

            rows_kept += 1
            unique_concepts.add(concept_id)
            unique_raw_german_terms.add(german_term)
            unique_normalized_german_terms.add(normalized_term)

    snogit_lookup = {
        key: sorted(
            terms,
            key=lambda t: (
                t.concept_id,
                t.german_term,
                t.term_id or "",
                t.english_term or "",
            ),
        )
        for key, terms in snogit_lookup.items()
    }

    stats = {
        "path": str(config.snogit_path),
        "delimiter": config.snogit_delimiter,
        "has_header": config.snogit_has_header,
        "manual_header": config.snogit_manual_header,
        "columns": {
            "concept_id": config.snogit_concept_id_col,
            "term_id": config.snogit_term_id_col,
            "german_term": config.snogit_german_term_col,
            "english_term": config.snogit_english_term_col,
        },
        "rows_read": rows_read,
        "rows_kept": rows_kept,
        "rows_skipped_missing_required": rows_skipped_missing_required,
        "duplicate_rows": duplicate_rows,
        "rows_with_extra_fields": rows_with_extra_fields,
        "num_unique_concepts": len(unique_concepts),
        "num_unique_raw_german_terms": len(unique_raw_german_terms),
        "num_unique_normalized_german_terms": len(unique_normalized_german_terms),
    }

    return snogit_lookup, stats


def snomed_description_to_json(desc: SnomedDescription) -> Dict[str, Any]:
    return {
        "description_id": desc.description_id,
        "term": desc.term,
        "type_id": desc.type_id,
        "description_type": desc.description_type,
        "language_code": desc.language_code,
        "active": desc.active,
    }


def snogit_term_to_json(term: SnogitTerm) -> Dict[str, Any]:
    return {
        "term_id": term.term_id,
        "german_term": term.german_term,
        "english_term": term.english_term,
    }


def concept_match_to_json(
    *,
    concept_id: str,
    snomed_desc_matches: List[SnomedDescription],
    snogit_term_matches: List[SnogitTerm],
    snomed_concepts: Dict[str, SnomedConceptInfo],
) -> Dict[str, Any]:
    concept_info = snomed_concepts.get(concept_id)

    known_in_snomed_german = concept_info is not None
    concept_active = concept_info.concept_active if concept_info is not None else None
    fsn_terms = sorted(concept_info.fsn_terms) if concept_info is not None else []

    all_snomed_descriptions = (
        list(concept_info.descriptions) if concept_info is not None else []
    )

    matched_snomed_terms = sorted({d.term for d in snomed_desc_matches})
    matched_snomed_synonym_terms = sorted(
        {d.term for d in snomed_desc_matches if d.description_type == "synonym"}
    )
    matched_snomed_fsn_terms = sorted(
        {
            d.term
            for d in snomed_desc_matches
            if d.description_type == "fully_specified_name"
        }
    )
    matched_snomed_definition_terms = sorted(
        {d.term for d in snomed_desc_matches if d.description_type == "definition"}
    )
    matched_snomed_other_terms = sorted(
        {
            d.term
            for d in snomed_desc_matches
            if d.description_type not in {"synonym", "fully_specified_name", "definition"}
        }
    )

    matched_snomed_description_types = sorted(
        {d.description_type or "unknown" for d in snomed_desc_matches}
    )

    matched_snogit_terms = sorted({t.german_term for t in snogit_term_matches})
    matched_snogit_english_terms = sorted(
        {t.english_term for t in snogit_term_matches if t.english_term}
    )

    sources = []
    if snomed_desc_matches:
        sources.append("snomed_de")
    if snogit_term_matches:
        sources.append("snogit")

    return {
        "concept_id": concept_id,
        "sources": sources,
        "known_in_snomed_german_descriptions": known_in_snomed_german,
        "concept_active": concept_active,
        "concept_active_available": concept_active is not None,
        "fsn_terms": fsn_terms,
        "fsn_available": len(fsn_terms) > 0,
        "num_fsn_terms": len(fsn_terms),

        "has_snomed_match": len(snomed_desc_matches) > 0,
        "has_snomed_synonym_match": len(matched_snomed_synonym_terms) > 0,
        "has_snomed_fsn_match": len(matched_snomed_fsn_terms) > 0,
        "has_snogit_match": len(snogit_term_matches) > 0,

        "matched_snomed_terms": matched_snomed_terms,
        "matched_snomed_synonym_terms": matched_snomed_synonym_terms,
        "matched_snomed_fsn_terms": matched_snomed_fsn_terms,
        "matched_snomed_definition_terms": matched_snomed_definition_terms,
        "matched_snomed_other_terms": matched_snomed_other_terms,
        "matched_snomed_description_types": matched_snomed_description_types,

        "matched_snogit_terms": matched_snogit_terms,
        "matched_snogit_english_terms": matched_snogit_english_terms,

        "num_matching_snomed_descriptions": len(snomed_desc_matches),
        "num_matching_snogit_terms": len(snogit_term_matches),
        "num_snomed_descriptions_for_concept": len(all_snomed_descriptions),

        "snomed_description_matches": [
            snomed_description_to_json(d) for d in snomed_desc_matches
        ],
        "snogit_term_matches": [
            snogit_term_to_json(t) for t in snogit_term_matches
        ],
    }


def make_concept_matches(
    *,
    snomed_desc_matches: List[SnomedDescription],
    snogit_term_matches: List[SnogitTerm],
    snomed_concepts: Dict[str, SnomedConceptInfo],
) -> List[Dict[str, Any]]:
    by_concept_snomed: Dict[str, List[SnomedDescription]] = defaultdict(list)
    by_concept_snogit: Dict[str, List[SnogitTerm]] = defaultdict(list)

    for desc in snomed_desc_matches:
        by_concept_snomed[desc.concept_id].append(desc)

    for term in snogit_term_matches:
        by_concept_snogit[term.concept_id].append(term)

    concept_ids = sorted(set(by_concept_snomed) | set(by_concept_snogit))

    return [
        concept_match_to_json(
            concept_id=concept_id,
            snomed_desc_matches=by_concept_snomed.get(concept_id, []),
            snogit_term_matches=by_concept_snogit.get(concept_id, []),
            snomed_concepts=snomed_concepts,
        )
        for concept_id in concept_ids
    ]


def reconstruct_span_text_from_offsets(
    sentence_text: Optional[str],
    sentence_offset: Optional[List[int]],
    token_offsets: Optional[List[List[int]]],
    start_token: int,
    end_token: int,
    fallback_tokens: List[str],
) -> Tuple[str, str]:
    if (
        sentence_text is not None
        and sentence_offset is not None
        and token_offsets is not None
        and len(sentence_offset) == 2
        and end_token > start_token
    ):
        sentence_start = sentence_offset[0]
        char_start = token_offsets[start_token][0] - sentence_start
        char_end = token_offsets[end_token - 1][1] - sentence_start

        if 0 <= char_start <= char_end <= len(sentence_text):
            return sentence_text[char_start:char_end], "character_offsets"

    return " ".join(fallback_tokens), "token_join_fallback"


def extract_bio_spans(record: Dict[str, Any]) -> List[EntitySpan]:
    tokens = record.get("tokens")
    tags = record.get("tags")
    token_offsets = record.get("token_offsets")
    sentence_text = record.get("text")
    sentence_offset = record.get("sentence_offset")

    if tokens is None or tags is None:
        raise ValueError(
            f"Record missing required keys 'tokens' and/or 'tags': "
            f"{record.get('sentence_id', '<unknown sentence_id>')}"
        )

    if len(tokens) != len(tags):
        raise ValueError(
            f"tokens/tags length mismatch in {record.get('sentence_id', '<unknown>')}: "
            f"{len(tokens)} != {len(tags)}"
        )

    if token_offsets is not None and len(token_offsets) != len(tokens):
        raise ValueError(
            f"tokens/token_offsets length mismatch in {record.get('sentence_id', '<unknown>')}: "
            f"{len(tokens)} != {len(token_offsets)}"
        )

    spans: List[EntitySpan] = []
    current_label: Optional[str] = None
    current_start: Optional[int] = None

    def close_span(end_idx: int) -> None:
        nonlocal current_label, current_start

        if current_label is None or current_start is None:
            return

        span_tokens = tokens[current_start:end_idx]
        span_text, text_source = reconstruct_span_text_from_offsets(
            sentence_text=sentence_text,
            sentence_offset=sentence_offset,
            token_offsets=token_offsets,
            start_token=current_start,
            end_token=end_idx,
            fallback_tokens=span_tokens,
        )

        start_char = None
        end_char = None
        if token_offsets is not None:
            start_char = token_offsets[current_start][0]
            end_char = token_offsets[end_idx - 1][1]

        spans.append(
            EntitySpan(
                text=span_text,
                label=current_label,
                start_token=current_start,
                end_token=end_idx,
                start_char=start_char,
                end_char=end_char,
                text_source=text_source,
            )
        )

        current_label = None
        current_start = None

    for i, tag in enumerate(tags):
        if tag == "O" or tag == "":
            close_span(i)
            continue

        if "-" not in tag:
            raise ValueError(
                f"Unsupported tag '{tag}' in {record.get('sentence_id', '<unknown>')}"
            )

        prefix, label = tag.split("-", 1)

        if prefix == "B":
            close_span(i)
            current_label = label
            current_start = i

        elif prefix == "I":
            if current_label is None:
                current_label = label
                current_start = i
            elif current_label != label:
                close_span(i)
                current_label = label
                current_start = i

        else:
            raise ValueError(
                f"Unsupported BIO prefix '{prefix}' in tag '{tag}' "
                f"in {record.get('sentence_id', '<unknown>')}"
            )

    close_span(len(tokens))
    return spans


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on line {line_no} in {path}: {e}") from e


def entity_to_json(span: EntitySpan) -> Dict[str, Any]:
    return {
        "text": span.text,
        "label": span.label,
        "start_token": span.start_token,
        "end_token": span.end_token,
        "start_char": span.start_char,
        "end_char": span.end_char,
        "text_source": span.text_source,
        "span_source": "gold_bio_tags",
    }


def init_label_stats() -> Dict[str, Any]:
    return {
        "entities": 0,
        "matched_entities": 0,
        "unmatched_entities": 0,
        "concept_ambiguous_entities": 0,

        "matched_entities_via_snomed": 0,
        "matched_entities_via_snogit": 0,
        "matched_entities_via_both": 0,

        "matched_entities_with_snomed_synonym_match": 0,
        "matched_entities_with_snomed_fsn_match": 0,

        "matched_entities_with_concept_active_available": 0,
        "matched_entities_with_active_concept": 0,
        "matched_entities_with_inactive_concept": 0,
        "matched_entities_with_unknown_snogit_concept_in_snomed": 0,

        "total_snomed_description_matches": 0,
        "total_snogit_term_matches": 0,
        "total_unique_concept_matches": 0,

        "matched_entities_with_levenshtein_snomed_candidate": 0,
        "matched_entities_with_levenshtein_snogit_candidate": 0,
    }


def finalize_rates(stats: Dict[str, Any]) -> None:
    entities = stats.get("entities", 0)
    matched_entities = stats.get("matched_entities", 0)

    if entities > 0:
        stats["entity_match_rate"] = matched_entities / entities
        stats["concept_ambiguity_rate_among_entities"] = (
            stats.get("concept_ambiguous_entities", 0) / entities
        )
    else:
        stats["entity_match_rate"] = 0.0
        stats["concept_ambiguity_rate_among_entities"] = 0.0

    if matched_entities > 0:
        stats["concept_ambiguity_rate_among_matched_entities"] = (
            stats.get("concept_ambiguous_entities", 0) / matched_entities
        )
        stats["snomed_match_rate_among_matched_entities"] = (
            stats.get("matched_entities_via_snomed", 0) / matched_entities
        )
        stats["snogit_match_rate_among_matched_entities"] = (
            stats.get("matched_entities_via_snogit", 0) / matched_entities
        )
    else:
        stats["concept_ambiguity_rate_among_matched_entities"] = 0.0
        stats["snomed_match_rate_among_matched_entities"] = 0.0
        stats["snogit_match_rate_among_matched_entities"] = 0.0


def normalization_config_to_json(config: Config) -> Dict[str, bool]:
    return {
        "unicode_nfkc": config.unicode_nfkc,
        "casefold": config.casefold,
        "punctuation_to_space": config.punctuation_to_space,
        "symbols_to_space": config.symbols_to_space,
        "collapse_whitespace": config.collapse_whitespace,
        "strip": config.strip,
    }


def update_stats_for_entity(
    *,
    stats: Dict[str, Any],
    concept_matches: List[Dict[str, Any]],
    num_snomed_desc_matches: int,
    num_snogit_term_matches: int,
    has_levenshtein_snomed_candidate: bool,
    has_levenshtein_snogit_candidate: bool,
) -> None:
    num_concepts = len(concept_matches)
    is_matched = num_concepts > 0
    is_ambiguous = num_concepts > 1

    has_snomed = any(m["has_snomed_match"] for m in concept_matches)
    has_snogit = any(m["has_snogit_match"] for m in concept_matches)
    has_snomed_synonym = any(m["has_snomed_synonym_match"] for m in concept_matches)
    has_snomed_fsn = any(m["has_snomed_fsn_match"] for m in concept_matches)

    has_concept_active_available = any(
        m["concept_active_available"] for m in concept_matches
    )
    has_active_concept = any(m["concept_active"] == "1" for m in concept_matches)
    has_inactive_concept = any(m["concept_active"] == "0" for m in concept_matches)

    has_unknown_snogit_concept = any(
        m["has_snogit_match"] and not m["known_in_snomed_german_descriptions"]
        for m in concept_matches
    )

    if is_matched:
        stats["matched_entities"] += 1
    else:
        stats["unmatched_entities"] += 1

    if is_ambiguous:
        stats["concept_ambiguous_entities"] += 1

    if has_snomed:
        stats["matched_entities_via_snomed"] += 1

    if has_snogit:
        stats["matched_entities_via_snogit"] += 1

    if has_snomed and has_snogit:
        stats["matched_entities_via_both"] += 1

    if has_snomed_synonym:
        stats["matched_entities_with_snomed_synonym_match"] += 1

    if has_snomed_fsn:
        stats["matched_entities_with_snomed_fsn_match"] += 1

    if has_concept_active_available:
        stats["matched_entities_with_concept_active_available"] += 1

    if has_active_concept:
        stats["matched_entities_with_active_concept"] += 1

    if has_inactive_concept:
        stats["matched_entities_with_inactive_concept"] += 1

    if has_unknown_snogit_concept:
        stats["matched_entities_with_unknown_snogit_concept_in_snomed"] += 1

    if has_levenshtein_snomed_candidate:
        stats["matched_entities_with_levenshtein_snomed_candidate"] += 1

    if has_levenshtein_snogit_candidate:
        stats["matched_entities_with_levenshtein_snogit_candidate"] += 1

    stats["total_snomed_description_matches"] += num_snomed_desc_matches
    stats["total_snogit_term_matches"] += num_snogit_term_matches
    stats["total_unique_concept_matches"] += num_concepts


def ground_dataset(
    *,
    config: Config,
    input_file: Path,
    output_file: Path,
    snomed_term_lookup: Dict[str, List[SnomedDescription]],
    snomed_length_index: Dict[int, List[str]],
    snogit_lookup: Dict[str, List[SnogitTerm]],
    snogit_length_index: Dict[int, List[str]],
    snomed_concepts: Dict[str, SnomedConceptInfo],
) -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "input_path": str(input_file),
        "output_path": str(output_file),
        "matching": {
            "method": "exact_or_levenshtein_lexical_match_after_normalization",
            "case_sensitive": not config.casefold,
            "normalization": normalization_config_to_json(config),
            "levenshtein": {
                "enabled": config.levenshtein_enabled,
                "configured_max_distance": config.levenshtein_max_distance,
                "relative_distance": config.levenshtein_relative_distance,
                "formula": (
                    "min(configured_max_distance, "
                    "floor(len(normalized_entity) * relative_distance))"
                ),
            },
            "span_source": "gold_bio_tags",
            "sources": [
                "snomed_de_descriptions",
                "snogit_terms_resolved_to_snomed",
            ],
        },
        "sentences": 0,
        "entities": 0,
        **init_label_stats(),
        "span_text_sources": {
            "character_offsets": 0,
            "token_join_fallback": 0,
        },
        "by_label": {},
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as out:
        for record in iter_jsonl(input_file):
            stats["sentences"] += 1

            spans = extract_bio_spans(record)

            for span in spans:
                stats["entities"] += 1

                if span.text_source not in stats["span_text_sources"]:
                    stats["span_text_sources"][span.text_source] = 0
                stats["span_text_sources"][span.text_source] += 1

                if span.label not in stats["by_label"]:
                    stats["by_label"][span.label] = init_label_stats()

                label_stats = stats["by_label"][span.label]
                label_stats["entities"] += 1

                normalized_entity = normalize_for_exact_match(span.text, config)

                exact_snomed_desc_matches = snomed_term_lookup.get(
                    normalized_entity,
                    [],
                )
                exact_snogit_term_matches = snogit_lookup.get(
                    normalized_entity,
                    [],
                )

                effective_levenshtein_max_distance = (
                    dynamic_levenshtein_max_distance(
                        normalized_entity=normalized_entity,
                        configured_max_distance=config.levenshtein_max_distance,
                        relative_distance=config.levenshtein_relative_distance,
                    )
                    if normalized_entity
                    else 0
                )

                snomed_levenshtein_matches: List[Dict[str, Any]] = []
                snogit_levenshtein_matches: List[Dict[str, Any]] = []

                fuzzy_snomed_desc_matches: List[SnomedDescription] = []
                fuzzy_snogit_term_matches: List[SnogitTerm] = []

                # Fuzzy matching short-circuits if we already found an exact match
                if (
                    config.levenshtein_enabled
                    and normalized_entity
                    and effective_levenshtein_max_distance > 0
                    and not exact_snomed_desc_matches
                    and not exact_snogit_term_matches
                ):
                    snomed_candidate_terms = find_levenshtein_candidate_terms(
                        query=normalized_entity,
                        length_index=snomed_length_index,
                        max_distance=effective_levenshtein_max_distance,
                    )

                    for candidate_term, dist in snomed_candidate_terms:
                        candidate_descs = snomed_term_lookup.get(candidate_term, [])
                        fuzzy_snomed_desc_matches.extend(candidate_descs)

                        snomed_levenshtein_matches.append(
                            {
                                "normalized_matched_term": candidate_term,
                                "distance": dist,
                                "num_descriptions": len(candidate_descs),
                            }
                        )

                    snogit_candidate_terms = find_levenshtein_candidate_terms(
                        query=normalized_entity,
                        length_index=snogit_length_index,
                        max_distance=effective_levenshtein_max_distance,
                    )

                    for candidate_term, dist in snogit_candidate_terms:
                        candidate_terms = snogit_lookup.get(candidate_term, [])
                        fuzzy_snogit_term_matches.extend(candidate_terms)

                        snogit_levenshtein_matches.append(
                            {
                                "normalized_matched_term": candidate_term,
                                "distance": dist,
                                "num_terms": len(candidate_terms),
                            }
                        )

                snomed_desc_matches = deduplicate_snomed_descriptions(
                    [
                        *exact_snomed_desc_matches,
                        *fuzzy_snomed_desc_matches,
                    ]
                )
                snogit_term_matches = deduplicate_snogit_terms(
                    [
                        *exact_snogit_term_matches,
                        *fuzzy_snogit_term_matches,
                    ]
                )

                concept_matches = make_concept_matches(
                    snomed_desc_matches=snomed_desc_matches,
                    snogit_term_matches=snogit_term_matches,
                    snomed_concepts=snomed_concepts,
                )

                has_levenshtein_snomed_candidate = len(snomed_levenshtein_matches) > 0
                has_levenshtein_snogit_candidate = len(snogit_levenshtein_matches) > 0

                update_stats_for_entity(
                    stats=stats,
                    concept_matches=concept_matches,
                    num_snomed_desc_matches=len(snomed_desc_matches),
                    num_snogit_term_matches=len(snogit_term_matches),
                    has_levenshtein_snomed_candidate=has_levenshtein_snomed_candidate,
                    has_levenshtein_snogit_candidate=has_levenshtein_snogit_candidate,
                )

                update_stats_for_entity(
                    stats=label_stats,
                    concept_matches=concept_matches,
                    num_snomed_desc_matches=len(snomed_desc_matches),
                    num_snogit_term_matches=len(snogit_term_matches),
                    has_levenshtein_snomed_candidate=has_levenshtein_snomed_candidate,
                    has_levenshtein_snogit_candidate=has_levenshtein_snogit_candidate,
                )

                output_record = {
                    "fname": record.get("fname"),
                    "sentence_id": record.get("sentence_id"),
                    "entity": entity_to_json(span),
                    "normalized_entity": normalized_entity,
                    "matches": concept_matches,

                    "method": "exact_or_levenshtein_lexical_match_after_normalization",

                    "levenshtein": {
                        "enabled": config.levenshtein_enabled,
                        "configured_max_distance": config.levenshtein_max_distance,
                        "relative_distance": config.levenshtein_relative_distance,
                        "effective_max_distance": effective_levenshtein_max_distance,
                        "formula": (
                            "min(configured_max_distance, "
                            "floor(len(normalized_entity) * relative_distance))"
                        ),
                        "snomed_candidate_terms": snomed_levenshtein_matches,
                        "snogit_candidate_terms": snogit_levenshtein_matches,
                        "num_snomed_candidate_terms": len(snomed_levenshtein_matches),
                        "num_snogit_candidate_terms": len(snogit_levenshtein_matches),
                    },

                    "num_exact_snomed_description_matches": len(
                        exact_snomed_desc_matches
                    ),
                    "num_exact_snogit_term_matches": len(
                        exact_snogit_term_matches
                    ),
                    "num_snomed_description_matches": len(snomed_desc_matches),
                    "num_snogit_term_matches": len(snogit_term_matches),
                    "num_unique_concept_matches": len(concept_matches),

                    "has_match": len(concept_matches) > 0,
                    "has_snomed_match": any(
                        m["has_snomed_match"] for m in concept_matches
                    ),
                    "has_snogit_match": any(
                        m["has_snogit_match"] for m in concept_matches
                    ),
                    "has_match_via_both": (
                        any(m["has_snomed_match"] for m in concept_matches)
                        and any(m["has_snogit_match"] for m in concept_matches)
                    ),
                    "has_levenshtein_snomed_candidate": (
                        has_levenshtein_snomed_candidate
                    ),
                    "has_levenshtein_snogit_candidate": (
                        has_levenshtein_snogit_candidate
                    ),
                    "is_concept_ambiguous": len(concept_matches) > 1,
                }

                out.write(json.dumps(output_record, ensure_ascii=False) + "\n")

    finalize_rates(stats)
    for label_stats in stats["by_label"].values():
        finalize_rates(label_stats)

    return stats


def aggregate_file_stats(file_stats: List[Dict[str, Any]]) -> Dict[str, Any]:
    aggregate = {
        "num_files": len(file_stats),
        "sentences": 0,
        "entities": 0,
        **init_label_stats(),
        "span_text_sources": {
            "character_offsets": 0,
            "token_join_fallback": 0,
        },
        "by_label": {},
    }

    additive_keys = [
        "sentences",
        "entities",
        "matched_entities",
        "unmatched_entities",
        "concept_ambiguous_entities",
        "matched_entities_via_snomed",
        "matched_entities_via_snogit",
        "matched_entities_via_both",
        "matched_entities_with_snomed_synonym_match",
        "matched_entities_with_snomed_fsn_match",
        "matched_entities_with_concept_active_available",
        "matched_entities_with_active_concept",
        "matched_entities_with_inactive_concept",
        "matched_entities_with_unknown_snogit_concept_in_snomed",
        "total_snomed_description_matches",
        "total_snogit_term_matches",
        "total_unique_concept_matches",
        "matched_entities_with_levenshtein_snomed_candidate",
        "matched_entities_with_levenshtein_snogit_candidate",
    ]

    for stats in file_stats:
        for key in additive_keys:
            aggregate[key] += stats.get(key, 0)

        for source, count in stats.get("span_text_sources", {}).items():
            aggregate["span_text_sources"][source] = (
                aggregate["span_text_sources"].get(source, 0) + count
            )

        for label, label_stats in stats.get("by_label", {}).items():
            if label not in aggregate["by_label"]:
                aggregate["by_label"][label] = init_label_stats()

            for key in additive_keys:
                if key in aggregate["by_label"][label]:
                    aggregate["by_label"][label][key] += label_stats.get(key, 0)

    finalize_rates(aggregate)

    for label_stats in aggregate["by_label"].values():
        finalize_rates(label_stats)

    return aggregate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lexical grounding baseline using SNOMED German + SNOGIT."
    )
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="YAML or JSON config file.",
    )
    return parser.parse_args()


def main() -> None:
    increase_csv_field_size_limit()

    args = parse_args()

    print(f"Loading config from {args.config}", file=sys.stderr)
    config = build_config(args.config)

    print("Discovering input files...", file=sys.stderr)
    input_files = discover_input_files(config)

    print("Loading SNOMED concept activeness...", file=sys.stderr)
    concept_active, concept_stats = load_snomed_concept_activeness(config)

    print("Loading SNOMED descriptions...", file=sys.stderr)
    snomed_term_lookup, snomed_concepts, snomed_description_stats = (
        load_snomed_descriptions(
            config=config,
            concept_active=concept_active,
        )
    )

    print("Loading SNOGIT terms...", file=sys.stderr)
    snogit_lookup, snogit_stats = load_snogit(config)

    print("Building length indices for SNOMED and SNOGIT...", file=sys.stderr)
    snomed_length_index = build_length_index(snomed_term_lookup.keys())
    snogit_length_index = build_length_index(snogit_lookup.keys())

    print("Grounding datasets...", file=sys.stderr)
    file_grounding_stats: List[Dict[str, Any]] = []

    print(f"Processing {len(input_files)} input files...", file=sys.stderr)
    n = 0
    for input_file in input_files:
        output_file = output_path_for_input_file(
            input_file=input_file,
            config=config,
        )
        print(f"Processing file {n+1}/{len(input_files)}: {input_file} -> {output_file}", file=sys.stderr)
        n += 1

        file_stats = ground_dataset(
            config=config,
            input_file=input_file,
            output_file=output_file,
            snomed_term_lookup=snomed_term_lookup,
            snomed_length_index=snomed_length_index,
            snogit_lookup=snogit_lookup,
            snogit_length_index=snogit_length_index,
            snomed_concepts=snomed_concepts,
        )

        file_grounding_stats.append(file_stats)

    print("Aggregating grounding stats across files...", file=sys.stderr)
    grounding_aggregate_stats = aggregate_file_stats(file_grounding_stats)

    print("Saving stats...", file=sys.stderr)
    stats = {
        "config_path": str(args.config),
        "io": {
            "input_path": str(config.input_path),
            "output_path": str(config.output_path),
            "input_glob": config.input_glob,
            "output_suffix": config.output_suffix,
            "num_input_files": len(input_files),
            "input_files": [str(path) for path in input_files],
        },
        "grounding": {
            "aggregate": grounding_aggregate_stats,
            "files": file_grounding_stats,
        },
        "matching": {
            "method": "exact_or_levenshtein_lexical_match_after_normalization",
            "normalization": normalization_config_to_json(config),
            "levenshtein": {
                "enabled": config.levenshtein_enabled,
                "configured_max_distance": config.levenshtein_max_distance,
                "relative_distance": config.levenshtein_relative_distance,
                "formula": (
                    "min(configured_max_distance, "
                    "floor(len(normalized_entity) * relative_distance))"
                ),
            },
            "snomed_length_index_num_lengths": len(snomed_length_index),
            "snogit_length_index_num_lengths": len(snogit_length_index),
        },
        "snomed": {
            "concepts": concept_stats,
            "descriptions": snomed_description_stats,
        },
        "snogit": snogit_stats,
    }

    print(f"Saving stats to {config.stats_output_path}...", file=sys.stderr)
    config.stats_output_path.parent.mkdir(parents=True, exist_ok=True)
    config.stats_output_path.write_text(
        json.dumps(stats, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps(stats, indent=2, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()