"""NiceGUI deployment preparation and explicit remote apply; network is mocked."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from snomed_post_processing.gui.nicegui.deployment_ui import (
    InceptionDeploymentControls,
    PreparedDeployment,
    prepare_review_deployment,
)
from snomed_post_processing.gui.nicegui.file_sources import SourceFile
from snomed_post_processing.gui.nicegui.review import load_review
from snomed_post_processing.gui.nicegui.suggestions import load_suggestions_preview
from snomed_post_processing.pipelines.inception_deployment import InceptionDeploymentResult

FIXTURE = Path(__file__).parent / "projects/synthetic-annotator-scope"


def reviewed_state():
    state = load_suggestions_preview((FIXTURE / "suggestions.json").read_bytes(), "suggestions.json")
    state.metadata["annotation_source_file"] = "project.zip"
    return state, load_review((FIXTURE / "staged-decisions.json").read_bytes(), state)


def element(value=None):
    item = MagicMock()
    item.value = value
    item.options = {}
    item.classes.return_value = item
    item.props.return_value = item
    item.tooltip.return_value = item
    item.set_text.side_effect = lambda text: setattr(item, "text", text)
    item.set_value.side_effect = lambda new_value: setattr(item, "value", new_value)
    item.set_visibility.side_effect = lambda visible: setattr(item, "visible", visible)
    item.set_enabled.side_effect = lambda enabled: setattr(item, "enabled", enabled)
    return item


def fake_ui():
    ui = MagicMock()
    ui.expansion.side_effect = lambda *_args, **_kwargs: element()
    ui.row.side_effect = lambda *_args, **_kwargs: element()
    ui.label.side_effect = lambda text="": element(text)
    ui.input.side_effect = lambda _label, value="", **_kwargs: element(value)
    ui.checkbox.side_effect = lambda _label, value=False, **_kwargs: element(value)
    ui.linear_progress.side_effect = lambda value=0.0, **_kwargs: element(value)
    ui.button.side_effect = lambda *_args, **_kwargs: element()
    return ui


class FakeFileSource:
    def __init__(self, *_args, **_kwargs):
        self.container = element()
        self.uploading = False
        self.source = None

    def snapshot(self):
        return self.source

    def close(self):
        pass


class DeploymentWorkerTest(unittest.TestCase):
    def decisions_text(self, source="project.zip"):
        data = json.loads((FIXTURE / "staged-decisions.json").read_text(encoding="utf-8"))
        data["metadata"]["annotation_source_file"] = source
        return json.dumps(data)

    def test_prepares_frozen_shell_and_artifacts_without_network(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "snomed_post_processing.pipelines.inception_deployment._pycaprio_client"
        ) as client:
            prepared = prepare_review_deployment(
                FIXTURE / "project.zip", self.decisions_text(), Path(directory),
                project_name="Synthetic sanitized", project_slug=None,
                manual_review_layer="webanno.custom.ManualReview",
                store_scope=None, project_template=None,
            )
            client.assert_not_called()
            self.assertTrue(prepared.result.shell_project.is_file())
            self.assertTrue(prepared.artifacts_zip.is_file())
            self.assertIsNotNone(prepared.sanitized_project_zip)
            self.assertTrue(prepared.sanitized_project_zip.is_file())
            self.assertGreater(prepared.result.deployment_result.planned_upload_count, 0)
            self.assertFalse(prepared.result.applied)

    def test_rejects_review_bound_to_another_source(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(Exception, "does not match"):
            prepare_review_deployment(
                FIXTURE / "project.zip", self.decisions_text("other.zip"), Path(directory),
                project_name=None, project_slug=None,
                manual_review_layer="webanno.custom.ManualReview",
                store_scope=None, project_template=None,
            )


class DeploymentControlsTest(unittest.IsolatedAsyncioTestCase):
    def setup_controls(self):
        ui = fake_ui()
        state, session = reviewed_state()
        source = SourceFile(FIXTURE / "project.zip")
        project = MagicMock()
        project.snapshot.return_value = source
        scope = element(None)
        inputs = SimpleNamespace(
            is_store=False, project=project, scope=scope, revision=3, closed=False,
            listeners=[], data_dir=element("data"),
        )
        review = SimpleNamespace(
            state=state, controls=SimpleNamespace(session=session, before_export=None), deployment=None,
        )
        with patch("snomed_post_processing.gui.nicegui.deployment_ui.FileSource", FakeFileSource):
            controls = InceptionDeploymentControls(ui, inputs, review)
        return ui, inputs, review, controls

    async def test_connection_interface_is_separate_and_reuses_project_listing_helper(self):
        _, _, _, controls = self.setup_controls()
        controls.url.value = "https://inception.invalid"
        controls.username.value = "deploy-user"
        controls.password.value = "secret"
        controls.disable_tls.value = False
        with patch("snomed_post_processing.gui.nicegui.deployment_ui._inception_projects", return_value=["a", "b"]) as listing, \
                patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args, **kwargs: function(*args, **kwargs))):
            await controls.test_connection()
        listing.assert_called_once_with("https://inception.invalid", "deploy-user", "secret", True)
        self.assertIn("2 project", controls.connection_status.text)
        controls.close()

    async def test_confirmed_upload_uses_frozen_package_once(self):
        _, _, _, controls = self.setup_controls()
        prepared = MagicMock(spec=PreparedDeployment)
        prepared.result = MagicMock()
        prepared.sanitized_project_zip = Path("sanitized.zip")
        controls.prepared = prepared
        controls.prepared_token = controls._token()
        controls.url.value = "https://inception.invalid"
        controls.username.value = "deploy-user"
        controls.password.value = "secret"
        controls.annotation_user.value = "annotation-user"
        controls.disable_tls.value = False
        controls.confirm.value = True
        result = InceptionDeploymentResult(
            dry_run=False, applied=True, shell_project=Path("shell.zip"),
            upload_artifacts_dir=Path("artifacts"), artifact_report_path=Path("artifact-report.json"),
            deployment_report_path=Path("deployment-report.json"), planned_upload_count=4,
            warnings=(), errors=(), imported_project_id=42, imported_project_name="sanitized",
        )
        with patch("snomed_post_processing.gui.nicegui.deployment_ui.upload_prepared_deployment", return_value=result) as upload, \
                patch("nicegui.run.cpu_bound", new=AsyncMock(side_effect=lambda function, *args, **kwargs: function(*args, **kwargs))):
            await controls.upload()
        upload.assert_called_once_with(
            prepared, inception_url="https://inception.invalid", username="deploy-user", password="secret",
            annotation_user="annotation-user", verify_tls=True,
        )
        self.assertTrue(controls.upload_attempted)
        self.assertIn("new INCEpTION project sanitized (ID 42)", controls.connection_status.text)
        controls.close()


if __name__ == "__main__":
    unittest.main()
