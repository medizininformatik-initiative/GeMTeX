"""Synthetic SQLite/ZIP equivalence; never modifies a clinical database."""
from contextlib import closing
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from snomed_post_processing.annotation_source import read_annotation_store, store_scopes, store_annotators
from snomed_post_processing.pipelines.policy_check import check_policy, PolicySettings
from snomed_post_processing.pipelines.suggestion_generation import generate_suggestions, SuggestionSettings
from snomed_post_processing.review_context import ReviewContext
from snomed_post_processing.sanitization.concept_rules import DEFAULT_CONCEPT_RULES, preview_concept_rules
from snomed_post_processing.uima_processing import process_inception_zip

FIXTURE = Path(__file__).parent / "projects" / "synthetic-annotator-scope"
LAYERS = ("gemtex.Concept", "webanno.custom.Concept")


def make_store(path):
    corpus = process_inception_zip(FIXTURE / "project.zip", annotation_types=list(LAYERS))
    texts = ReviewContext.from_project_path(FIXTURE / "project.zip").document_texts
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript("""
            PRAGMA user_version=2;
            CREATE TABLE exports(id INTEGER PRIMARY KEY, filename TEXT);
            CREATE TABLE documents(id INTEGER PRIMARY KEY, document_name TEXT);
            CREATE TABLE document_texts(id INTEGER PRIMARY KEY, document_hash_id INTEGER, text TEXT);
            CREATE TABLE annotation_views(id INTEGER PRIMARY KEY, export_id INTEGER, document_id INTEGER,
                document_hash_id INTEGER, document_text_id INTEGER, view_kind TEXT, annotator TEXT);
            CREATE TABLE annotations(id INTEGER PRIMARY KEY, document_hash_id INTEGER, layer TEXT,
                begin_offset INTEGER, end_offset INTEGER, covered_text TEXT, sctid TEXT);
            CREATE TABLE annotation_occurrence_links(id INTEGER PRIMARY KEY, annotation_id INTEGER, view_id INTEGER);
            INSERT INTO exports VALUES(1,'synthetic.zip');
        """)
        documents, payloads = {}, {}
        for annotator, container in corpus.annotators.items():
            for document, annotations in container.documents.items():
                if document not in documents:
                    identity = len(documents) + 1
                    documents[document] = identity
                    connection.execute("INSERT INTO documents VALUES(?,?)", (identity, document))
                    connection.execute("INSERT INTO document_texts VALUES(?,?,?)", (identity, identity, texts[document]))
                identity = documents[document]
                view = connection.execute("INSERT INTO annotation_views(export_id,document_id,document_hash_id,document_text_id,view_kind,annotator) VALUES(1,?,?,?,'annotation',?)",
                                          (identity, identity, identity, annotator)).lastrowid
                for i in range(annotations.length):
                    code = annotations.snomed_codes[i].decode()
                    values = (identity, str(annotations.layers[i]), *map(int, annotations.offsets[i]),
                              str(annotations.text[i]), None if code == 'nan' else code)
                    if values not in payloads:
                        payloads[values] = connection.execute("INSERT INTO annotations(document_hash_id,layer,begin_offset,end_offset,covered_text,sctid) VALUES(?,?,?,?,?,?)", values).lastrowid
                    connection.execute("INSERT INTO annotation_occurrence_links(annotation_id,view_id) VALUES(?,?)", (payloads[values], view))
    return path


