"""Optional SNOGIT/interface terminology sidecar support for BM25 fallback.

The sidecar is a small HDF5 file built on demand from a selected SNOGIT release
ZIP and one specific SNOMED policy HDF5. It intentionally stores only the rows
needed by runtime BM25:

``/terms/concept_index``
    Index into the main HDF5 ``/concepts`` arrays.
``/terms/term``
    German/interface term text.

Because concept indices are only meaningful for the exact main HDF5 view used at
build time, the sidecar also stores compatibility metadata and hashes.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import math
import pathlib
import re
import zipfile
from collections import Counter, defaultdict
from typing import Callable, Iterable, Optional, Sequence, Union

import h5py
import numpy as np

from ..hdf5_handling.policy import read_concepts, read_policy_indices, require_bm25_ready
from .semantic_models import Bm25Hit
from .semantic_text import _tokenize

SCHEMA_NAME = "snomed-post-processing.snogit-sidecar"
SCHEMA_VERSION = "2"
_STRING_DTYPE = h5py.string_dtype(encoding="utf-8")
_DEFAULT_CHUNK_SIZE = 100_000


@dataclasses.dataclass(frozen=True)
class SnogitZipMember:
    """A candidate terminology member inside a SNOGIT release ZIP."""

    name: str
    kind: str
    date: str
    recommended_default: bool = False


@dataclasses.dataclass(frozen=True)
class SnogitSidecarTerms:
    """Runtime terms read from a compatible SNOGIT sidecar."""

    concept_index: np.ndarray
    term: tuple[str, ...]
    metadata: dict[str, object]


@dataclasses.dataclass(frozen=True)
class SnogitSidecarBuildResult:
    """Summary of a processed SNOGIT cache build."""

    output_path: pathlib.Path
    selected_members: tuple[str, ...]
    rows_read: int
    rows_kept: int
    rows_written: int
    rows_skipped_unknown_concept: int
    rows_skipped_policy: int
    rows_skipped_empty_term: int
    duplicate_rows: int
    vocab_size: int = 0
    postings_count: int = 0


@dataclasses.dataclass(frozen=True)
class SnogitBm25Hit:
    """A BM25 hit from the HDF5-backed SNOGIT inverted index."""

    term_row: int
    concept_index: int
    term: str
    score: float
    matched_query_tokens: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class MainHdf5Fingerprint:
    """Compatibility fingerprint for concept-index sidecars."""

    release_date: str
    policy_date: str
    rf2_view: str
    concept_count: int
    policy_candidate_count: int
    concept_codes_hash: str
    policy_candidate_hash: str


def list_snogit_zip_members(zip_path: Union[str, pathlib.Path]) -> list[SnogitZipMember]:
    """List supported ``.dat`` terminology files in a SNOGIT release ZIP."""
    members: list[SnogitZipMember] = []
    with zipfile.ZipFile(zip_path) as archive:
        for name in sorted(archive.namelist()):
            base = pathlib.PurePosixPath(name).name
            if not base.lower().endswith(".dat"):
                continue
            kind = _source_kind(base)
            if kind not in {"snogit", "snogit_elga", "snomed_latin"}:
                continue
            members.append(SnogitZipMember(name=name, kind=kind, date=_member_date(base)))

    default = default_snogit_members(members)
    default_names = {member.name for member in default}
    return [
        dataclasses.replace(member, recommended_default=member.name in default_names)
        for member in members
    ]


def default_snogit_members(members: Sequence[SnogitZipMember]) -> tuple[SnogitZipMember, ...]:
    """Return the newest general ``SNOGIT_*.dat`` member, excluding ELGA/Latin."""
    general = [member for member in members if member.kind == "snogit"]
    if not general:
        return ()
    newest = max(general, key=lambda member: (member.date, member.name))
    return (newest,)


def build_snogit_sidecar(
    *,
    hdf5_path: Union[str, pathlib.Path],
    snogit_zip_path: Union[str, pathlib.Path],
    output_path: Union[str, pathlib.Path],
    members: Optional[Sequence[str]] = None,
    max_terms_per_concept: Optional[int] = None,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    progress_callback: Optional[Callable[[dict[str, object]], None]] = None,
) -> SnogitSidecarBuildResult:
    """Build a minimal filtered HDF5 sidecar from selected SNOGIT ZIP members.

    If ``members`` is omitted, the newest general ``SNOGIT_*.dat`` file in the
    archive is used. Rows are filtered to concepts that are active, whitelisted,
    and not blacklisted in the selected main HDF5.
    """
    hdf5_path = pathlib.Path(hdf5_path)
    snogit_zip_path = pathlib.Path(snogit_zip_path)
    output_path = pathlib.Path(output_path)

    with h5py.File(hdf5_path, "r") as h5_file:
        require_bm25_ready(h5_file)
        concepts = read_concepts(h5_file)
        whitelist_indices = read_policy_indices(h5_file, "whitelist")
        blacklist_indices = read_policy_indices(h5_file, "blacklist")
        allowed_indices = frozenset(
            idx
            for idx in whitelist_indices
            if 0 <= idx < len(concepts.codes)
            and bool(concepts.active[idx])
            and idx not in blacklist_indices
        )
        fingerprint = fingerprint_main_hdf5(h5_file, allowed_indices=allowed_indices)

    zip_members = list_snogit_zip_members(snogit_zip_path)
    if members is None:
        selected = tuple(member.name for member in default_snogit_members(zip_members))
    else:
        selected = tuple(members)
    if not selected:
        raise ValueError("No SNOGIT ZIP member selected; choose at least one .dat member.")

    available = {member.name for member in zip_members}
    missing = [member for member in selected if member not in available]
    if missing:
        raise ValueError("Selected SNOGIT member(s) not found in ZIP: " + ", ".join(missing))

    selected_member_sizes: dict[str, int] = {}
    with zipfile.ZipFile(snogit_zip_path) as archive:
        for member in selected:
            selected_member_sizes[member] = int(archive.getinfo(member).file_size)
    total_selected_bytes = sum(selected_member_sizes.values())
    processed_bytes = 0

    def report_progress(**payload: object) -> None:
        if progress_callback is not None:
            progress_callback(payload)

    report_progress(
        phase="start",
        selected_members=selected,
        total_bytes=total_selected_bytes,
        processed_bytes=processed_bytes,
        progress=0.0,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    counters = {
        "rows_read": 0,
        "rows_kept": 0,
        "rows_written": 0,
        "rows_skipped_unknown_concept": 0,
        "rows_skipped_policy": 0,
        "rows_skipped_empty_term": 0,
        "duplicate_rows": 0,
    }
    seen: set[tuple[int, str]] = set()
    per_concept_counts: dict[int, int] = {}

    with h5py.File(output_path, "w") as sidecar:
        _write_metadata(
            sidecar,
            hdf5_path=hdf5_path,
            snogit_zip_path=snogit_zip_path,
            selected_members=selected,
            fingerprint=fingerprint,
            max_terms_per_concept=max_terms_per_concept,
        )
        terms_group = sidecar.create_group("terms")
        concept_index_ds = terms_group.create_dataset(
            "concept_index",
            shape=(0,),
            maxshape=(None,),
            chunks=(max(1, min(chunk_size, _DEFAULT_CHUNK_SIZE)),),
            dtype=np.int64,
            compression="gzip",
            compression_opts=4,
            shuffle=True,
        )
        term_ds = terms_group.create_dataset(
            "term",
            shape=(0,),
            maxshape=(None,),
            chunks=(max(1, min(chunk_size, _DEFAULT_CHUNK_SIZE)),),
            dtype=_STRING_DTYPE,
        )
        length_ds = terms_group.create_dataset(
            "length",
            shape=(0,),
            maxshape=(None,),
            chunks=(max(1, min(chunk_size, _DEFAULT_CHUNK_SIZE)),),
            dtype=np.int32,
            compression="gzip",
            compression_opts=4,
            shuffle=True,
        )

        pending_indices: list[int] = []
        pending_terms: list[str] = []
        pending_lengths: list[int] = []
        postings: dict[str, list[tuple[int, int]]] = defaultdict(list)

        def flush() -> None:
            if not pending_indices:
                return
            start = int(concept_index_ds.shape[0])
            end = start + len(pending_indices)
            concept_index_ds.resize((end,))
            term_ds.resize((end,))
            length_ds.resize((end,))
            concept_index_ds[start:end] = np.asarray(pending_indices, dtype=np.int64)
            term_ds[start:end] = np.asarray(pending_terms, dtype=object)
            length_ds[start:end] = np.asarray(pending_lengths, dtype=np.int32)
            counters["rows_written"] += len(pending_indices)
            pending_indices.clear()
            pending_terms.clear()
            pending_lengths.clear()

        with zipfile.ZipFile(snogit_zip_path) as archive:
            for member in selected:
                report_progress(
                    phase="parsing",
                    member=member,
                    selected_members=selected,
                    total_bytes=total_selected_bytes,
                    processed_bytes=processed_bytes,
                    progress=(processed_bytes / total_selected_bytes if total_selected_bytes else 0.0),
                    **counters,
                )
                with archive.open(member) as raw_file:
                    for raw_line in raw_file:
                        counters["rows_read"] += 1
                        processed_bytes += len(raw_line)
                        if counters["rows_read"] % max(1, chunk_size) == 0:
                            report_progress(
                                phase="parsing",
                                member=member,
                                selected_members=selected,
                                total_bytes=total_selected_bytes,
                                processed_bytes=processed_bytes,
                                progress=(processed_bytes / total_selected_bytes if total_selected_bytes else 0.0),
                                **counters,
                            )
                        parsed = _parse_dat_line(raw_line)
                        if parsed is None:
                            counters["rows_skipped_empty_term"] += 1
                            continue
                        concept_code, term = parsed
                        concept_idx = concepts.code_to_index.get(concept_code)
                        if concept_idx is None:
                            counters["rows_skipped_unknown_concept"] += 1
                            continue
                        if concept_idx not in allowed_indices:
                            counters["rows_skipped_policy"] += 1
                            continue
                        normalized = _normalize_term(term)
                        if not normalized:
                            counters["rows_skipped_empty_term"] += 1
                            continue
                        key = (concept_idx, normalized)
                        if key in seen:
                            counters["duplicate_rows"] += 1
                            continue
                        tokens = _tokenize(term)
                        if not tokens:
                            counters["rows_skipped_empty_term"] += 1
                            continue
                        if max_terms_per_concept is not None:
                            count = per_concept_counts.get(concept_idx, 0)
                            if count >= max_terms_per_concept:
                                counters["duplicate_rows"] += 1
                                continue
                            per_concept_counts[concept_idx] = count + 1
                        row_id = counters["rows_kept"]
                        seen.add(key)
                        counters["rows_kept"] += 1
                        token_counts = Counter(tokens)
                        for token, count in token_counts.items():
                            postings[token].append((row_id, int(count)))
                        pending_indices.append(int(concept_idx))
                        pending_terms.append(term)
                        pending_lengths.append(len(tokens))
                        if len(pending_indices) >= chunk_size:
                            flush()
        flush()
        report_progress(
            phase="writing_index",
            selected_members=selected,
            total_bytes=total_selected_bytes,
            processed_bytes=processed_bytes,
            progress=1.0,
            **counters,
        )
        vocab_size, postings_count = _write_inverted_index(
            sidecar,
            postings=postings,
            document_count=counters["rows_written"],
            lengths=np.asarray(length_ds[:], dtype=np.int32),
        )
        sidecar["metadata"].attrs["vocab_size"] = int(vocab_size)
        sidecar["metadata"].attrs["postings_count"] = int(postings_count)
        _store_counter_attrs(sidecar["metadata"], counters)
        report_progress(
            phase="complete",
            selected_members=selected,
            total_bytes=total_selected_bytes,
            processed_bytes=processed_bytes,
            progress=1.0,
            vocab_size=vocab_size,
            postings_count=postings_count,
            **counters,
        )

    return SnogitSidecarBuildResult(
        output_path=output_path,
        selected_members=selected,
        rows_read=counters["rows_read"],
        rows_kept=counters["rows_kept"],
        rows_written=counters["rows_written"],
        rows_skipped_unknown_concept=counters["rows_skipped_unknown_concept"],
        rows_skipped_policy=counters["rows_skipped_policy"],
        rows_skipped_empty_term=counters["rows_skipped_empty_term"],
        duplicate_rows=counters["duplicate_rows"],
        vocab_size=vocab_size,
        postings_count=postings_count,
    )


def search_snogit_sidecar_bm25(
    sidecar_path: Union[str, pathlib.Path],
    query_tokens: Sequence[str],
    *,
    hdf5_path: Optional[Union[str, pathlib.Path]] = None,
    strict: bool = True,
    k1: float = 1.5,
    b: float = 0.75,
    max_hits: int = 50,
    max_postings_per_token: int = 250_000,
    max_candidate_rows: int = 100_000,
) -> list[SnogitBm25Hit]:
    """Search a processed SNOGIT cache using its HDF5 inverted BM25 index.

    Only postings for query tokens are read. The score computation is vectorized
    with NumPy and does not construct the full Python ``BM25Index`` object graph.
    """
    if hdf5_path is not None:
        validate_snogit_sidecar_compatibility(sidecar_path, hdf5_path, strict=strict)
    unique_query_tokens = tuple(dict.fromkeys(token for token in query_tokens if token))
    if not unique_query_tokens:
        return []

    sidecar_path = pathlib.Path(sidecar_path)
    with h5py.File(sidecar_path, "r") as sidecar:
        _require_supported_schema(sidecar)
        if "index" not in sidecar:
            raise ValueError("Processed SNOGIT cache has no HDF5 inverted index; rebuild it with build-snogit-cache.")
        index = sidecar["index"]
        document_count = int(index.attrs.get("document_count", 0))
        avgdl = float(index.attrs.get("average_document_length", 0.0)) or 1e-9
        if document_count <= 0:
            return []
        vocab = tuple(_decode(value) for value in sidecar["index/vocab/token"][:])
        vocab_pos = {token: idx for idx, token in enumerate(vocab)}
        starts = np.asarray(sidecar["index/vocab/postings_start"][:], dtype=np.int64)
        lengths = np.asarray(sidecar["index/vocab/postings_length"][:], dtype=np.int64)
        term_lengths_ds = sidecar["terms/length"]

        token_infos: list[tuple[int, str, int]] = []
        for token in unique_query_tokens:
            vocab_idx = vocab_pos.get(token)
            if vocab_idx is None:
                continue
            postings_length = int(lengths[vocab_idx])
            if postings_length <= 0:
                continue
            token_infos.append((postings_length, token, vocab_idx))
        token_infos.sort(key=lambda item: (item[0], item[1]))

        row_chunks: list[np.ndarray] = []
        contribution_chunks: list[np.ndarray] = []
        matched_tokens_by_row: dict[int, set[str]] = defaultdict(set)
        candidate_rows_seen: set[int] = set()
        for postings_length, token, vocab_idx in token_infos:
            if postings_length > max_postings_per_token:
                continue
            start = int(starts[vocab_idx])
            end = start + postings_length
            rows = np.asarray(sidecar["index/postings/term_row"][start:end], dtype=np.int64)
            if rows.size == 0:
                continue
            rows_set = set(int(row) for row in rows)
            if len(candidate_rows_seen | rows_set) > max_candidate_rows:
                # Too broad for this query. Because tokens are processed from
                # rarest to most common, skip this broad token and keep scoring
                # with the more selective tokens already accepted.
                continue
            candidate_rows_seen.update(rows_set)
            tf = np.asarray(sidecar["index/postings/token_count"][start:end], dtype=np.float64)
            dl = np.asarray(term_lengths_ds[rows], dtype=np.float64)
            idf = math.log(1.0 + (document_count - postings_length + 0.5) / (postings_length + 0.5))
            denominator = tf + float(k1) * (1.0 - float(b) + float(b) * dl / avgdl)
            contribution = idf * tf * (float(k1) + 1.0) / denominator
            row_chunks.append(rows)
            contribution_chunks.append(contribution)
            for row in rows:
                matched_tokens_by_row[int(row)].add(token)

        if not row_chunks:
            return []
        all_rows = np.concatenate(row_chunks)
        all_contributions = np.concatenate(contribution_chunks)
        unique_rows, inverse = np.unique(all_rows, return_inverse=True)
        scores = np.bincount(inverse, weights=all_contributions)
        positive = scores > 0.0
        if not np.any(positive):
            return []
        unique_rows = unique_rows[positive]
        scores = scores[positive]
        hit_count = min(int(max_hits), int(scores.size))
        top_positions = np.argpartition(scores, -hit_count)[-hit_count:]
        ordered_positions = sorted(top_positions, key=lambda pos: (-float(scores[pos]), int(unique_rows[pos])))
        top_rows = np.asarray([unique_rows[pos] for pos in ordered_positions], dtype=np.int64)
        concept_indices = _read_dataset_rows_in_requested_order(sidecar["terms/concept_index"], top_rows)
        terms = tuple(
            _decode(value)
            for value in _read_dataset_rows_in_requested_order(sidecar["terms/term"], top_rows)
        )

    return [
        SnogitBm25Hit(
            term_row=int(row),
            concept_index=int(concept_idx),
            term=term,
            score=float(scores[pos]),
            matched_query_tokens=tuple(sorted(matched_tokens_by_row.get(int(row), set()))),
        )
        for pos, row, concept_idx, term in zip(ordered_positions, top_rows, concept_indices, terms)
    ]


def read_snogit_sidecar_terms(
    sidecar_path: Union[str, pathlib.Path],
    *,
    hdf5_path: Optional[Union[str, pathlib.Path]] = None,
    strict: bool = True,
) -> SnogitSidecarTerms:
    """Read terms from a SNOGIT HDF5 sidecar and optionally validate it."""
    sidecar_path = pathlib.Path(sidecar_path)
    with h5py.File(sidecar_path, "r") as sidecar:
        _require_supported_schema(sidecar)
        metadata = _metadata_dict(sidecar["metadata"])
        concept_index = np.asarray(sidecar["terms/concept_index"][:], dtype=np.int64)
        term = tuple(_decode(value) for value in sidecar["terms/term"][:])

    if hdf5_path is not None:
        validate_snogit_sidecar_compatibility(sidecar_path, hdf5_path, strict=strict)
    return SnogitSidecarTerms(concept_index=concept_index, term=term, metadata=metadata)


def validate_snogit_sidecar_compatibility(
    sidecar_path: Union[str, pathlib.Path],
    hdf5_path: Union[str, pathlib.Path],
    *,
    strict: bool = True,
) -> bool:
    """Validate that a sidecar's concept indices refer to the selected HDF5."""
    with h5py.File(hdf5_path, "r") as h5_file:
        require_bm25_ready(h5_file)
        whitelist_indices = read_policy_indices(h5_file, "whitelist")
        blacklist_indices = read_policy_indices(h5_file, "blacklist")
        active = np.asarray(h5_file["concepts/active"][:], dtype=bool)
        allowed_indices = frozenset(
            idx
            for idx in whitelist_indices
            if 0 <= idx < len(active) and bool(active[idx]) and idx not in blacklist_indices
        )
        expected = fingerprint_main_hdf5(h5_file, allowed_indices=allowed_indices)
    with h5py.File(sidecar_path, "r") as sidecar:
        metadata = _metadata_dict(sidecar["metadata"])
    problems = []
    for field in dataclasses.fields(MainHdf5Fingerprint):
        expected_value = getattr(expected, field.name)
        actual_value = metadata.get(f"main_hdf5_{field.name}")
        if str(actual_value) != str(expected_value):
            problems.append(f"{field.name}: sidecar={actual_value!r}, hdf5={expected_value!r}")
    if problems and strict:
        raise ValueError("SNOGIT sidecar is not compatible with selected HDF5: " + "; ".join(problems))
    return not problems


