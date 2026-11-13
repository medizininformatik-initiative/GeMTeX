"""Policy engine equivalence and installed-SDK controls on owned/artificial inputs."""
import asyncio
from contextlib import redirect_stdout
import gc
import io
from importlib.util import find_spec
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import zipfile

from snomed_post_processing.findings_io.json_io import read_critical_findings_json
from snomed_post_processing.gui.nicegui.file_sources import MAX_UPLOAD_BYTES, list_server_files
from snomed_post_processing.gui.nicegui.policy_ui import PolicyCheckControls
from snomed_post_processing.pipelines.policy_check import PolicySettings, check_policy, project_annotators

FIXTURE = Path(__file__).parent / "projects" / "synthetic-annotator-scope"


def inline(function, *args):
    with redirect_stdout(io.StringIO()):
        return function(*args)


class PolicyEngineTest(unittest.TestCase):
    def test_matches_existing_findings_and_writes_no_source_files(self):
        paths = list(FIXTURE.iterdir())
        before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in paths}
        result = inline(check_policy, FIXTURE / "project.zip", FIXTURE / "policy.hdf5", PolicySettings())
        expected = read_critical_findings_json(FIXTURE / "critical-findings.json")
        self.assertEqual(result.findings, tuple(expected))
        self.assertEqual(result.critical_documents, 6)
        self.assertEqual(set(result.reports), {"critical-findings.json", "policy-report.md",
                                             "policy-report.masked.md", "policy-report.json"})
        self.assertEqual(tuple(read_critical_findings_json(io.StringIO(result.reports["critical-findings.json"]))), result.findings)
        self.assertEqual({p: (p.stat().st_size, p.stat().st_mtime_ns) for p in FIXTURE.iterdir()}, before)

    def test_normalized_scope_and_same_id_layer_defaults(self):
        settings = PolicySettings(annotators=(" Alice ", "ALICE"))
        result = inline(check_policy, FIXTURE / "project.zip", FIXTURE / "policy.hdf5", settings)
        self.assertEqual(result.settings.annotators, ("alice",))
        self.assertEqual(len(result.findings), 5)
        self.assertEqual({f.annotator.lower() for f in result.findings}, {"alice"})
        metadata = json.loads(result.reports["critical-findings.json"])["metadata"]
        self.assertEqual(metadata["annotators"], ["alice"])
        self.assertEqual(metadata["annotation_types"], ["gemtex.Concept", "webanno.custom.Concept"])
        self.assertEqual(metadata["ignore_overlap_types"], [])
        self.assertEqual(metadata["id_feature"], "id")

    def test_names_and_unsupported_ser(self):
        self.assertEqual(set(project_annotators(FIXTURE / "project.zip")), {"alice", "bob"})
        with TemporaryDirectory() as directory:
            path = Path(directory) / "project.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("document.ser", b"synthetic")
            with self.assertRaisesRegex(ValueError, "serialized CAS"):
                project_annotators(path)

    def test_directory_listing_is_direct_sorted_and_case_insensitive(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("z.H5", "a.hdf5", "b.zip", "unrelated.txt"):
                (root / name).touch()
            (root / "nested").mkdir()
            (root / "nested" / "hidden.h5").touch()
            self.assertEqual([p.name for p in list_server_files(root, (".hdf5", ".h5"))], ["a.hdf5", "z.H5"])
            self.assertEqual(list_server_files(root / "missing", (".zip",)), [])


@unittest.skipUnless(find_spec("nicegui") is not None, "requires the optional NiceGUI extra")
class PolicyControlsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from nicegui import ui, Client
        from nicegui.page import page
        self.ui = ui
        self.client = Client(page("/policy-test"))
        with self.client:
            with ui.column() as self.container:
                self.panel = PolicyCheckControls(ui)
        self.worker = patch("nicegui.run.io_bound", new=AsyncMock(side_effect=inline))
        self.worker_mock = self.worker.start()

    async def asyncTearDown(self):
        self.panel.close()
        self.client.delete()
        self.worker.stop()

    def server_inputs(self, directory=FIXTURE):
        p = self.panel
        p.project.mode.set_value("Server path")
        p.project.path.set_value(str(directory / "project.zip"))
        p.lists.mode.set_value("Server path")
        p.lists.path.set_value(str(directory / "policy.hdf5"))

    async def test_page_policy_check_does_not_change_loaded_review(self):
        from nicegui import events
        from snomed_post_processing.gui.nicegui.page import build_page
        from test.test_nicegui_suggestions import encoded, payload, upload_event
        controls = []
        def create(ui):
            control = PolicyCheckControls(ui)
            controls.append(control)
            return control
        with self.client, patch("snomed_post_processing.gui.nicegui.page.PolicyCheckControls", side_effect=create), \
                patch.object(self.ui, "upload", wraps=self.ui.upload) as uploads:
            build_page(self.ui, events)
            source_upload = uploads.call_args.kwargs["on_upload"]
        with self.client:
            await source_upload(upload_event(encoded(payload())))
        elements = self.client.elements
        review_grid = next(element for element in elements.values()
                           if hasattr(element, "options") and isinstance(element.options, dict)
                           and any(column.get("field") == "review" for column in element.options.get("columnDefs", [])))
        rows = [dict(row) for row in review_grid.options["rowData"]]
        review_source = next(element for element in elements.values() if getattr(element, "text", None) == "Source: suggestions.json")
        tabs = next(element for element in elements.values() if element.tag == "q-tabs")
        tabs.set_value("check")
        self.assertFalse(review_source.visible)
        policy = controls[0]
        worker_calls = self.worker_mock.await_count
        drawer = next(element for element in elements.values() if element.tag == "q-drawer")
        self.assertIs(policy.inputs.parent_slot.parent, drawer)
        self.assertEqual(drawer.default_slot.children.count(policy.inputs), 1)
        for tab in ("suggest", "review", "check"):
            tabs.set_value(tab)
            self.assertIs(policy.inputs.parent_slot.parent, drawer)
            self.assertTrue(policy.inputs.visible)
        self.assertEqual(self.worker_mock.await_count, worker_calls)
        drawer.hide()
        self.assertFalse(drawer.value)
        drawer.toggle()
        self.assertTrue(drawer.value)
        for source, name in ((policy.project, "project.zip"), (policy.lists, "policy.hdf5")):
            source.mode.set_value("Server path")
            source.path.set_value(str(FIXTURE / name))
        for tab in ("suggest", "review", "check"):
            tabs.set_value(tab)
            self.assertEqual(policy.project.snapshot().path, FIXTURE / "project.zip")
            self.assertEqual(policy.lists.snapshot().path, FIXTURE / "policy.hdf5")
        self.assertEqual(self.worker_mock.await_count, worker_calls)
        await policy.run_check()
        self.assertIsNotNone(policy.result)
        self.assertEqual(review_grid.options["rowData"], rows)
        tabs.set_value("review")
        self.assertTrue(review_source.visible)

    async def test_selection_and_directory_refresh_never_run_policy(self):
        p = self.panel
        self.assertFalse(p.run_button.enabled)
        p.data_dir.set_value(str(FIXTURE))
        for source, name in ((p.project, "project.zip"), (p.lists, "policy.hdf5")):
            source.mode.set_value("Data directory")
            self.assertIn(str(FIXTURE / name), source.choice.options)
            source.choice.set_value(str(FIXTURE / name))
            self.assertEqual(source.snapshot().path, FIXTURE / name)
        self.assertTrue(p.run_button.enabled)
        self.worker_mock.assert_not_awaited()
        await p.load_annotators()
        self.assertEqual(set(p.annotators.options), {"alice", "bob"})
        p.annotators.set_value(["alice"])
        self.assertIsNone(p.result)
        self.assertEqual(p.settings().annotators, ("alice",))
        p.project.path.set_value(str(FIXTURE / "project.zip"))
        p.project.mode.set_value("Server path")
        self.assertEqual(p.annotators.value, ["alice"])
        p.project.path.set_value(str(FIXTURE / "different-project.zip"))
        self.assertEqual(p.annotators.value, [])

    async def test_explicit_check_exports_all_findings_and_filters_do_not_rerun(self):
        p = self.panel
        self.server_inputs()
        await p.run_check()
        self.assertIsNotNone(p.result)
        self.assertEqual(len(p.grid.options["rowData"]), 10)
        self.assertTrue(p.results.visible)
        result = p.result
        calls = self.worker_mock.await_count
        with patch.object(p.grid, "run_grid_method", new=AsyncMock()) as grid_method:
            await p.clear_filters()
            grid_method.assert_awaited_once_with("setFilterModel", None)
        self.assertEqual(self.worker_mock.await_count, calls)
        with patch.object(self.ui.download, "content") as download:
            for filename, content in result.reports.items():
                await p.download(filename)
                download.assert_called_with(content, filename)
        self.assertIs(p.result, result)

    async def test_failure_retains_result_and_changes_invalidate_downloads_without_processing(self):
        p = self.panel
        self.server_inputs()
        await p.run_check()
        result = p.result
        with patch("snomed_post_processing.gui.nicegui.policy_ui.check_policy", side_effect=ValueError("DO_NOT_ECHO")):
            await p.run_check()
        self.assertIs(p.result, result)
        self.assertTrue(p.results.visible)
        self.assertNotIn("DO_NOT_ECHO", p.status.text)
        count = self.worker_mock.await_count
        p.prefix.set_value("")
        self.assertFalse(p.results.visible)
        self.assertTrue(all(not button.enabled for button in p.downloads))
        self.assertEqual(self.worker_mock.await_count, count)
        with patch.object(self.ui.download, "content") as download:
            await p.download("critical-findings.json")
            download.assert_not_called()

    async def test_edit_during_worker_discards_completion(self):
        p = self.panel
        self.server_inputs()
        started, finish = asyncio.Event(), asyncio.Event()
        async def delayed(function, *args):
            started.set()
            await finish.wait()
            return inline(function, *args)
        with patch("nicegui.run.io_bound", side_effect=delayed):
            task = asyncio.create_task(p.run_check())
            await started.wait()
            p.layers.set_value("changed.Layer")
            finish.set()
            await task
        self.assertIsNone(p.result)
        self.assertIn("discarded", p.status.text)

    async def test_external_file_change_blocks_download(self):
        p = self.panel
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("project.zip", "policy.hdf5"):
                shutil.copyfile(FIXTURE / name, root / name)
            self.server_inputs(root)
            await p.run_check()
            with (root / "policy.hdf5").open("ab") as stream:
                stream.write(b"changed")
            with patch.object(self.ui.download, "content") as download:
                await p.download("critical-findings.json")
                download.assert_not_called()
            self.assertFalse(p.results.visible)
            self.assertIn("changed", p.status.text)

    async def test_uploads_stream_to_owned_files_and_worker_references_keep_them_alive(self):
        for source, name in ((self.panel.project, "project.zip"), (self.panel.lists, "policy.hdf5")):
            content = (FIXTURE / name).read_bytes()
            async def save(path):
                path.write_bytes(content)
            event = SimpleNamespace(file=SimpleNamespace(name=name, size=lambda: len(content),
                                                         save=AsyncMock(side_effect=save), read=AsyncMock()))
            await source.load(event)
            snapshot = source.snapshot()
            self.assertEqual(snapshot.path.read_bytes(), content)
            event.file.read.assert_not_awaited()
            if source is self.panel.project:
                self.panel.annotators.set_options({"alice": "Alice"}, value=["alice"])
                rejected = SimpleNamespace(file=SimpleNamespace(name=name, size=lambda: MAX_UPLOAD_BYTES + 1, save=AsyncMock()))
                await source.load(rejected)
                self.assertEqual(self.panel.annotators.value, ["alice"])
                self.assertEqual(source.snapshot(), snapshot)
            owned_path = snapshot.path
            source.close()
            self.assertTrue(owned_path.exists())
            del snapshot
            gc.collect()
            self.assertFalse(owned_path.exists())

    async def test_oversize_and_late_uploads_do_not_replace_selection(self):
        source = self.panel.project
        event = SimpleNamespace(file=SimpleNamespace(name="project.zip", size=lambda: MAX_UPLOAD_BYTES + 1, save=AsyncMock()))
        await source.load(event)
        event.file.save.assert_not_awaited()
        self.assertIsNone(source.snapshot())
        started, finish = asyncio.Event(), asyncio.Event()
        async def save(path):
            started.set()
            await finish.wait()
            path.write_bytes(b"synthetic")
        event.file.size = lambda: 9
        event.file.save = save
        task = asyncio.create_task(source.load(event))
        await started.wait()
        source.mode.set_value("Server path")
        source.path.set_value(str(FIXTURE / "project.zip"))
        finish.set()
        await task
        self.assertEqual(source.snapshot().path, FIXTURE / "project.zip")
        self.assertIsNone(source.uploaded)

    async def test_disconnected_page_never_publishes_worker_result(self):
        self.server_inputs()
        started, finish = asyncio.Event(), asyncio.Event()
        async def delayed(function, *args):
            started.set()
            await finish.wait()
            return inline(function, *args)
        with patch("nicegui.run.io_bound", side_effect=delayed):
            task = asyncio.create_task(self.panel.run_check())
            await started.wait()
            self.panel.close()
            finish.set()
            await task
        self.assertIsNone(self.panel.result)


if __name__ == "__main__":
    unittest.main()
