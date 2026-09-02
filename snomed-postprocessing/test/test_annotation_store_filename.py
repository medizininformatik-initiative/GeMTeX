import pathlib

from snomed_post_processing.annotation_store.filename import (
    normalize_document_name,
    parse_export_filename,
    view_kind_from_cas_path,
)


def test_parse_export_filename_standard_batch():
    meta = parse_export_filename(pathlib.Path("berlin_XMI_2-3.zip"))
    assert meta.site == "berlin"
    assert meta.batch_index == 2
    assert meta.batch_total == 3
    assert meta.batch_label == "2-3"


def test_parse_export_filename_flat_and_umlaut():
    meta = parse_export_filename(pathlib.Path("münchen_flat_XMI_1-3.zip"))
    assert meta.site == "münchen"
    assert meta.batch_index == 1
    assert meta.batch_total == 3


def test_parse_export_filename_fallback_and_override():
    meta = parse_export_filename(pathlib.Path("some_export.zip"), site_override="dresden")
    assert meta.site == "dresden"
    assert meta.batch_index is None


def test_parse_export_filename_tolerates_suffix_and_batch_override():
    meta = parse_export_filename(
        pathlib.Path("berlin_XMI_1-3_reviewed.zip"),
        batch_index_override=9,
        batch_total_override=10,
    )
    assert meta.site == "berlin"
    assert meta.batch_index == 9
    assert meta.batch_total == 10
    assert meta.batch_label == "9-10"


def test_parse_export_filename_without_batch():
    meta = parse_export_filename(pathlib.Path("dresden_XMI.zip"))
    assert meta.site == "dresden"
    assert meta.batch_index is None
    assert meta.batch_total is None


def test_parse_export_filename_json_variants():
    meta = parse_export_filename(pathlib.Path("dresden_JSON_2-4.zip"))
    assert meta.site == "dresden"
    assert meta.batch_index == 2
    assert meta.batch_total == 4
    meta = parse_export_filename(pathlib.Path("dresden_flat_JSON.zip"))
    assert meta.site == "dresden"
    assert meta.batch_index is None


def test_normalize_document_name_removes_cas_suffixes():
    assert normalize_document_name("Albers.txt.xmi") == "Albers.txt"
    assert normalize_document_name("curation/Albers.txt.xmi/CURATION_USER.zip") == "CURATION_USER"
    assert normalize_document_name("Albers.txt") == "Albers.txt"


def test_view_kind_from_cas_path():
    assert view_kind_from_cas_path("annotation/Doc.txt.xmi/user.zip") == "annotation"
    assert view_kind_from_cas_path("curation/Doc.txt.xmi/CURATION_USER.zip") == "curation"
    assert view_kind_from_cas_path("Doc.txt.xmi/user.zip", fallback_flat_layout=True) == "flat"
