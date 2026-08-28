import json
import pathlib
import tempfile
import unittest
import zipfile

from snomed_post_processing.pipelines.inception_deployment import (
    deploy_inception_sanitized_project,
)


class TestInceptionDeployment(unittest.TestCase):
    def _write_shell_zip(self, path: pathlib.Path):
        with zipfile.ZipFile(path, "w") as zip_file:
            zip_file.writestr("exportedproject.json", json.dumps({"name": "shell"}))

    def _write_artifacts(self, directory: pathlib.Path):
        directory.mkdir(parents=True, exist_ok=True)
        artifact = directory / "doc__ann-anna.json"
        artifact.write_text('{"%TYPES":{},"%FEATURE_STRUCTURES":[]}', encoding="utf-8")
        report = {
            "mode": "flattened-documents",
            "source_project": "source.zip",
            "artifact_count": 1,
            "uploads": [
                {
                    "source_member": "annotation/doc.txt.xmi/anna.json",
                    "source_document": "doc.txt.xmi",
                    "source_annotator": "anna",
                    "remote_document_name": "doc__ann-anna.json",
                    "output_path": str(artifact),
                    "format": "jsoncas",
                    "decision_count": 2,
                    "changed_annotation_count": 2,
                }
            ],
        }
        (directory / "inception-upload-artifacts-report.json").write_text(
            json.dumps(report), encoding="utf-8"
        )
        return artifact

    def test_dry_run_writes_plan_report_without_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            shell_zip = tmp_path / "shell.zip"
            artifacts_dir = tmp_path / "artifacts"
            self._write_shell_zip(shell_zip)
            self._write_artifacts(artifacts_dir)

            result = deploy_inception_sanitized_project(
                shell_project=shell_zip,
                upload_artifacts_dir=artifacts_dir,
            )

            self.assertTrue(result.dry_run)
            self.assertFalse(result.applied)
            self.assertEqual(result.planned_upload_count, 1)
            self.assertEqual(result.errors, ())
            self.assertTrue(result.deployment_report_path.exists())
            report = json.loads(result.deployment_report_path.read_text(encoding="utf-8"))
            self.assertTrue(report["dry_run"])
            self.assertFalse(report["applied"])
            self.assertEqual(report["would_import_shell_project"], str(shell_zip))
            self.assertEqual(report["would_create_documents"], ["doc__ann-anna.json"])
            self.assertEqual(report["would_upload_annotations"], 1)

    def test_dry_run_accepts_existing_relative_output_paths(self):
        with tempfile.TemporaryDirectory(dir=".") as tmp:
            tmp_path = pathlib.Path(tmp)
            shell_zip = tmp_path / "shell.zip"
            self._write_shell_zip(shell_zip)
            artifacts_dir = tmp_path / "artifacts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            artifact = artifacts_dir / "doc__ann-anna.json"
            artifact.write_text('{"%TYPES":{},"%FEATURE_STRUCTURES":[]}', encoding="utf-8")
            (artifacts_dir / "inception-upload-artifacts-report.json").write_text(
                json.dumps(
                    {
                        "mode": "flattened-documents",
                        "uploads": [
                            {
                                "remote_document_name": "doc__ann-anna.json",
                                "output_path": str(artifact),
                                "format": "jsoncas",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = deploy_inception_sanitized_project(
                shell_project=shell_zip,
                upload_artifacts_dir=artifacts_dir,
            )

            self.assertEqual(result.errors, ())

    def test_dry_run_reports_invalid_artifact_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            shell_zip = tmp_path / "shell.zip"
            artifacts_dir = tmp_path / "artifacts"
            self._write_shell_zip(shell_zip)
            artifacts_dir.mkdir()
            (artifacts_dir / "inception-upload-artifacts-report.json").write_text(
                json.dumps(
                    {
                        "mode": "flattened-documents",
                        "uploads": [
                            {
                                "remote_document_name": "doc__ann-anna.json",
                                "format": "jsoncas",
                            },
                            {
                                "remote_document_name": "doc__ann-anna.json",
                                "format": "bad-format",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = deploy_inception_sanitized_project(
                shell_project=shell_zip,
                upload_artifacts_dir=artifacts_dir,
            )

            self.assertTrue(result.dry_run)
            self.assertFalse(result.applied)
            self.assertGreaterEqual(len(result.errors), 3)
            self.assertTrue(any("Duplicate remote document name" in e for e in result.errors))
            self.assertTrue(any("Unsupported format" in e for e in result.errors))
            self.assertTrue(any("does not exist" in e for e in result.errors))
            report = json.loads(result.deployment_report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["errors"], list(result.errors))

    def test_apply_requires_connection_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            shell_zip = tmp_path / "shell.zip"
            artifacts_dir = tmp_path / "artifacts"
            self._write_shell_zip(shell_zip)
            self._write_artifacts(artifacts_dir)

            result = deploy_inception_sanitized_project(
                shell_project=shell_zip,
                upload_artifacts_dir=artifacts_dir,
                apply=True,
            )

            self.assertFalse(result.dry_run)
            self.assertFalse(result.applied)
            self.assertTrue(any("URL is required" in e for e in result.errors))
            self.assertTrue(any("username is required" in e for e in result.errors))
            self.assertTrue(any("password is required" in e for e in result.errors))


if __name__ == "__main__":
    unittest.main()
