from snomed_post_processing.annotation_store.models import ExportMetadata
from snomed_post_processing.annotation_store.sqlite import AnnotationStoreWriter
from snomed_post_processing.pipelines.annotation_store_check import run_check_annotation_store_document


def test_check_annotation_store_document_matches_by_hash_only(tmp_path):
    db_path = tmp_path / "annotations.sqlite"
    doc_path = tmp_path / "external-name-does-not-matter.txt"
    text = "same content\n"
    doc_path.write_text(text, encoding="utf-8")

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
            "f953bbd204bb867e48a6ff774cffa3dcffd02c6580e8f1d00c37dbbaa743d6c8"
        )
        writer.insert_annotation_view(export_id, document_id, document_hash_id, None, "curation", "CURATION_USER", "cas/path.zip")
        writer.commit()
    finally:
        writer.close()

    result = run_check_annotation_store_document(
        store=db_path,
        document=doc_path,
        encoding="utf-8",
        report=None,
        log_level="ERROR",
    )
    assert result.matched is True
    assert result.matches[0].document_name == "Albers.txt"
