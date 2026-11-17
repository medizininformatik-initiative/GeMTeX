from snomed_post_processing.annotation_store.extraction import normalize_sctid


def test_normalize_sctid_strips_prefix_case_insensitive():
    assert normalize_sctid("HTTP://SNOMED.INFO/ID/123") == "123"


def test_normalize_sctid_keeps_unknown_prefixless_value_and_handles_empty():
    assert normalize_sctid(" 123 ") == "123"
    assert normalize_sctid(None) is None
    assert normalize_sctid("nan") is None
