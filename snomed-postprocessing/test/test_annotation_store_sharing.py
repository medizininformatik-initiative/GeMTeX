"""Shared annotation identity and provenance regression tests (stdlib runner)."""
import dataclasses
import pathlib
import sqlite3
import tempfile
import unittest

from snomed_post_processing.annotation_store.models import AnnotationOccurrence, ExportMetadata
from snomed_post_processing.annotation_store.sqlite import AnnotationStoreWriter


class TestAnnotationSharing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.writer = AnnotationStoreWriter(self.root / "new.sqlite")
        self.writer.initialize()
        self.base = AnnotationOccurrence(
            layer="gemtex.Concept", begin_offset=1, end_offset=5,
            covered_text="test", sctid=None, fsn=None, semantic_tag=None,
            active=None, raw_id=None, literal=None, annotation_hash="occurrence-1",
        )

    def tearDown(self):
        self.writer.close()
        self.tmp.cleanup()

    def view(self, site, text_hash="same-text", annotator="user"):
        export = self.writer.insert_export(
            ExportMetadata(site, 1, 1, "1-1"), self.root / f"{site}.zip", "now"
        )
        doc = self.writer.insert_document("doc.txt")
        doc_hash = self.writer.insert_document_hash(text_hash) if text_hash else None
        return self.writer.insert_annotation_view(
            export, doc, doc_hash, None, "annotation", annotator, "doc.xmi"
        )

    def test_share_across_sites_and_annotators_preserving_occurrences(self):
        first = self.view("a")
        second = self.view("b", annotator="other")
        self.assertTrue(self.writer.insert_annotation(first, self.base))
        other = dataclasses.replace(self.base, annotation_hash="occurrence-2")
        self.assertTrue(self.writer.insert_annotation(second, other))
        self.assertFalse(self.writer.insert_annotation(second, other))
        self.assertEqual(self.writer.count("annotations"), 1)
        self.assertEqual(self.writer.count("annotation_occurrence_links"), 2)
        rows = self.writer.connection.execute("""
            select e.site, av.annotator
            from annotation_occurrence_links o
            join annotation_views av on av.id = o.view_id
            join exports e on e.id = av.export_id
            order by e.site
        """).fetchall()
        self.assertEqual([r["site"] for r in rows], ["a", "b"])
        self.assertEqual([r["annotator"] for r in rows], ["user", "other"])
        self.writer.commit()
        self.writer.initialize()
        self.assertEqual(self.writer.count("annotation_occurrence_links"), 2)
        self.assertEqual(self.writer.connection.execute(
            "select count(*) from sqlite_master where type = 'view'"
        ).fetchone()[0], 0)
        self.assertEqual(self.writer.connection.execute("pragma foreign_key_check").fetchall(), [])

    def test_distinct_document_contents_do_not_share(self):
        for i, text_hash in enumerate(["text-a", "text-b"]):
            self.writer.insert_annotation(
                self.view(str(i), text_hash),
                dataclasses.replace(self.base, annotation_hash=str(i)),
            )
        self.assertEqual(self.writer.count("annotations"), 2)

    def test_missing_document_content_does_not_share_between_views(self):
        for i in range(2):
            self.writer.insert_annotation(
                self.view(str(i), None),
                dataclasses.replace(self.base, annotation_hash=str(i)),
            )
        self.assertEqual(self.writer.count("annotations"), 2)

    def test_every_data_field_participates_in_identity(self):
        view = self.view("a")
        self.writer.insert_annotation(view, self.base)
        changes = dict(layer="other", begin_offset=2, end_offset=6, covered_text="Test",
                       sctid="123", fsn="Example", semantic_tag="finding", active=False,
                       raw_id="null", literal="")
        self.writer.insert_concept("123", None)
        for field, value in changes.items():
            self.writer.insert_annotation(view, dataclasses.replace(
                self.base, **{field: value}, annotation_hash=field
            ))
        self.assertEqual(self.writer.count("annotations"), 1 + len(changes))

    def test_unversioned_database_rejected_without_changes(self):
        path = self.root / "unsupported.sqlite"
        with sqlite3.connect(path) as db:
            db.execute("create table unrelated(value integer)")
            db.execute("insert into unrelated values (7)")
        before = path.read_bytes()
        writer = AnnotationStoreWriter(path)
        try:
            with self.assertRaisesRegex(ValueError, "Build a new database"):
                writer.initialize()
        finally:
            writer.close()
        self.assertEqual(path.read_bytes(), before)

    def test_bundled_queries_count_shared_data(self):
        for site in ("a", "b"):
            self.writer.insert_annotation(
                self.view(site), dataclasses.replace(self.base, annotation_hash=site)
            )
        query_dir = pathlib.Path(__file__).resolve().parents[1] / "queries" / "annotation-store"
        parameters = dict(n=50, term="test", term_part="", semantic_tag="",
                          semantic_tag_part="", bin_by_sctid="false")
        for path in query_dir.glob("*.sql"):
            rows = self.writer.connection.execute(path.read_text(), parameters).fetchall()
            # NULL semantic tags do not match the tag-filter query.
            for row in rows:
                self.assertEqual(row["annotation_count"], 1, path.name)


if __name__ == "__main__":
    unittest.main()
