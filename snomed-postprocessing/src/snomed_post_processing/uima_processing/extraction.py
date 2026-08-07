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


def get_annotations_from_document(
    document: Union[cassis.Cas, str, pathlib.Path],
    annotation_types: list[str] = None,
    id_prefix: str = "http://snomed.info/id/",
    ignore_overlap_types: Optional[list[str]] = None,
    ignore_overlap_mode: str = "overlap",
) -> DocumentAnnotations:
    if not annotation_types:
        annotation_types = ["gemtex.Concept"]
    if ignore_overlap_types is None:
        ignore_overlap_types = []
    id_prefix = id_prefix + "/" if not id_prefix.endswith("/") else id_prefix
    id_prefix = id_prefix.lower()

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
                _id = annotation.get("id")
                if _id is None:
                    codes.append(np.nan)
                else:
                    _id = str(_id).strip().lower().removeprefix(id_prefix).strip()
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
