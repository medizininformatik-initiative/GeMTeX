from types import SimpleNamespace

from snomed_post_processing.gui.sanitization_run_tab import (
    _needs_row_specific_choice,
    _replacement_options_and_hints,
    _status_label,
)
from snomed_post_processing.sanitization.models import SanitizationStatus


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
