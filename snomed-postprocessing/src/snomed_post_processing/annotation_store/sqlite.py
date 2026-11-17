"""SQLite writer for annotation-store imports."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sqlite3
from typing import Optional, Union

from .models import AnnotationOccurrence, ConceptMetadata, ExportMetadata

SCHEMA_SQL = """
pragma foreign_keys = on;

create table if not exists exports(
  id integer primary key,
  site text not null,
  path text not null,
  filename text not null,
  batch_index integer,
  batch_total integer,
  batch_label text,
  imported_at text not null,
  unique(path)
);

create table if not exists documents(
  id integer primary key,
  document_name text not null unique
);

create table if not exists document_hashes(
  id integer primary key,
  text_hash text not null unique
);

create table if not exists document_texts(
  id integer primary key,
  document_hash_id integer not null unique,
  text text not null,
  foreign key(document_hash_id) references document_hashes(id)
);

create table if not exists annotation_views(
  id integer primary key,
  export_id integer not null,
  document_id integer not null,
  document_hash_id integer,
  document_text_id integer,
  view_kind text not null,
  annotator text not null,
  cas_path text not null,
  unique(export_id, document_id, view_kind, annotator, cas_path),
  foreign key(export_id) references exports(id),
  foreign key(document_id) references documents(id),
  foreign key(document_hash_id) references document_hashes(id),
  foreign key(document_text_id) references document_texts(id)
);

create table if not exists snomed_concepts(
  sctid text primary key,
  fsn text,
  semantic_tag text,
  active integer
);

create table if not exists annotations(
  id integer primary key,
  document_hash_id integer,
  layer text not null,
  begin_offset integer not null,
  end_offset integer not null,
  covered_text text,
  sctid text,
  fsn text,
  semantic_tag text,
  active integer,
  raw_id text,
  literal text,
  annotation_hash text not null unique,
  foreign key(document_hash_id) references document_hashes(id),
  foreign key(sctid) references snomed_concepts(sctid)
);

create table if not exists annotation_occurrence_links(
  id integer primary key,
  annotation_id integer not null,
  view_id integer not null,
  occurrence_hash text not null unique,
  foreign key(annotation_id) references annotations(id),
  foreign key(view_id) references annotation_views(id)
);
create index if not exists idx_occurrence_links_annotation on annotation_occurrence_links(annotation_id);
create index if not exists idx_occurrence_links_view on annotation_occurrence_links(view_id);

