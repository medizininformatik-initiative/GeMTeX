import sqlite3

from snomed_post_processing.annotation_store.sqlite import AnnotationStoreWriter


def test_initialize_deduplicates_existing_document_hash_rows(tmp_path):
    db_path = tmp_path / "annotations.sqlite"
    con = sqlite3.connect(db_path)
    try:
        con.executescript(
            """
            create table exports(id integer primary key, site text, path text, filename text, batch_index integer, batch_total integer, batch_label text, imported_at text);
            create table documents(id integer primary key, document_name text);
            create table document_hashes(id integer primary key, document_id integer, export_id integer, text_hash text, source_path text);
            create table annotation_views(id integer primary key, export_id integer, document_id integer, document_hash_id integer, document_text_id integer, view_kind text, annotator text, cas_path text);
            insert into exports(id, site, path, filename, imported_at) values (1, 'a', 'a.zip', 'a.zip', 'now'), (2, 'b', 'b.zip', 'b.zip', 'now');
            insert into documents(id, document_name) values (1, 'A.txt'), (2, 'B.txt');
            insert into document_hashes(id, document_id, export_id, text_hash, source_path) values (100, 1, 1, 'same', 'a'), (101, 2, 2, 'same', 'b');
            insert into annotation_views(id, export_id, document_id, document_hash_id, document_text_id, view_kind, annotator, cas_path) values (200, 2, 2, 101, null, 'curation', 'u', 'b');
            """
        )
        con.commit()
    finally:
        con.close()

    writer = AnnotationStoreWriter(db_path)
    try:
        writer.initialize()
        assert writer.connection.execute("select count(*) from document_hashes where text_hash = 'same'").fetchone()[0] == 1
        assert writer.connection.execute("select document_hash_id from annotation_views where id = 200").fetchone()[0] == 100
    finally:
        writer.close()
