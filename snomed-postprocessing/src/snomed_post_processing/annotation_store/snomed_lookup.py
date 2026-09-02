"""SNOMED metadata lookup from the compact HDF5 concept store."""

from __future__ import annotations

import pathlib
from typing import Optional, Union

import h5py

from .models import ConceptMetadata


def _decode(value) -> str:
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8")
    return str(value)


class SnomedLookup:
    """In-memory SCTID to FSN/semantic-tag/active lookup."""

    def __init__(self, concepts: dict[str, ConceptMetadata]):
        self._concepts = concepts

    @classmethod
    def from_hdf5(cls, path: Union[str, pathlib.Path]) -> "SnomedLookup":
        path = pathlib.Path(path)
        with h5py.File(path, "r") as h5_file:
            for required in (
                "concepts/codes",
                "concepts/fsn",
                "concepts/semantic_tag_id",
                "concepts/semantic_tags",
                "concepts/active",
            ):
                if required not in h5_file:
                    raise ValueError(f"HDF5 file is missing required dataset: {required}")

            codes = h5_file["concepts/codes"][:]
            fsns = h5_file["concepts/fsn"][:]
            semantic_tag_ids = h5_file["concepts/semantic_tag_id"][:]
            semantic_tags = h5_file["concepts/semantic_tags"][:]
            active = h5_file["concepts/active"][:]

        decoded_tags = [_decode(tag) for tag in semantic_tags]
        concepts: dict[str, ConceptMetadata] = {}
        for code, fsn, tag_id, is_active in zip(codes, fsns, semantic_tag_ids, active):
            sctid = _decode(code)
            tag_idx = int(tag_id)
            semantic_tag: Optional[str] = None
            if 0 <= tag_idx < len(decoded_tags):
                semantic_tag = decoded_tags[tag_idx]
            concepts[sctid] = ConceptMetadata(
                sctid=sctid,
                fsn=_decode(fsn),
                semantic_tag=semantic_tag,
                active=bool(is_active),
            )
        return cls(concepts)

    def get(self, sctid: Optional[str]) -> Optional[ConceptMetadata]:
        if not sctid:
            return None
        return self._concepts.get(str(sctid))