create index if not exists idx_exports_site on exports(site);
create index if not exists idx_exports_site_batch on exports(site, batch_index, batch_total);
create index if not exists idx_views_export_doc on annotation_views(export_id, document_id);
create index if not exists idx_views_annotator on annotation_views(annotator);
create index if not exists idx_annotations_document_offsets on annotations(document_hash_id, begin_offset, end_offset);
create index if not exists idx_annotations_sctid on annotations(sctid);
create index if not exists idx_annotations_semantic_tag on annotations(semantic_tag);
"""

class AnnotationStoreWriter:
    """Small upsert-oriented SQLite writer."""

    def __init__(self, path: Union[str, pathlib.Path]):
        self.path = pathlib.Path(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("pragma foreign_keys = on")
        self.connection.row_factory = sqlite3.Row

    def close(self) -> None:
        self.connection.close()

    def initialize(self) -> None:
        # Only empty databases or this application's current schema are accepted.
        version = self.connection.execute("pragma user_version").fetchone()[0]
        has_tables = self.connection.execute(
            "select 1 from sqlite_master where type = 'table' and name not like 'sqlite_%' limit 1"
        ).fetchone() is not None
        if (has_tables and version != 2) or version not in (0, 2):
            raise ValueError(
                "Unsupported annotation-store schema. Build a new database at a different "
                "output path; automatic migration is not supported."
            )
        self.connection.executescript(SCHEMA_SQL)
        self.connection.execute("pragma user_version = 2")
        self.connection.commit()

    def insert_export(self, metadata: ExportMetadata, export_path: pathlib.Path, imported_at: str) -> int:
        path = str(pathlib.Path(export_path).resolve())
        filename = pathlib.Path(export_path).name
        self.connection.execute(
            """
            insert or ignore into exports(site, path, filename, batch_index, batch_total, batch_label, imported_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metadata.site,
                path,
                filename,
                metadata.batch_index,
                metadata.batch_total,
                metadata.batch_label,
                imported_at,
            ),
        )
        return self._id_for("exports", "path", path)

    def insert_document(self, document_name: str) -> int:
        self.connection.execute(
            "insert or ignore into documents(document_name) values (?)",
            (document_name,),
        )
        return self._id_for("documents", "document_name", document_name)

    def insert_document_hash(self, text_hash: str) -> int:
        self.connection.execute(
            "insert or ignore into document_hashes(text_hash) values (?)",
            (text_hash,),
        )
        row = self.connection.execute(
            """
            select id from document_hashes
            where text_hash = ?
            """,
            (text_hash,),
        ).fetchone()
        return int(row["id"])

    def insert_document_text(self, document_hash_id: int, text: str) -> int:
        self.connection.execute(
            "insert or ignore into document_texts(document_hash_id, text) values (?, ?)",
            (document_hash_id, text),
        )
        row = self.connection.execute(
            "select id from document_texts where document_hash_id = ?",
            (document_hash_id,),
        ).fetchone()
        return int(row["id"])

    def insert_annotation_view(
        self,
        export_id: int,
        document_id: int,
        document_hash_id: Optional[int],
        document_text_id: Optional[int],
        view_kind: str,
        annotator: str,
        cas_path: str,
    ) -> int:
        self.connection.execute(
            """
            insert or ignore into annotation_views(
              export_id, document_id, document_hash_id, document_text_id, view_kind, annotator, cas_path
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (export_id, document_id, document_hash_id, document_text_id, view_kind, annotator, cas_path),
        )
        if document_hash_id is not None or document_text_id is not None:
            self.connection.execute(
                """
                update annotation_views
                set document_hash_id = coalesce(document_hash_id, ?),
                    document_text_id = coalesce(document_text_id, ?)
                where export_id = ? and document_id = ? and view_kind = ? and annotator = ? and cas_path = ?
                """,
                (document_hash_id, document_text_id, export_id, document_id, view_kind, annotator, cas_path),
            )
        row = self.connection.execute(
            """
            select id from annotation_views
            where export_id = ? and document_id = ? and view_kind = ? and annotator = ? and cas_path = ?
            """,
            (export_id, document_id, view_kind, annotator, cas_path),
        ).fetchone()
        return int(row["id"])

    def insert_concept(self, sctid: Optional[str], concept: Optional[ConceptMetadata]) -> None:
        if not sctid:
            return
        self.connection.execute(
            """
            insert or ignore into snomed_concepts(sctid, fsn, semantic_tag, active)
            values (?, ?, ?, ?)
            """,
            (
                sctid,
                concept.fsn if concept else None,
                concept.semantic_tag if concept else None,
                _bool_to_int(concept.active) if concept else None,
            ),
        )

    def insert_annotation(self, view_id: int, occurrence: AnnotationOccurrence) -> bool:
        view = self.connection.execute(
            "select document_hash_id from annotation_views where id = ?", (view_id,)
        ).fetchone()
        if view is None:
            raise ValueError(f"Unknown annotation view: {view_id}")
        document_hash_id = view["document_hash_id"]
        # Missing document text must not cause sharing across unrelated views.
        payload = [
            document_hash_id, view_id if document_hash_id is None else None,
            occurrence.layer, occurrence.begin_offset, occurrence.end_offset,
            occurrence.covered_text, occurrence.sctid, occurrence.fsn,
            occurrence.semantic_tag, occurrence.active, occurrence.raw_id, occurrence.literal,
        ]
        annotation_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.connection.execute(
            """
            insert or ignore into annotations(
              document_hash_id, layer, begin_offset, end_offset, covered_text, sctid, fsn,
              semantic_tag, active, raw_id, literal, annotation_hash
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_hash_id,
                occurrence.layer,
                occurrence.begin_offset,
                occurrence.end_offset,
                occurrence.covered_text,
                occurrence.sctid,
                occurrence.fsn,
                occurrence.semantic_tag,
                _bool_to_int(occurrence.active),
                occurrence.raw_id,
                occurrence.literal,
                annotation_hash,
            ),
        )
        annotation_id = self._id_for("annotations", "annotation_hash", annotation_hash)
        cursor = self.connection.execute(
            """insert or ignore into annotation_occurrence_links(
                annotation_id, view_id, occurrence_hash
            ) values (?, ?, ?)""",
            (annotation_id, view_id, occurrence.annotation_hash),
        )
        return cursor.rowcount > 0

    def commit(self) -> None:
        self.connection.commit()

    def count(self, table: str) -> int:
        row = self.connection.execute(f"select count(*) as n from {table}").fetchone()
        return int(row["n"])

    def _id_for(self, table: str, column: str, value) -> int:
        row = self.connection.execute(
            f"select id from {table} where {column} = ?",
            (value,),
        ).fetchone()
        return int(row["id"])


def _bool_to_int(value: Optional[bool]) -> Optional[int]:
    if value is None:
        return None
    return 1 if value else 0
