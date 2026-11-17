from snomed_post_processing.annotation_store.sqlite import AnnotationStoreWriter


def test_document_content_hashes_are_shared(tmp_path):
    writer = AnnotationStoreWriter(tmp_path / "new-store.sqlite")
    try:
        writer.initialize()
        first = writer.insert_document_hash("same-content")
        assert writer.insert_document_hash("same-content") == first
        assert writer.insert_document_hash("different-content") != first
        assert writer.count("document_hashes") == 2
        text = writer.insert_document_text(first, "example")
        assert writer.insert_document_text(first, "example") == text
        assert writer.count("document_texts") == 1
    finally:
        writer.close()
