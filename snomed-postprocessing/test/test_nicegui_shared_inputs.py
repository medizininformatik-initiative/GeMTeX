"""Shared input ownership and asynchronous inspection, without a workflow panel."""
import asyncio
from importlib.util import find_spec
from pathlib import Path
import shutil
import unittest
from unittest.mock import AsyncMock, patch

from snomed_post_processing.gui.nicegui.shared_inputs import SharedInputControls


FIXTURE = Path(__file__).parent / "projects" / "synthetic-annotator-scope"


@unittest.skipUnless(find_spec("nicegui") is not None, "requires the optional NiceGUI extra")
class SharedInputControlsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from nicegui import Client, ui
        from nicegui.page import page
        self.ui, self.client = ui, Client(page("/shared-inputs-test"))
        with self.client:
            self.inputs = SharedInputControls(ui)
        self.worker = patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args)))
        self.io = self.worker.start()

    async def asyncTearDown(self):
        self.client.delete()
        self.worker.stop()

    def select_project(self):
        self.inputs.project.mode.set_value("Server path")
        self.inputs.project.path.set_value(str(FIXTURE / "project.zip"))

    async def test_inputs_and_annotator_inspection_work_without_policy_controls(self):
        inputs = self.inputs
        self.select_project()
        self.assertTrue(inputs.load_names.enabled)
        inputs.prefix.set_value("")
        inputs.annotators.set_options({" ALICE ": "Alice"}, value=[" ALICE "])
        self.assertEqual(inputs.settings().annotators, ("alice",))
        self.assertEqual(inputs.settings().id_prefix, "")
        self.io.assert_not_awaited()
        await inputs.load_annotators()
        self.assertEqual(inputs.annotators.value, ["alice"])
        self.assertEqual(set(inputs.annotators.options), {"alice", "bob"})
        self.io.assert_awaited_once()

    async def test_inception_api_button_does_not_require_prefilled_credentials(self):
        self.assertFalse(self.inputs.api_projects_button.enabled)
        self.inputs.use_api.set_value(True)
        self.assertTrue(self.inputs.api_projects_button.enabled)

    async def test_inception_api_lists_and_downloads_project_like_streamlit(self):
        inputs = self.inputs
        inputs.use_api.set_value(True)
        inputs.api_url.set_value("https://synthetic.invalid")
        inputs.api_username.set_value("remote-user")
        inputs.api_password.set_value("placeholder-password")
        calls = []

        def fake_get_project_zip(directory, url, username, password, project, verify_ssl):
            calls.append((directory, url, username, password, project, verify_ssl))
            if project is None:
                return ["Synthetic project", "Second project"]
            target = Path(directory) / "synthetic-project.zip"
            shutil.copyfile(FIXTURE / "project.zip", target)
            return target

        with patch("snomed_post_processing.gui.nicegui.shared_inputs.get_project_zip", side_effect=fake_get_project_zip):
            self.io.assert_not_awaited()
            await inputs.load_api_projects()
            self.assertEqual(inputs.api_project.options, ["Synthetic project", "Second project"])
            self.assertIsNone(inputs.project.snapshot())
            inputs.api_project.value = "Synthetic project"
            await inputs.api_project_changed()

        project = inputs.project.snapshot()
        self.assertIsNotNone(project)
        self.assertTrue(project.path.is_file())
        self.assertEqual(calls[0][1:], ("https://synthetic.invalid", "remote-user", "placeholder-password", None, False))
        self.assertEqual(calls[1][1:], ("https://synthetic.invalid", "remote-user", "placeholder-password",
                                       "Synthetic project", False))
        await inputs.load_annotators()
        self.assertEqual(set(inputs.annotators.options), {"alice", "bob"})

    async def test_changed_api_source_rejects_delayed_project_list(self):
        inputs = self.inputs
        inputs.use_api.set_value(True)
        inputs.api_url.set_value("https://synthetic.invalid")
        inputs.api_username.set_value("remote-user")
        inputs.api_password.set_value("placeholder-password")
        entered, release = asyncio.Event(), asyncio.Event()

        async def delayed(function, *args):
            entered.set()
            await release.wait()
            return ["Old project"]

        with patch("nicegui.run.io_bound", side_effect=delayed):
            task = asyncio.create_task(inputs.load_api_projects())
            await entered.wait()
            inputs.use_api.set_value(False)
            release.set()
            await task
        self.assertFalse(inputs.api_project.options)
        self.assertIsNone(inputs.project.snapshot())

    async def test_changed_or_closed_inputs_reject_pending_annotator_results(self):
        self.select_project()
        for close in (False, True):
            entered, release = asyncio.Event(), asyncio.Event()
            async def delayed(function, *args):
                entered.set()
                await release.wait()
                return function(*args)
            with patch("nicegui.run.io_bound", side_effect=delayed):
                task = asyncio.create_task(self.inputs.load_annotators())
                await entered.wait()
                if close:
                    self.inputs.close()
                else:
                    self.inputs.prefix.set_value("")
                release.set()
                await task
            self.assertFalse(self.inputs.annotators.options)

    async def test_closing_policy_does_not_close_shared_sources_or_leave_listener(self):
        from snomed_post_processing.gui.nicegui.policy_ui import PolicyCheckControls
        self.select_project()
        with self.client:
            policy = PolicyCheckControls(self.ui, self.inputs)
        self.assertIn(policy.changed, self.inputs.listeners)
        policy.close()
        self.assertNotIn(policy.changed, self.inputs.listeners)
        self.assertFalse(self.inputs.closed)
        self.assertFalse(self.inputs.project.closed)
        self.assertEqual(self.inputs.project.snapshot().path, FIXTURE / "project.zip")
        self.inputs.prefix.set_value("")
        self.io.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
