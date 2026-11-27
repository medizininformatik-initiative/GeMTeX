"""Both shells share the same table resizing styles, without inline height resets."""
from importlib.util import find_spec
import unittest


@unittest.skipUnless(find_spec("nicegui"), "requires NiceGUI extra")
class ResizableTablesTest(unittest.IsolatedAsyncioTestCase):
    async def test_all_workflow_tables_resize_and_document_minimum_is_larger(self):
        from nicegui import Client, events, ui
        from nicegui.page import page
        from snomed_post_processing.gui.nicegui.page import build_page
        client = Client(page("/table-resize-test"))
        try:
            with client:
                workflow = build_page(ui, events)
            review = workflow.review
            grids = (workflow.policy.grid, workflow.suggestions.rule_editor, workflow.suggestions.overview,
                     review.finding_grid, review.candidate_grid, review.rule_grid, review.document_grid)
            for grid in grids:
                self.assertEqual(grid.style["resize"], "vertical")
                self.assertEqual(grid.style["overflow"], "auto")
                self.assertNotIn("height", grid.style)
                self.assertEqual(grid.style["min-height"], "320px" if grid is review.document_grid else "160px")
            self.assertIn("h-80", review.document_grid._classes)
            review.controls.refresh()
            for grid in grids:
                self.assertNotIn("height", grid.style)
            self.assertFalse(review.controls.session.dirty)
        finally:
            client.delete()
