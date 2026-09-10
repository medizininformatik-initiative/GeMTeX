"""Annotation extraction from CAS documents."""

from __future__ import annotations

import logging
import pathlib
from typing import Optional, Union

import cassis
import numpy as np

from .io import _load_document
from .models import DocumentAnnotations, IgnoreOverlap


def spans_match(
    target: tuple[int, int], ignore: tuple[int, int], mode: str = "overlap"
) -> bool:
    target_begin, target_end = target
    ignore_begin, ignore_end = ignore
    if mode == "exact":
        return target_begin == ignore_begin and target_end == ignore_end
    if mode == "covered-by":
        return target_begin >= ignore_begin and target_end <= ignore_end
    if mode == "contains":
        return target_begin <= ignore_begin and target_end >= ignore_end
    if mode == "overlap":
        return target_begin < ignore_end and ignore_begin < target_end
    raise ValueError(f"Unknown overlap mode: '{mode}'.")


def _safe_select(document: cassis.Cas, type_: str):
    try:
        yield from document.select(type_)
    except Exception as e:
        logging.debug(f"Could not select annotations of type '{type_}': {e}")


def _normalized_id_prefix(id_prefix: str) -> str:
    prefix = str(id_prefix or "").strip().lower()
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return prefix


def _normalize_annotation_id(value: object, *, id_prefix: str) -> str:
    text = str(value).strip().lower()
    if id_prefix:
        text = text.removeprefix(id_prefix)
    return text.strip()


def get_annotations_from_document(
    document: Union[cassis.Cas, str, pathlib.Path],
    annotation_types: list[str] = None,
    id_prefix: str = "http://snomed.info/id/",
    id_feature: str = "id",
    ignore_overlap_types: Optional[list[str]] = None,
    ignore_overlap_mode: str = "overlap",
) -> DocumentAnnotations:
    if not annotation_types:
        annotation_types = ["gemtex.Concept"]
    if ignore_overlap_types is None:
        ignore_overlap_types = []
    id_prefix = _normalized_id_prefix(id_prefix)
    id_feature = str(id_feature or "id").strip() or "id"

    if not isinstance(document, cassis.Cas):
        document = _load_document(document)

    ignore_spans: list[IgnoreOverlap] = []
    for type_ in ignore_overlap_types:
        for annotation in _safe_select(document, type_):
            try:
                ignore_spans.append(
                    IgnoreOverlap(
                        layer=type_,
                        offset=(annotation.begin, annotation.end),
                        text=annotation.get_covered_text(),
                    )
                )
            except Exception:
                pass

    codes, offsets, text, layers, ignore_mask, ignore_overlaps = [], [], [], [], [], []
    for type_ in annotation_types:
        for annotation in _safe_select(document, type_):
            try:
                _id = annotation.get(id_feature)
                if _id is None:
                    codes.append(np.nan)
                else:
                    _id = _normalize_annotation_id(_id, id_prefix=id_prefix)
                    if _id in {"", "null", "none", "nan"}:
                        codes.append(np.nan)
                    else:
                        codes.append(_id)

                offset = (annotation.begin, annotation.end)
                overlaps = [
                    ignore
                    for ignore in ignore_spans
                    if spans_match(offset, ignore.offset, ignore_overlap_mode)
                ]
                offsets.append(offset)
                text.append(annotation.get_covered_text())
                layers.append(type_)
                ignore_mask.append(len(overlaps) > 0)
                ignore_overlaps.append(overlaps)
            except Exception:
                pass
    return DocumentAnnotations(
        snomed_codes=np.asarray(codes, dtype="bytes"),
        offsets=np.asarray(offsets, dtype="i,i"),
        text=np.asarray(text, dtype=np.dtypes.StringDType),
        layers=np.asarray(layers, dtype=np.dtypes.StringDType),
        length=len(codes),
        ignore_mask=np.asarray(ignore_mask, dtype=bool),
        ignore_overlaps=ignore_overlaps,
    )
