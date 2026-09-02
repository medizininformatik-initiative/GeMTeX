from snomed_post_processing.annotation_store.models import AnnotationOccurrence, ConceptMetadata, ExportMetadata
from snomed_post_processing.annotation_store.sqlite import AnnotationStoreWriter


def test_sqlite_writer_inserts_and_flattens_rows(tmp_path):
    db_path = tmp_path / "annotations.sqlite"
    writer = AnnotationStoreWriter(db_path)
    try:
        writer.initialize()
        export_id = writer.insert_export(
            ExportMetadata("berlin", 1, 3, "1-3"),
            tmp_path / "berlin_XMI_1-3.zip",
            "2026-01-01T00:00:00Z",
        )
        document_id = writer.insert_document("Albers.txt")
        document_hash_id = writer.insert_document_hash(
            document_id,
            export_id,
            "doc-hash",
            "curation/Albers.txt.xmi/CURATION_USER.zip",
        )
        view_id = writer.insert_annotation_view(
            export_id,
            document_id,
            document_hash_id,
            None,
            "curation",
            "CURATION_USER",
            "curation/Albers.txt.xmi/CURATION_USER.zip",
        )
        concept = ConceptMetadata("123", "Example (finding)", "finding", True)
        writer.insert_concept("123", concept)
        inserted = writer.insert_annotation(
            view_id,
            AnnotationOccurrence(
                layer="gemtex.Concept",
                begin_offset=1,
                end_offset=5,
                covered_text="test",
                sctid="123",
                fsn="Example (finding)",
                semantic_tag="finding",
                active=True,
                raw_id="http://snomed.info/id/123",
                literal=None,
                annotation_hash="abc",
            ),
        )
        assert inserted is True
        assert writer.insert_annotation(
            view_id,
            AnnotationOccurrence(
                layer="gemtex.Concept",
                begin_offset=1,
                end_offset=5,
                covered_text="test",
                sctid="123",
                fsn="Example (finding)",
                semantic_tag="finding",
                active=True,
                raw_id="http://snomed.info/id/123",
                literal=None,
                annotation_hash="abc",
            ),
        ) is False
        writer.commit()
        row = writer.connection.execute("select * from annotation_occurrences").fetchone()
        assert row["site"] == "berlin"
        assert row["document_name"] == "Albers.txt"
        assert row["sctid"] == "123"
        assert row["document_text_hash"] == "doc-hash"
    finally:
        writer.close()
