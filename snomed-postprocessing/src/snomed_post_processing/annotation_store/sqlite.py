"""SQLite writer for annotation-store imports."""

from __future__ import annotations

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
  view_id integer not null,
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
  foreign key(view_id) references annotation_views(id),
  foreign key(sctid) references snomed_concepts(sctid)
);

create index if not exists idx_exports_site on exports(site);
create index if not exists idx_exports_site_batch on exports(site, batch_index, batch_total);
create index if not exists idx_views_export_doc on annotation_views(export_id, document_id);
create index if not exists idx_views_annotator on annotation_views(annotator);
create index if not exists idx_annotations_view_offsets on annotations(view_id, begin_offset, end_offset);
create index if not exists idx_annotations_sctid on annotations(sctid);
create index if not exists idx_annotations_semantic_tag on annotations(semantic_tag);
"""

VIEW_SQL = """
drop view if exists annotation_occurrences;
create view annotation_occurrences as
select
  e.site,
  e.filename as export_file,
  e.batch_index,
  e.batch_total,
  d.document_name,
  av.view_kind,
  av.annotator,
  av.cas_path,
  dh.text_hash as document_text_hash,
  a.layer,
  a.begin_offset,
  a.end_offset,
  a.covered_text,
  a.sctid,
  a.semantic_tag,
  a.fsn,
  a.active,
  a.raw_id,
  a.literal
from annotations a
join annotation_views av on av.id = a.view_id
join exports e on e.id = av.export_id
join documents d on d.id = av.document_id
left join document_hashes dh on dh.id = av.document_hash_id;
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
        self.connection.execute("drop view if exists annotation_occurrences")
        self.connection.executescript(SCHEMA_SQL)
        self.connection.commit()
        self.connection.execute("pragma foreign_keys = off")
        self._migrate_existing_schema()
        self.connection.commit()
        self.connection.execute("pragma foreign_keys = on")
        self.connection.executescript(VIEW_SQL)
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
        cursor = self.connection.execute(
            """
            insert or ignore into annotations(
              view_id, layer, begin_offset, end_offset, covered_text, sctid, fsn,
              semantic_tag, active, raw_id, literal, annotation_hash
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                view_id,
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
                occurrence.annotation_hash,
            ),
        )
        return cursor.rowcount > 0

    def commit(self) -> None:
        self.connection.commit()

    def count(self, table: str) -> int:
        row = self.connection.execute(f"select count(*) as n from {table}").fetchone()
        return int(row["n"])

    def _migrate_existing_schema(self) -> None:
        """Migrate early annotation-store schemas in-place.

        Development builds initially stored provenance fields on
        `document_hashes`. Applicability is content-hash based, while provenance
        belongs to `annotation_views -> exports`, so this method rebuilds
        `document_hashes` to `(id, text_hash)` and rewrites optional raw text
        storage to reference the canonical hash row.
        """
        view_columns = {
            row["name"]
            for row in self.connection.execute("pragma table_info(annotation_views)")
        }
        if "document_hash_id" not in view_columns:
            self.connection.execute("alter table annotation_views add column document_hash_id integer")

        hash_columns = {
            row["name"]
            for row in self.connection.execute("pragma table_info(document_hashes)")
        }
        if hash_columns and hash_columns != {"id", "text_hash"}:
            self._rebuild_document_hashes_table()

        text_columns = {
            row["name"]
            for row in self.connection.execute("pragma table_info(document_texts)")
        }
        if text_columns and text_columns != {"id", "document_hash_id", "text"}:
            self._rebuild_document_texts_table()

        self.connection.execute(
            "create unique index if not exists idx_document_hashes_text_hash_unique on document_hashes(text_hash)"
        )

    def _rebuild_document_hashes_table(self) -> None:
        self.connection.execute(
            """
            update annotation_views
            set document_hash_id = (
              select min(canonical.id)
              from document_hashes current
              join document_hashes canonical on canonical.text_hash = current.text_hash
              where current.id = annotation_views.document_hash_id
            )
            where document_hash_id is not null
            """
        )
        self.connection.execute("alter table document_hashes rename to document_hashes_old")
        self.connection.execute(
            """
            create table document_hashes(
              id integer primary key,
              text_hash text not null unique
            )
            """
        )
        self.connection.execute(
            """
            insert into document_hashes(id, text_hash)
            select min(id), text_hash
            from document_hashes_old
            group by text_hash
            """
        )
        self.connection.execute("drop table document_hashes_old")

    def _rebuild_document_texts_table(self) -> None:
        old_columns = {
            row["name"]
            for row in self.connection.execute("pragma table_info(document_texts)")
        }
        if "text_hash" not in old_columns:
            return
        self.connection.execute("alter table document_texts rename to document_texts_old")
        self.connection.execute(
            """
            create table document_texts(
              id integer primary key,
              document_hash_id integer not null unique,
              text text not null,
              foreign key(document_hash_id) references document_hashes(id)
            )
            """
        )
        self.connection.execute(
            """
            insert or ignore into document_texts(id, document_hash_id, text)
            select min(dt.id), dh.id, dt.text
            from document_texts_old dt
            join document_hashes dh on dh.text_hash = dt.text_hash
            group by dt.text_hash
            """
        )
        self.connection.execute(
            """
            update annotation_views
            set document_text_id = (
              select min(new_dt.id)
              from document_texts_old old_dt
              join document_hashes dh on dh.text_hash = old_dt.text_hash
              join document_texts new_dt on new_dt.document_hash_id = dh.id
              where old_dt.id = annotation_views.document_text_id
            )
            where document_text_id is not null
            """
        )
        self.connection.execute("drop table document_texts_old")

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
