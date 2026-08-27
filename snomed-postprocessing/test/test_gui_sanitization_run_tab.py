from types import SimpleNamespace

from snomed_post_processing.gui.sanitization_run_tab import (
    _finding_context_label,
    _metadata_finding_context_lookup,
    _needs_row_specific_choice,
    _replacement_options_and_hints,
    _review_rows_to_decisions,
    _row_manual_choice_resolved,
    _status_label,
    _status_label_for_suggestion,
)
from snomed_post_processing.sanitization.models import SanitizationStatus


def test_finding_context_uses_metadata_when_project_text_is_unavailable():
    finding = SimpleNamespace(
        document="doc.txt.xmi",
        annotator="fmatthies",
        code="123456",
        offset=(10, 20),
        covered_text="covered",
    )
    metadata = {
        "finding_contexts": [
            {
                "document": "doc.txt.xmi",
                "annotator": "fmatthies",
                "code": "123456",
                "offset": [10, 20],
                "context": "… real [covered] context …",
            }
        ]
    }

    assert _finding_context_label(finding, {}, _metadata_finding_context_lookup(metadata)) == "… real [covered] context …"


def test_finding_context_fallback_explains_missing_full_document_text():
    finding = SimpleNamespace(
        document="doc.txt.xmi",
        annotator="fmatthies",
        code="123456",
        offset=(10, 20),
        covered_text="covered",
    )

    assert _finding_context_label(finding, {}) == "No full document context loaded."


def test_single_bm25_replacement_is_not_manual_choice():
    suggestion = SimpleNamespace(
        status=SanitizationStatus.SEMANTIC_BM25_REPLACEMENT,
        replacement_code="123456",
        replacement_fsn="Candidate concept (finding)",
        score=7.5,
        candidates=(
            SimpleNamespace(
                code="123456",
                fsn="Candidate concept (finding)",
                score=7.5,
                lexical_score=1.0,
                semantic_tag="finding",
                source="snomed_fsn",
            ),
            SimpleNamespace(
                code="7891011",
                fsn="Other candidate (finding)",
                score=5.0,
                lexical_score=0.8,
                semantic_tag="finding",
                source="snomed_fsn",
            ),
        ),
    )

    options, _ = _replacement_options_and_hints(suggestion)

    assert options == ["123456 — Candidate concept (finding)"]
    assert not _needs_row_specific_choice(suggestion, options)
    assert _status_label(suggestion.status) == "BM25 suggestion"
    assert _status_label_for_suggestion(suggestion) == "BM25 suggestion"


def test_single_snogit_bm25_replacement_status_mentions_snogit():
    suggestion = SimpleNamespace(
        status=SanitizationStatus.SEMANTIC_BM25_REPLACEMENT,
        replacement_code="123456",
        replacement_fsn="Candidate concept (finding)",
        candidates=(
            SimpleNamespace(
                code="123456",
                fsn="Candidate concept (finding)",
                score=7.5,
                lexical_score=1.0,
                semantic_tag="finding",
                source="snogit",
                matched_term="candidate term",
                source_member="SNOGIT_20240131.dat",
            ),
        ),
    )

    assert _status_label_for_suggestion(suggestion) == "BM25 suggestion (SNOGIT)"


def test_manual_choice_delete_counts_as_resolved():
    row = {
        "#": 1,
        "_needs_choice": True,
        "Apply": False,
        "Delete annotation": True,
        "Suggested replacement": "123456 — Candidate concept (finding)",
    }

    assert _row_manual_choice_resolved(row)


def test_manual_choice_manual_edit_counts_as_resolved():
    row = {
        "#": 1,
        "_needs_choice": True,
        "Apply": False,
        "Delete annotation": False,
        "Needs manual edit": True,
        "Suggested replacement": "123456 — Candidate concept (finding)",
    }

    assert _row_manual_choice_resolved(row)


def test_manual_edit_decision_takes_precedence_over_apply_and_delete():
    original = {
        "#": 1,
        "Document": "doc.txt",
        "Status": "Ambiguous replacement",
        "Why suggested": "multiple candidates",
        "_offset": (12, 21),
        "_layer": "gemtex.Concept",
        "_valid_choices": ("123456 — Candidate concept (finding)",),
    }
    edited = {
        "#": 1,
        "Apply": True,
        "Delete annotation": True,
        "Needs manual edit": True,
        "Annotator": "annotator-a",
        "Source code": "233604007",
        "Covered text": "pneumonia",
        "Suggested replacement": "123456 — Candidate concept (finding)",
    }

    decision = _review_rows_to_decisions([edited], [original], {})[0]

    assert decision["action"] == "manual_edit"
    assert decision["manual_edit"] is True
    assert decision["apply"] is False
    assert decision["delete_annotation"] is False


def test_ambiguous_bm25_replacement_still_requires_choice():
    suggestion = SimpleNamespace(
        status=SanitizationStatus.AMBIGUOUS_REPLACEMENT,
        replacement_code=None,
        replacement_fsn=None,
        candidates=(
            SimpleNamespace(
                code="123456",
                fsn="Candidate concept (finding)",
                score=7.5,
                lexical_score=1.0,
                semantic_tag="finding",
                source="snomed_fsn",
            ),
            SimpleNamespace(
                code="7891011",
                fsn="Other candidate (finding)",
                score=7.5,
                lexical_score=1.0,
                semantic_tag="finding",
                source="snomed_fsn",
            ),
        ),
    )

    options, _ = _replacement_options_and_hints(suggestion)

    assert len(options) == 2
    assert _needs_row_specific_choice(suggestion, options)