class AnnotationSourceTest(unittest.TestCase):
    def setUp(self):
        self.owner = tempfile.TemporaryDirectory()
        self.addCleanup(self.owner.cleanup)
        self.path = make_store(Path(self.owner.name) / "annotations.sqlite")

    def test_occurrences_policy_suggestions_rules_and_context_match_zip(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        policy = PolicySettings(annotation_types=LAYERS)
        sql_policy = replace(policy, store_scope="*:annotation")
        original = check_policy(FIXTURE / "project.zip", FIXTURE / "policy.hdf5", policy)
        stored = check_policy(self.path, FIXTURE / "policy.hdf5", sql_policy)
        self.assertEqual(stored.findings, original.findings)
        self.assertEqual(len(stored.findings), 10)
        corpus = process_inception_zip(self.path, annotation_types=list(LAYERS))
        self.assertEqual(sum(a.length for c in corpus.annotators.values() for a in c.documents.values()), 14)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertLess(connection.execute("SELECT count(*) FROM annotations").fetchone()[0], 14)
        store_texts = ReviewContext.from_project_path(self.path).document_texts
        zip_texts = ReviewContext.from_project_path(FIXTURE / "project.zip").document_texts
        self.assertTrue(all(zip_texts[name] == text for name, text in store_texts.items()))
        self.assertTrue(all(finding.document in store_texts for finding in stored.findings))
        options = SuggestionSettings(semantic_bm25_fallback=False, snogit_bm25=False)
        results = [generate_suggestions(FIXTURE / "policy.hdf5", result.findings, {"annotators": []}, settings,
                                       options, binding="test", project=source)
                   for source, result, settings in ((self.path, stored, sql_policy), (FIXTURE / "project.zip", original, policy))]
        self.assertEqual(results[0].suggestions, results[1].suggestions)
        self.assertEqual(json.loads(results[0].json)["metadata"]["store_scope"], "*:annotation")
        self.assertEqual(preview_concept_rules(self.path, FIXTURE / "policy.hdf5", DEFAULT_CONCEPT_RULES,
                                              annotation_types=LAYERS, store_scope="*:annotation"),
                         preview_concept_rules(FIXTURE / "project.zip", FIXTURE / "policy.hdf5", DEFAULT_CONCEPT_RULES, annotation_types=LAYERS))
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)
        self.assertFalse(Path(str(self.path) + "-wal").exists())
        self.assertFalse(Path(str(self.path) + "-shm").exists())

    def test_scope_filters_and_duplicate_view_rejection(self):
        self.assertEqual(store_scopes(self.path), {"*:annotation": "All exports · annotation"})
        self.assertEqual({name.lower() for name in store_annotators(self.path)}, {"alice", "bob"})
        data = read_annotation_store(self.path, annotator_filter=[" ALICE "], annotation_types=LAYERS)
        self.assertEqual(sum(a.length for c in data.corpus.annotators.values() for a in c.documents.values()), 7)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("INSERT INTO exports VALUES(2,'second.zip')")
            connection.execute("INSERT INTO annotation_views(export_id,document_id,document_hash_id,document_text_id,view_kind,annotator) SELECT 2,document_id,document_hash_id,document_text_id,view_kind,annotator FROM annotation_views LIMIT 1")
        with self.assertRaisesRegex(ValueError, "Multiple views"):
            read_annotation_store(self.path)
        self.assertTrue(read_annotation_store(self.path, store_scope="1:annotation").corpus.annotators)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE annotation_views SET view_kind='curation' WHERE export_id=2")
        with self.assertRaisesRegex(ValueError, "scope first"):
            read_annotation_store(self.path)
        self.assertIn("*:curation", store_scopes(self.path))

    def test_pending_wal_and_conflicting_text_are_rejected(self):
        pending = self.path.with_name("pending.sqlite")
        pending.write_bytes(self.path.read_bytes())
        Path(str(pending) + "-wal").write_bytes(b"pending")
        with self.assertRaisesRegex(ValueError, "checkpointed"):
            read_annotation_store(pending)
        self.assertFalse(Path(str(pending) + "-shm").exists())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("INSERT INTO document_texts SELECT 1000,document_hash_id,'conflicting text' FROM annotation_views LIMIT 1")
            connection.execute("UPDATE annotation_views SET document_text_id=1000 WHERE id=(SELECT max(id) FROM annotation_views WHERE document_id=(SELECT document_id FROM annotation_views LIMIT 1))")
        with self.assertRaisesRegex(ValueError, "conflicting text"):
            read_annotation_store(self.path, annotation_types=LAYERS)

    def test_missing_full_text_keeps_annotations_available(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE annotation_views SET document_text_id=NULL")
        data = read_annotation_store(self.path, annotation_types=LAYERS)
        self.assertFalse(data.document_texts)
        self.assertEqual(sum(a.length for c in data.corpus.annotators.values() for a in c.documents.values()), 14)

    def test_ignore_layers_offsets_and_version_are_validated_without_migration(self):
        with self.assertRaisesRegex(ValueError, "ignore-overlap layer"):
            read_annotation_store(self.path, ignore_overlap_types=["missing.Ignore"])
        original = read_annotation_store(self.path, annotation_types=LAYERS)
        available = sorted({str(layer) for container in original.corpus.annotators.values()
                            for annotations in container.documents.values() for layer in annotations.layers})
        data = read_annotation_store(self.path, annotation_types=LAYERS, ignore_overlap_types=available, ignore_overlap_mode="exact")
        self.assertTrue(all(a.ignore_mask.all() for c in data.corpus.annotators.values() for a in c.documents.values()))
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE annotations SET end_offset=-1 WHERE id=1")
        with self.assertRaisesRegex(ValueError, "offsets"):
            read_annotation_store(self.path)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA user_version=1")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "schema v2"):
            read_annotation_store(self.path)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
