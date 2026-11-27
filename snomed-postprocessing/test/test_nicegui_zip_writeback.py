"""Local NiceGUI ZIP write-back; no network or remote deployment."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from snomed_post_processing.gui.nicegui.file_sources import SourceFile
from snomed_post_processing.gui.nicegui.review import load_review
from snomed_post_processing.gui.nicegui.suggestions import load_suggestions_preview
from snomed_post_processing.gui.nicegui.zip_writeback_ui import (
    ZipWritebackControls,
    build_sanitized_zip,
)

FIXTURE = Path(__file__).parent / "projects/synthetic-annotator-scope"


def reviewed_state():
    state = load_suggestions_preview((FIXTURE / "suggestions.json").read_bytes(), "suggestions.json")
    state.metadata["annotation_source_file"] = "project.zip"
    return state, load_review((FIXTURE / "staged-decisions.json").read_bytes(), state)


def fake_ui():
    ui = MagicMock()

    def element(value=None, **_):
        item = MagicMock()
        item.value = value
        item.classes.return_value = item
        item.props.return_value = item
        item.tooltip.return_value = item
        item.set_text.side_effect = lambda text: setattr(item, "text", text)
        item.set_value.side_effect = lambda new_value: setattr(item, "value", new_value)
        item.set_visibility.side_effect = lambda visible: setattr(item, "visible", visible)
        item.set_enabled.side_effect = lambda enabled: setattr(item, "enabled", enabled)
        return item

    ui.expansion.side_effect = lambda *_args, **_kwargs: element()
    ui.label.side_effect = lambda text="": element(text)
    ui.input.side_effect = lambda _label, value="", **_kwargs: element(value)
    ui.linear_progress.side_effect = lambda value=0.0, **_kwargs: element(value)
    ui.button.side_effect = lambda *_args, **_kwargs: element()
    return ui


class ZipWritebackWorkerTest(unittest.TestCase):
    def decisions_text(self, source="project.zip"):
        data = json.loads((FIXTURE / "staged-decisions.json").read_text(encoding="utf-8"))
        data["metadata"]["annotation_source_file"] = source
        return json.dumps(data)

    def test_builds_new_zip_with_saved_scope_and_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sanitized.zip"
            result = build_sanitized_zip(
                FIXTURE / "project.zip", self.decisions_text(), output,
                manual_review_layer="webanno.custom.ManualReview",
            )
            self.assertTrue(output.is_file())
            self.assertEqual(result.changed_annotation_count, 6)
            self.assertEqual(result.changed_member_count, 4)
            self.assertFalse(result.unmatched_decisions)
            self.assertTrue((FIXTURE / "project.zip").is_file())

    def test_rejects_unbound_or_different_source_before_writing(self):
        for source in (None, "other.zip"):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                data = json.loads(self.decisions_text())
                if source is None:
                    data["metadata"].pop("annotation_source_file")
                else:
                    data["metadata"]["annotation_source_file"] = source
                output = Path(directory) / "sanitized.zip"
                with self.assertRaisesRegex(Exception, "record|does not match"):
                    build_sanitized_zip(
                        FIXTURE / "project.zip", json.dumps(data), output,
                        manual_review_layer="webanno.custom.ManualReview",
                    )
                self.assertFalse(output.exists())


class ZipWritebackControlsTest(unittest.IsolatedAsyncioTestCase):
    def setup_controls(self):
        ui = fake_ui()
        state, session = reviewed_state()
        source = SourceFile(FIXTURE / "project.zip")
        project = MagicMock()
        project.snapshot.return_value = source
        inputs = SimpleNamespace(is_store=False, project=project, revision=3, closed=False, listeners=[])
        review = SimpleNamespace(state=state, controls=SimpleNamespace(session=session, before_export=None), writeback=None)
        controls = ZipWritebackControls(ui, inputs, review)
        return ui, inputs, review, controls

    async def test_prepares_and_downloads_current_result(self):
        ui, _, _, controls = self.setup_controls()
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args, **kwargs: function(*args, **kwargs))), \
                patch("nicegui.run.cpu_bound", new=AsyncMock(side_effect=lambda function, *args, **kwargs: function(*args, **kwargs))):
            await controls.prepare()
        self.assertIsNotNone(controls.output)
        self.assertEqual(controls.progress.value, 1.0)
        self.assertIn("Changed 6 annotation", controls.status.text)
        controls.download_output()
        ui.download.file.assert_called_once_with(controls.output.path, filename=controls.output.path.name)
        controls.close()

    async def test_discards_result_when_inputs_change_during_worker(self):
        _, inputs, _, controls = self.setup_controls()

        async def changed_worker(function, *args, **kwargs):
            result = function(*args, **kwargs)
            inputs.revision += 1
            return result

        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args, **kwargs: function(*args, **kwargs))), \
                patch("nicegui.run.cpu_bound", new=AsyncMock(side_effect=changed_worker)):
            await controls.prepare()
        self.assertIsNone(controls.output)
        self.assertIn("stale result was discarded", controls.status.text)
        controls.close()


if __name__ == "__main__":
    unittest.main()
