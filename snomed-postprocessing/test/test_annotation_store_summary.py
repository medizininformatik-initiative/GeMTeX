from snomed_post_processing.annotation_store.models import AnnotationStoreSummary
from snomed_post_processing.pipelines.annotation_store import _summary_as_dict


def test_serialized_cas_members_count():
    summary = AnnotationStoreSummary(
        failed_cas_members=[
            {"reason": "serialized_cas"},
            {"reason": "load_error"},
            {"reason": "serialized_cas"},
            {},
        ]
    )

    assert summary.serialized_cas_members == 2


def test_summary_report_includes_missing_sctid_occurrences():
    summary = AnnotationStoreSummary(missing_sctid_occurrences=7)

    assert _summary_as_dict(summary)["missing_sctid_occurrences"] == 7
