"""Extract annotation-store occurrences from CAS views."""

from __future__ import annotations

import hashlib
import json
from typing import Iterator, Optional

import cassis

from .models import AnnotationOccurrence, CasView
from .snomed_lookup import SnomedLookup


def normalize_sctid(raw_id, *, id_prefix: str = "http://snomed.info/id/") -> Optional[str]:
    """Normalize an annotation id feature to a bare SCTID-like string."""
    if raw_id is None:
        return None
    value = str(raw_id).strip()
    if value.lower() in {"", "null", "none", "nan"}:
        return None
    prefix = id_prefix if id_prefix.endswith("/") else id_prefix + "/"
    if value.lower().startswith(prefix.lower()):
        value = value[len(prefix) :]
    value = value.strip()
    return value or None


def iter_annotation_occurrences(
    view: CasView,
    snomed_lookup: SnomedLookup,
    *,
    annotation_types: list[str],
    id_prefix: str = "http://snomed.info/id/",
) -> Iterator[AnnotationOccurrence]:
    """Yield enriched annotation occurrences from selected CAS layers."""
    for layer in annotation_types:
        try:
            annotations = list(view.cas.select(layer))
        except Exception:
            continue
        for annotation in annotations:
            try:
                raw_id = _feature(annotation, "id")
                literal = _feature(annotation, "literal")
                sctid = normalize_sctid(raw_id, id_prefix=id_prefix)
                concept = snomed_lookup.get(sctid)
                covered_text = annotation.get_covered_text()
                occurrence_payload = {
                    "export_path": str(view.export_path.resolve()),
                    "site": view.site,
                    "batch_index": view.batch_index,
                    "batch_total": view.batch_total,
                    "document_name": view.document_name,
                    "view_kind": view.view_kind,
                    "annotator": view.annotator,
                    "cas_path": view.cas_path,
                    "layer": layer,
                    "begin_offset": int(annotation.begin),
                    "end_offset": int(annotation.end),
                    "sctid": sctid,
                    "covered_text": covered_text,
                    "raw_id": None if raw_id is None else str(raw_id),
                    "literal": None if literal is None else str(literal),
                }
                yield AnnotationOccurrence(
                    layer=layer,
                    begin_offset=int(annotation.begin),
                    end_offset=int(annotation.end),
                    covered_text=covered_text,
                    sctid=sctid,
                    fsn=concept.fsn if concept else None,
                    semantic_tag=concept.semantic_tag if concept else None,
                    active=concept.active if concept else None,
                    raw_id=None if raw_id is None else str(raw_id),
                    literal=None if literal is None else str(literal),
                    annotation_hash=_hash_payload(occurrence_payload),
                )
            except Exception:
                continue


def cas_document_text(cas: cassis.Cas) -> Optional[str]:
    """Return the CAS sofa string if available."""
    text = getattr(cas, "sofa_string", None)
    if text is None:
        return None
    return str(text)


def document_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _feature(annotation, name: str):
    try:
        return annotation.get(name)
    except Exception:
        return None


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