def fingerprint_main_hdf5(
    h5_file: h5py.File,
    *,
    allowed_indices: Iterable[int],
) -> MainHdf5Fingerprint:
    """Create a stable fingerprint for the main HDF5 concept/policy view."""
    concepts_group = h5_file["concepts"]
    concept_codes = [_decode(value) for value in concepts_group["codes"][:]]
    allowed = tuple(sorted(int(idx) for idx in allowed_indices))
    return MainHdf5Fingerprint(
        release_date=str(concepts_group.attrs.get("release_date", "")),
        policy_date=str(concepts_group.attrs.get("policy_date", "")),
        rf2_view=str(concepts_group.attrs.get("rf2_view", "")),
        concept_count=len(concept_codes),
        policy_candidate_count=len(allowed),
        concept_codes_hash=_hash_strings(concept_codes),
        policy_candidate_hash=_hash_indices_and_codes(allowed, concept_codes),
    )


def _read_dataset_rows_in_requested_order(dataset: h5py.Dataset, rows: np.ndarray) -> np.ndarray:
    """Read arbitrary HDF5 rows while preserving requested order.

    h5py fancy indexing requires increasing indices. BM25 hit rows are ranked by
    score, so sort only for the disk read and restore the score order after.
    """
    rows = np.asarray(rows, dtype=np.int64)
    if rows.size == 0:
        return np.asarray([], dtype=dataset.dtype)
    order = np.argsort(rows, kind="stable")
    sorted_rows = rows[order]
    sorted_values = dataset[sorted_rows]
    restored = np.empty_like(sorted_values)
    restored[order] = sorted_values
    return restored


