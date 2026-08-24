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
import pathlib
import re
import zipfile
from typing import Iterable, Optional, Sequence, Union

import h5py
import numpy as np

from ..hdf5_handling.policy import read_concepts, read_policy_indices, require_bm25_ready

SCHEMA_NAME = "snomed-post-processing.snogit-sidecar"
SCHEMA_VERSION = "1"
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
    """Summary of an on-demand sidecar build."""

    output_path: pathlib.Path
    selected_members: tuple[str, ...]
    rows_read: int
    rows_kept: int
    rows_written: int
    rows_skipped_unknown_concept: int
    rows_skipped_policy: int
    rows_skipped_empty_term: int
    duplicate_rows: int


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

        pending_indices: list[int] = []
        pending_terms: list[str] = []

        def flush() -> None:
            if not pending_indices:
                return
            start = int(concept_index_ds.shape[0])
            end = start + len(pending_indices)
            concept_index_ds.resize((end,))
            term_ds.resize((end,))
            concept_index_ds[start:end] = np.asarray(pending_indices, dtype=np.int64)
            term_ds[start:end] = np.asarray(pending_terms, dtype=object)
            counters["rows_written"] += len(pending_indices)
            pending_indices.clear()
            pending_terms.clear()

        with zipfile.ZipFile(snogit_zip_path) as archive:
            for member in selected:
                with archive.open(member) as raw_file:
                    for raw_line in raw_file:
                        counters["rows_read"] += 1
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
                        if max_terms_per_concept is not None:
                            count = per_concept_counts.get(concept_idx, 0)
                            if count >= max_terms_per_concept:
                                counters["duplicate_rows"] += 1
                                continue
                            per_concept_counts[concept_idx] = count + 1
                        seen.add(key)
                        counters["rows_kept"] += 1
                        pending_indices.append(int(concept_idx))
                        pending_terms.append(term)
                        if len(pending_indices) >= chunk_size:
                            flush()
        flush()
        _store_counter_attrs(sidecar["metadata"], counters)

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
    )


def read_snogit_sidecar_terms(
    sidecar_path: Union[str, pathlib.Path],
    *,
    hdf5_path: Optional[Union[str, pathlib.Path]] = None,
    strict: bool = True,
) -> SnogitSidecarTerms:
    """Read terms from a SNOGIT HDF5 sidecar and optionally validate it."""
    sidecar_path = pathlib.Path(sidecar_path)
    with h5py.File(sidecar_path, "r") as sidecar:
        if _attr(sidecar["schema"], "name") != SCHEMA_NAME:
            raise ValueError(f"Unsupported SNOGIT sidecar schema: {_attr(sidecar['schema'], 'name')!r}")
        if _attr(sidecar["schema"], "version") != SCHEMA_VERSION:
            raise ValueError(f"Unsupported SNOGIT sidecar schema version: {_attr(sidecar['schema'], 'version')!r}")
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
