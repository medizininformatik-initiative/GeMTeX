"""Check whether external document text is represented in an annotation store."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import sqlite3
from typing import Optional, Union

from ..cli import set_log_level


@dataclasses.dataclass(frozen=True)
class AnnotationStoreDocumentMatch:
    site: str
    export_file: str
    batch_index: Optional[int]
    batch_total: Optional[int]
    document_name: str
    view_kind: str
    annotator: str
    annotation_views: int
    annotations: int


@dataclasses.dataclass(frozen=True)
class AnnotationStoreDocumentCheckResult:
    document_path: pathlib.Path
    text_hash: str
    matched: bool
    matches: list[AnnotationStoreDocumentMatch]


def run_check_annotation_store_document(
    store: Union[str, pathlib.Path],
    document: Union[str, pathlib.Path],
    encoding: str,
    report: Optional[Union[str, pathlib.Path]],
    log_level: str,
) -> AnnotationStoreDocumentCheckResult:
    """Hash an external document and look it up in document_hashes."""
    set_log_level(log_level)
    store = pathlib.Path(store)
    document = pathlib.Path(document)
    text = document.read_text(encoding=encoding)
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    with sqlite3.connect(store) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            select
              e.site,
              e.filename as export_file,
              e.batch_index,
              e.batch_total,
              d.document_name,
              av.view_kind,
              av.annotator,
              count(distinct av.id) as annotation_views,
              count(a.id) as annotations
            from document_hashes dh
            join annotation_views av on av.document_hash_id = dh.id
            join documents d on d.id = av.document_id
            join exports e on e.id = av.export_id
            left join annotations a on a.view_id = av.id
            where dh.text_hash = ?
            group by
              e.site,
              e.filename,
              e.batch_index,
              e.batch_total,
              d.document_name,
              av.view_kind,
              av.annotator
            order by
              e.site,
              e.filename,
              d.document_name,
              av.view_kind,
              av.annotator
            """,
            (text_hash,),
        ).fetchall()

    matches = [
        AnnotationStoreDocumentMatch(
            site=row["site"],
            export_file=row["export_file"],
            batch_index=row["batch_index"],
            batch_total=row["batch_total"],
            document_name=row["document_name"],
            view_kind=row["view_kind"] or "",
            annotator=row["annotator"] or "",
            annotation_views=int(row["annotation_views"]),
            annotations=int(row["annotations"]),
        )
        for row in rows
    ]
    result = AnnotationStoreDocumentCheckResult(
        document_path=document,
        text_hash=text_hash,
        matched=bool(matches),
        matches=matches,
    )
    if report is not None:
        pathlib.Path(report).write_text(
            json.dumps(_result_as_dict(result), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return result


def _result_as_dict(result: AnnotationStoreDocumentCheckResult) -> dict:
    return {
        "document_path": str(result.document_path),
        "text_hash": result.text_hash,
        "matched": result.matched,
        "matches": [dataclasses.asdict(match) for match in result.matches],
    }