def _write_inverted_index(
    sidecar: h5py.File,
    *,
    postings: dict[str, list[tuple[int, int]]],
    document_count: int,
    lengths: np.ndarray,
) -> tuple[int, int]:
    """Write token postings arrays for HDF5-backed BM25 retrieval."""
    index = sidecar.create_group("index")
    index.attrs["k1"] = 1.5
    index.attrs["b"] = 0.75
    index.attrs["document_count"] = int(document_count)
    index.attrs["average_document_length"] = float(np.mean(lengths)) if len(lengths) else 0.0
    index.attrs["tokenizer"] = "snomed_post_processing.sanitization.semantic_text._tokenize"

    vocab_tokens = sorted(postings)
    starts = np.empty(len(vocab_tokens), dtype=np.int64)
    posting_lengths = np.empty(len(vocab_tokens), dtype=np.int64)
    total_postings = sum(len(postings[token]) for token in vocab_tokens)
    term_rows = np.empty(total_postings, dtype=np.int64)
    token_counts = np.empty(total_postings, dtype=np.int32)

    cursor = 0
    for token_idx, token in enumerate(vocab_tokens):
        token_postings = sorted(postings[token], key=lambda item: item[0])
        starts[token_idx] = cursor
        posting_lengths[token_idx] = len(token_postings)
        end = cursor + len(token_postings)
        if token_postings:
            rows, counts = zip(*token_postings)
            term_rows[cursor:end] = np.asarray(rows, dtype=np.int64)
            token_counts[cursor:end] = np.asarray(counts, dtype=np.int32)
        cursor = end

    vocab_group = index.create_group("vocab")
    vocab_group.create_dataset("token", data=np.asarray(vocab_tokens, dtype=object), dtype=_STRING_DTYPE)
    vocab_group.create_dataset("postings_start", data=starts, compression="gzip", compression_opts=4, shuffle=True)
    vocab_group.create_dataset("postings_length", data=posting_lengths, compression="gzip", compression_opts=4, shuffle=True)

    postings_group = index.create_group("postings")
    postings_group.create_dataset("term_row", data=term_rows, compression="gzip", compression_opts=4, shuffle=True)
    postings_group.create_dataset("token_count", data=token_counts, compression="gzip", compression_opts=4, shuffle=True)
    return len(vocab_tokens), int(total_postings)


