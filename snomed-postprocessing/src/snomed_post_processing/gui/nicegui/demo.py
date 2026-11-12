"""Entirely artificial UI examples; 990... codes are not real concept claims."""
from snomed_post_processing.gui.nicegui.state import CandidatePreview, FindingPreview, PreviewState


def create_demo_state() -> PreviewState:
    """Fresh per-page state, including tied and diagnostic-only candidates.

    Ranks and scores are fixed illustrative inputs, not retrieval/scoring output.
    These objects are not backend findings or exportable reviewed decisions.
    """
    return PreviewState(findings=(
        FindingPreview(
            row_id="synthetic-preview-v1:0", suggestion_index=0,
            document="automatic.txt", annotator="alice", code="990000101",
            text="Artificial historical example", reason="Toy REPLACED_BY example; preview only.", candidate_count=1,
            candidates=(CandidatePreview("990000201", "Toy replacement concept", "demo:0:selectable:0", rank=1),),
        ),
        FindingPreview(
            row_id="synthetic-preview-v1:1", suggestion_index=1,
            document="ambiguous.txt", annotator="bob", code="990000102",
            text="Artificial tied-score example", reason="Equal top scores; neither target is preselected.", candidate_count=3,
            candidates=(
                CandidatePreview("990000202", "Toy candidate A", "demo:1:selectable:0", rank=1, score=9.0),
                CandidatePreview("990000203", "Toy candidate B", "demo:1:selectable:1", rank=1, score=9.0),
                CandidatePreview("990000204", "Toy candidate C", "demo:1:selectable:2", rank=3, score=4.0),
                CandidatePreview("990000301", "Toy rejected target (context only)", "demo:1:context:0", selectable=False),
            ),
        ),
        FindingPreview(
            row_id="synthetic-preview-v1:2", suggestion_index=2,
            document="manual-controls.txt", annotator="alice", code="990000404",
            text="Artificial no-candidate example", reason="No saved selectable candidates; manual review required.",
        ),
    ))
