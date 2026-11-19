"""Document navigation is a view over artifact-bound review, not approval."""
import copy
from importlib.util import find_spec
from types import SimpleNamespace
import unittest

from snomed_post_processing.gui.nicegui.suggestions import load_suggestions_preview
from test.test_nicegui_suggestions import payload, encoded


@unittest.skipUnless(find_spec("nicegui"), "requires NiceGUI extra")
class DocumentOverviewTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from nicegui import Client, ui
        from nicegui.page import page
        from snomed_post_processing.gui.nicegui.review_panel import ReviewPanelControls
        self.client = Client(page("/document-overview-test"))
        with self.client:
            with ui.column() as container:
                self.panel = ReviewPanelControls(ui, container, banner=ui.label(), source=ui.label(), scope=ui.label())
            data = payload()
            second = copy.deepcopy(data["suggestions"][0])
            second["finding"]["document"] = "second.txt"
            data["suggestions"].append(second)
            self.panel.publish_generated(load_suggestions_preview(encoded(data)))

    async def asyncTearDown(self):
        self.client.delete()

    def rows(self):
        return self.panel.document_grid.options["rowData"]

    async def test_overview_counts_navigation_preserves_choices_and_clears_inspection(self):
        panel = self.panel
        self.assertEqual([row["findings"] for row in self.rows()], [1, 1])
        self.assertEqual([row["current"] for row in self.rows()], [True, False])
        finding = panel.state.findings[0]
        panel.state.select_finding(finding.row_id)
        panel.state.preview_candidate(finding.candidates[0].row_id)
        panel.controls.session.stage(finding.row_id, finding.candidates[0].row_id)
        panel.controls.refresh()
        self.assertEqual(self.rows()[0]["pending"], 1)
        session = panel.controls.session
        target = self.rows()[1]["row_id"]
        with self.client:
            panel.select_document(SimpleNamespace(args={"data": {"row_id": target}}))
        self.assertEqual(panel.active_document, "second.txt")
        self.assertEqual([row["current"] for row in self.rows()], [False, True])
        self.assertIs(panel.controls.session, session)
        self.assertTrue(session.drafts)
        self.assertFalse(session.saved)
        self.assertIsNone(panel.state.selected_candidate_id)
        self.assertIn("2/2", panel.document_position.text)
        panel.controls.command("save")
        self.assertEqual(self.rows()[0]["pending"], 0)
        self.assertEqual(self.rows()[0]["review"], "Not marked")

    async def test_document_review_flag_and_discard_refresh_overview(self):
        panel = self.panel
        finding = panel.state.findings[0]
        session = panel.controls.session
        session.mark_document(finding.row_id, True)
        panel.controls.refresh()
        self.assertEqual(self.rows()[0]["pending"], 1)
        self.assertEqual(self.rows()[0]["review"], "Not marked")
        panel.controls.command("save")
        self.assertEqual(self.rows()[0]["review"], "Reviewed")
        session.mark_document(finding.row_id, False)
        panel.controls.refresh()
        self.assertEqual(self.rows()[0]["pending"], 1)
        panel.controls.command("discard")
        self.assertEqual(self.rows()[0]["pending"], 0)
        self.assertEqual(self.rows()[0]["review"], "Reviewed")

    async def test_new_artifact_rejects_old_navigation_tokens(self):
        panel = self.panel
        old = self.rows()[1]["row_id"]
        with self.client:
            panel.publish_generated(load_suggestions_preview(encoded(payload())))
            panel.select_document(SimpleNamespace(args={"data": {"row_id": old}}))
        self.assertEqual(panel.active_document, "toy.txt")
        self.assertEqual(len(self.rows()), 1)
        self.assertFalse(panel.controls.session.dirty)