def _require_supported_schema(sidecar: h5py.File) -> None:
    if _attr(sidecar["schema"], "name") != SCHEMA_NAME:
        raise ValueError(f"Unsupported SNOGIT sidecar schema: {_attr(sidecar['schema'], 'name')!r}")
    if _attr(sidecar["schema"], "version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported SNOGIT sidecar schema version: {_attr(sidecar['schema'], 'version')!r}; rebuild the processed SNOGIT cache.")


def _write_metadata(
    sidecar: h5py.File,
    *,
    hdf5_path: pathlib.Path,
    snogit_zip_path: pathlib.Path,
    selected_members: Sequence[str],
    fingerprint: MainHdf5Fingerprint,
    max_terms_per_concept: Optional[int],
) -> None:
    schema = sidecar.create_group("schema")
    schema.attrs["name"] = SCHEMA_NAME
    schema.attrs["version"] = SCHEMA_VERSION
    metadata = sidecar.create_group("metadata")
    metadata.attrs["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    metadata.attrs["main_hdf5_file_name"] = hdf5_path.name
    metadata.attrs["snogit_zip_file_name"] = snogit_zip_path.name
    metadata.attrs["source_selection"] = "default_general_newest" if len(selected_members) == 1 and _source_kind(pathlib.PurePosixPath(selected_members[0]).name) == "snogit" else "explicit"
    metadata.attrs["max_terms_per_concept"] = "" if max_terms_per_concept is None else int(max_terms_per_concept)
    metadata.create_dataset("source_members", data=np.asarray(list(selected_members), dtype=object), dtype=_STRING_DTYPE)
    metadata.create_dataset(
        "source_kinds",
        data=np.asarray([_source_kind(pathlib.PurePosixPath(member).name) for member in selected_members], dtype=object),
        dtype=_STRING_DTYPE,
    )
    for field in dataclasses.fields(MainHdf5Fingerprint):
        metadata.attrs[f"main_hdf5_{field.name}"] = getattr(fingerprint, field.name)


def _store_counter_attrs(metadata: h5py.Group, counters: dict[str, int]) -> None:
    for key, value in counters.items():
        metadata.attrs[key] = int(value)


def _metadata_dict(metadata: h5py.Group) -> dict[str, object]:
    result = {key: _decode(value) for key, value in metadata.attrs.items()}
    if "source_members" in metadata:
        result["source_members"] = tuple(_decode(value) for value in metadata["source_members"][:])
    if "source_kinds" in metadata:
        result["source_kinds"] = tuple(_decode(value) for value in metadata["source_kinds"][:])
    return result


def _attr(group: h5py.Group, name: str) -> str:
    if name not in group.attrs:
        return ""
    return _decode(group.attrs[name])


def _parse_dat_line(raw_line: bytes) -> Optional[tuple[str, str]]:
    line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
    if not line:
        return None
    parts = line.split("\t")
    if len(parts) >= 4:
        concept_code, term = parts[0].strip(), parts[3].strip()
    elif len(parts) >= 3:
        concept_code, term = parts[0].strip(), parts[2].strip()
    else:
        return None
    if not concept_code or not term:
        return None
    return concept_code, term


def _source_kind(base_name: str) -> str:
    upper = base_name.upper()
    if upper.startswith("SNOGIT_ELGA_"):
        return "snogit_elga"
    if upper.startswith("SNOGIT_"):
        return "snogit"
    if upper.startswith("SNOMED_LATIN_"):
        return "snomed_latin"
    return "unknown"


def _member_date(base_name: str) -> str:
    match = re.search(r"(20\d{6})", base_name)
    return match.group(1) if match else ""


def _normalize_term(term: str) -> str:
    return " ".join(term.casefold().split())


def _hash_strings(values: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "little"))
        digest.update(encoded)
    return digest.hexdigest()


def _hash_indices_and_codes(indices: Sequence[int], concept_codes: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for idx in indices:
        digest.update(int(idx).to_bytes(8, "little", signed=True))
        encoded = concept_codes[int(idx)].encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "little"))
        digest.update(encoded)
    return digest.hexdigest()


def _decode(value) -> str:
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8")
    return str(value)
