"""Review shortcuts navigate findings and accept unique saved proposals."""
import asyncio
import copy
from importlib.util import find_spec
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock

from test.test_nicegui_suggestions import payload, encoded


@unittest.skipUnless(find_spec("nicegui"), "requires NiceGUI extra")
class ReviewKeyboardTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from nicegui import Client, ui
        from nicegui.page import page
        from snomed_post_processing.gui.nicegui.review_panel import ReviewPanelControls
        from snomed_post_processing.gui.nicegui.suggestions import load_suggestions_preview
        self.client = Client(page("/review-keyboard-test"))
        with self.client:
            with ui.column() as container:
                self.panel = ReviewPanelControls(ui, container, banner=ui.label(), source=ui.label(), scope=ui.label())
            data = payload()
            second = copy.deepcopy(data["suggestions"][0])
            second["finding"]["offset"] = [20, 35]
            third = copy.deepcopy(second)
            third["finding"]["document"] = "second.txt"
            data["suggestions"].extend([second, third])
            self.panel.publish_generated(load_suggestions_preview(encoded(data)))
        self.panel.keyboard.active = True
        for grid in (self.panel.finding_grid, self.panel.document_grid):
            grid.get_client_data = AsyncMock(side_effect=lambda grid=grid, **_: list(grid.options["rowData"]))
            grid.run_row_method = MagicMock()
            grid.run_grid_method = MagicMock()

    async def asyncTearDown(self):
        self.client.delete()

    async def press(self, name, *, action="keydown", repeat=False, **modifiers):
        from nicegui.events import KeyboardAction, KeyboardKey, KeyboardModifiers
        event = SimpleNamespace(
            key=KeyboardKey(name=name, code="", location=0),
            action=KeyboardAction(keydown=action == "keydown", keyup=action == "keyup", repeat=repeat),
            modifiers=KeyboardModifiers(**(dict(alt=False, ctrl=False, meta=False, shift=False) | modifiers)))
        with self.client:
            await self.panel.handle_key(event)

    async def test_findings_select_and_reveal_without_wrapping_or_staging(self):
        panel = self.panel
        ids = [row.row_id for row in panel.state.findings[:2]]
        await self.press("d")
        self.assertEqual(panel.state.selected_finding_id, ids[0])
        panel.finding_grid.run_row_method.assert_called_with(ids[0], "setSelected", True, True)
        await self.press("d")
        self.assertEqual(panel.state.selected_finding_id, ids[1])
        panel.finding_grid.run_grid_method.assert_called_with("ensureIndexVisible", 1)
        await self.press("d")
        self.assertEqual(panel.state.selected_finding_id, ids[1])
        await self.press("a")
        await self.press("a")
        self.assertEqual(panel.state.selected_finding_id, ids[0])
        self.assertFalse(panel.controls.session.dirty)
        self.assertIsNone(panel.state.selected_candidate_id)

    async def test_space_accepts_unique_saved_proposal(self):
        await self.press("d")
        row = self.panel.state.selected_finding
        self.assertIsNotNone(self.panel.controls.session.proposed_candidate(row.row_id))
        await self.press("space")
        self.assertIn(row.row_id, self.panel.controls.session.drafts)

    async def test_previous_from_no_selection_starts_at_last_visible_finding(self):
        await self.press("a")
        self.assertEqual(self.panel.state.selected_finding_id, self.panel.state.findings[1].row_id)

    async def test_empty_artifact_does_not_query_the_client(self):
        self.panel.document_slides.clear()
        await self.press("d")
        await self.press("s")
        self.panel.finding_grid.get_client_data.assert_not_awaited()
        self.panel.document_grid.get_client_data.assert_not_awaited()

    async def test_filtered_sorted_order_and_unknown_rows(self):
        grid = self.panel.finding_grid
        ids = [row.row_id for row in self.panel.state.findings]
        grid.get_client_data.side_effect = None
        grid.get_client_data.return_value = [{"row_id": "old-artifact"}, {"row_id": ids[2]},
                                             {"row_id": ids[1]}, {"row_id": ids[0]}]
        await self.press("d")
        self.assertEqual(self.panel.state.selected_finding_id, ids[1])
        await self.press("d")
        self.assertEqual(self.panel.state.selected_finding_id, ids[0])
        grid.get_client_data.assert_awaited_with(method="filtered_sorted")
        grid.get_client_data.return_value = []
        await self.press("a")
        self.assertEqual(self.panel.state.selected_finding_id, ids[0])

    async def test_documents_clear_inspection_but_keep_pending_choices(self):
        panel = self.panel
        await self.press("d")
        row = panel.state.selected_finding
        panel.controls.session.stage(row.row_id, row.candidates[0].row_id)
        drafts = dict(panel.controls.session.drafts)
        await self.press("s")
        self.assertEqual(panel.active_document, "second.txt")
        self.assertIsNone(panel.state.selected_finding_id)
        await self.press("s")
        self.assertEqual(panel.active_document, "second.txt")
        await self.press("w")
        self.assertEqual(panel.active_document, "toy.txt")
        self.assertEqual(panel.controls.session.drafts, drafts)
        self.assertFalse(panel.controls.session.saved)

    async def test_document_filter_order_and_previous_without_selection(self):
        grid = self.panel.document_grid
        rows = list(reversed(grid.options["rowData"]))
        grid.get_client_data.side_effect = None
        grid.get_client_data.return_value = rows
        await self.press("w")
        self.assertEqual(self.panel.active_document, "second.txt")
        await self.press("a")
        self.assertEqual(self.panel.state.selected_finding_id, self.panel.state.findings[-1].row_id)

    async def test_modifiers_arrows_keyup_repeats_and_inactive_are_ignored(self):
        for key in ("ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "x"):
            await self.press(key)
        for modifier in ("alt", "ctrl", "meta", "shift"):
            await self.press("d", **{modifier: True})
        await self.press("d", action="keyup")
        await self.press("d", repeat=True)
        self.panel.keyboard.active = False
        await self.press("d")
        self.panel.finding_grid.get_client_data.assert_not_awaited()
        self.assertIsNone(self.panel.state.selected_finding_id)
        self.assertFalse(self.panel.keyboard.props["repeating"])
        self.assertEqual(self.panel.keyboard.props["ignore"], ["input", "select", "button", "textarea"])

    async def test_delayed_response_after_reload_or_tab_switch_is_ignored(self):
        for change in (self.panel.begin_load, lambda: setattr(self.panel.keyboard, "active", False)):
            self.panel.keyboard.active = True
            async def delayed(**_):
                rows = list(self.panel.finding_grid.options["rowData"])
                change()
                return rows
            self.panel.finding_grid.get_client_data.side_effect = delayed
            await self.press("d")
            self.assertIsNone(self.panel.state.selected_finding_id)
            self.assertFalse(self.panel._keyboard_busy)

    async def test_unavailable_grid_and_overlapping_keys_are_safe(self):
        self.panel.finding_grid.get_client_data.side_effect = TimeoutError()
        await self.press("d")
        self.assertFalse(self.panel._keyboard_busy)
        started, release = asyncio.Event(), asyncio.Event()
        async def delayed(**_):
            started.set()
            await release.wait()
            return list(self.panel.finding_grid.options["rowData"])
        self.panel.finding_grid.get_client_data.side_effect = delayed
        first = asyncio.create_task(self.press("d"))
        await started.wait()
        await self.press("d")
        release.set()
        await first
        self.assertEqual(self.panel.state.selected_finding_id, self.panel.state.findings[0].row_id)
        self.assertEqual(self.panel.finding_grid.get_client_data.await_count, 2)
        self.assertFalse(self.panel.controls.session.dirty)
