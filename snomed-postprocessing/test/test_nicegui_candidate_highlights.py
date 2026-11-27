"""Presentation-only candidate highlights; artificial annotations/evidence."""
import copy
from importlib.util import find_spec
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from snomed_post_processing.gui.nicegui.review import ReviewSession, load_review
from snomed_post_processing.gui.nicegui.review_panel import _candidate_rows
from snomed_post_processing.gui.nicegui.suggestions import load_suggestions_preview
from test.test_nicegui_suggestions import payload, encoded


def preview(duplicates=False):
    data = payload()
    if duplicates:
        data["suggestions"][0]["candidates"][1]["code"] = data["suggestions"][0]["candidates"][0]["code"]
    return load_suggestions_preview(encoded(data))


class CandidateHighlightTest(unittest.TestCase):
    def test_inspection_does_not_choose_or_mutate_review(self):
        source = preview()
        finding = source.findings[0]
        session = ReviewSession(source)
        rows = _candidate_rows(finding, session, finding.candidates[-1].row_id)
        self.assertFalse(any(row["chosen"] for row in rows))
        self.assertEqual([row["selection"] for row in rows][-1], "Inspecting only")
        self.assertFalse(session.dirty)
        self.assertFalse(session.saved)

    def test_exact_duplicate_candidate_survives_save_and_restore(self):
        source = preview(duplicates=True)
        finding = source.findings[0]
        session = ReviewSession(source)
        target = finding.candidates[1].row_id
        session.stage(finding.row_id, target)
        rows = _candidate_rows(finding, session, finding.candidates[0].row_id)
        self.assertEqual([row["row_id"] for row in rows if row["chosen"]], [target])
        self.assertEqual(rows[1]["selection"], "Chosen — pending Save")
        self.assertEqual(rows[0]["selection"], "Inspecting only")
        session.save()
        restored = load_review(session.export_text().encode(), source)
        before = copy.deepcopy(restored.saved)
        rows = _candidate_rows(finding, restored, target)
        self.assertEqual([row["row_id"] for row in rows if row["chosen"]], [target])
        self.assertEqual(rows[1]["selection"], "Chosen — saved · inspecting")
        self.assertEqual(restored.saved, before)
        self.assertFalse(rows[-1]["chosen"])  # Same-code diagnostic evidence is never chosen.

    def test_pending_keep_delete_manual_review_and_discard(self):
        source = preview()
        finding = source.findings[0]
        session = ReviewSession(source)
        session.stage(finding.row_id, finding.candidates[1].row_id)
        session.save()
        for action in ("none", "delete", "manual_edit"):
            session.stage(finding.row_id, action=action)
            self.assertFalse(any(row["chosen"] for row in _candidate_rows(finding, session)))
            session.discard()
            self.assertTrue(_candidate_rows(finding, session)[1]["chosen"])
        session.stage(finding.row_id, action="none")
        session.save()
        self.assertFalse(any(row["chosen"] for row in _candidate_rows(finding, session)))

    def test_saved_proposal_is_not_an_applied_choice_and_never_marks_context(self):
        data = payload()
        data["suggestions"][0]["replacement_code"] = "990000201"
        source = load_suggestions_preview(encoded(data))
        finding = source.findings[0]
        session = ReviewSession(source)
        rows = _candidate_rows(finding, session)
        self.assertTrue(rows[0]["proposed"])
        self.assertEqual(rows[0]["selection"], "Saved proposal — not accepted")
        self.assertFalse(rows[-1]["proposed"])  # Same SCTID, but diagnostic evidence.
        self.assertFalse(any(row["chosen"] for row in rows))
        self.assertFalse(session.dirty)
        rows = _candidate_rows(finding, session, finding.candidates[0].row_id)
        self.assertEqual(rows[0]["selection"], "Inspecting only · saved proposal")
        session.stage(finding.row_id, finding.candidates[0].row_id)
        rows = _candidate_rows(finding, session)
        self.assertEqual(rows[0]["selection"], "Chosen — pending Save · saved proposal")
        self.assertTrue(rows[0]["chosen"] and rows[0]["proposed"])
        data["suggestions"][0]["candidates"][1]["code"] = "990000201"
        duplicate_source = load_suggestions_preview(encoded(data))
        rows = _candidate_rows(duplicate_source.findings[0], ReviewSession(duplicate_source))
        self.assertEqual(sum(row["proposed"] for row in rows), 2)
        self.assertFalse(any(row["chosen"] for row in rows))

    def test_legacy_code_only_decisions_do_not_guess_between_duplicates(self):
        for duplicates in (False, True):
            source = preview(duplicates)
            finding = source.findings[0]
            session = ReviewSession(source)
            session.stage(finding.row_id, finding.candidates[0].row_id)
            session.save()
            saved = session.saved[finding.suggestion_index]
            saved.pop("manual_candidate_ordinal")
            saved.pop("manual_candidate")
            rows = _candidate_rows(finding, session)
            self.assertEqual(sum(row["chosen"] for row in rows), 0 if duplicates else 1)


@unittest.skipUnless(find_spec("nicegui"), "requires NiceGUI extra")
class CandidateHighlightPanelTest(unittest.IsolatedAsyncioTestCase):
    async def test_click_apply_save_discard_and_navigation_update_grid(self):
        from nicegui import Client, ui
        from nicegui.page import page
        from snomed_post_processing.gui.nicegui.review_panel import ReviewPanelControls
        client = Client(page("/candidate-highlights-test"))
        try:
            with client:
                with ui.column() as container:
                    panel = ReviewPanelControls(ui, container, provenance=ui.label())
                panel.publish_generated(preview())
                finding = panel.state.findings[0]
                event = lambda row: SimpleNamespace(args={"data": {"row_id": row.row_id}})
                panel.select_finding(event(finding))
                panel.candidate_grid.update = MagicMock()
                panel.candidate_grid.run_grid_method = MagicMock()
                panel.finding_grid.run_grid_method = MagicMock()
                panel.select_candidate(event(finding.candidates[1]))
                panel.candidate_grid.update.assert_not_called()
                self.assertTrue(any(call.args[0] == "applyTransaction"
                                    for call in panel.candidate_grid.run_grid_method.call_args_list))
                self.assertEqual(panel.candidate_grid.options["rowData"][1]["selection"], "Inspecting only")
                self.assertFalse(panel.controls.session.dirty)
                panel.controls.command("candidate")
                self.assertTrue(any(call.args[0] == "applyTransaction"
                                    for call in panel.finding_grid.run_grid_method.call_args_list))
                self.assertEqual(panel.candidate_grid.options["rowData"][1]["selection"], "Chosen — pending Save · inspecting")
                panel.controls.command("save")
                self.assertEqual(panel.candidate_grid.options["rowData"][1]["selection"], "Chosen — saved · inspecting")
                panel.select_candidate(event(finding.candidates[0]))
                self.assertTrue(panel.candidate_grid.options["rowData"][1]["chosen"])
                self.assertTrue(panel.candidate_grid.options["rowData"][0]["inspected"])
                panel.controls.command("candidate")
                panel.controls.command("discard")
                self.assertTrue(panel.candidate_grid.options["rowData"][1]["chosen"])
                panel.clear_inspection()
                panel.select_finding(event(finding))
                self.assertTrue(panel.candidate_grid.options["rowData"][1]["chosen"])
                self.assertFalse(any(row["inspected"] for row in panel.candidate_grid.options["rowData"]))
        finally:
            client.delete()
