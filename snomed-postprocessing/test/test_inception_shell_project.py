import json
import pathlib
import tempfile
import unittest
import zipfile

from snomed_post_processing.pipelines.inception_shell_project import (
    InceptionShellProjectError,
    build_inception_shell_project,
)


class TestInceptionShellProject(unittest.TestCase):
    def _write_project_zip(self, path: pathlib.Path):
        exported_project = {
            "name": "Example project",
            "slug": "example-project",
            "description": "Original description.",
            "layers": [
                {
                    "name": "gemtex.Concept",
                    "uiName": "Concept",
                    "type": "span",
                    "anchoring_mode": "TOKENS",
                    "lock_to_token_offset": False,
                    "multiple_tokens": True,
                    "cross_sentence": False,
                    "overlap_mode": "NO_OVERLAP",
                    "allow_stacking": False,
                    "validation_mode": "ALWAYS",
                    "linked_list_behavior": False,
                    "built_in": False,
                    "features": [
                        {
                            "name": "id",
                            "uiName": "ID",
                            "type": "uima.cas.String",
                            "enabled": True,
                            "visible": True,
                        }
                    ],
                }
            ],
            "tag_sets": [
                {
                    "name": "ExampleTagset",
                    "language": "en",
                    "tags": [],
                }
            ],
            "source_documents": [
                {
                    "name": "doc.txt",
                    "format": "text",
                    "state": "NEW",
                }
            ],
            "annotation_documents": [
                {
                    "name": "doc.txt",
                    "user": "annotator-a",
                    "state": "NEW",
                }
            ],
            "project_permissions": [
                {"user": "annotator-a", "level": "ANNOTATOR"},
            ],
        }
        with zipfile.ZipFile(path, "w") as zip_file:
            zip_file.writestr("exportedproject.json", json.dumps(exported_project))
            zip_file.writestr("TypeSystem.xml", "<typeSystemDescription/>")
            zip_file.writestr("source/doc.txt", "patient text")
            zip_file.writestr("annotation/doc.txt/annotator-a.json", "{}")
            zip_file.writestr("annotation_ser/doc.txt/annotator-a.ser", b"serialized")
            zip_file.writestr("curation/doc.txt/CURATION_USER.json", "{}")
            zip_file.writestr("curation_ser/doc.txt/CURATION_USER.ser", b"serialized")

    def test_build_shell_project_clears_content_and_adds_manual_review_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            source_zip = tmp_path / "project.zip"
            shell_zip = tmp_path / "shell.zip"
            self._write_project_zip(source_zip)

            result = build_inception_shell_project(source_zip, shell_zip)

            self.assertEqual(result.project_name, "Example project (sanitized)")
            self.assertEqual(result.project_slug, "example-project-sanitized")
            self.assertEqual(result.source_document_count, 0)
            self.assertEqual(result.annotation_document_count, 0)
            with zipfile.ZipFile(shell_zip, "r") as zip_file:
                names = set(zip_file.namelist())
                project = json.loads(zip_file.read("exportedproject.json"))

            self.assertIn("exportedproject.json", names)
            self.assertIn("TypeSystem.xml", names)
            self.assertNotIn("source/doc.txt", names)
            self.assertFalse(any(name.startswith("annotation/") for name in names))
            self.assertFalse(any(name.startswith("annotation_ser/") for name in names))
            self.assertFalse(any(name.startswith("curation/") for name in names))
            self.assertFalse(any(name.startswith("curation_ser/") for name in names))
            self.assertEqual(project["source_documents"], [])
            self.assertEqual(project["annotation_documents"], [])
            layer_names = {layer.get("name") for layer in project.get("layers", [])}
            self.assertIn("gemtex.Concept", layer_names)
            self.assertIn("webanno.custom.ManualReview", layer_names)
            manual_layer = next(
                layer for layer in project["layers"] if layer.get("name") == "webanno.custom.ManualReview"
            )
            self.assertEqual(manual_layer.get("anchoring_mode"), "TOKENS")
            self.assertEqual(manual_layer.get("cross_sentence"), False)
            self.assertEqual(manual_layer.get("overlap_mode"), "NO_OVERLAP")
            self.assertEqual(manual_layer.get("allow_stacking"), False)
            self.assertEqual(
                {feature.get("name") for feature in manual_layer.get("features", [])},
                {
                    "source_code",
                    "suggestion_status",
                    "suggested_replacement",
                    "review_note",
                },
            )

    def test_explicit_project_metadata_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            source_zip = tmp_path / "project.zip"
            shell_zip = tmp_path / "shell.zip"
            self._write_project_zip(source_zip)

            build_inception_shell_project(
                source_zip,
                shell_zip,
                project_name="Sanitized review",
                project_slug="sanitized-review",
                project_description="Reviewed sanitized project.",
            )

            with zipfile.ZipFile(shell_zip, "r") as zip_file:
                project = json.loads(zip_file.read("exportedproject.json"))
            self.assertEqual(project["name"], "Sanitized review")
            self.assertEqual(project["slug"], "sanitized-review")
            self.assertEqual(project["description"], "Reviewed sanitized project.")

    def test_explicit_name_and_slug_are_not_rewritten_when_description_is_auto_appended(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            source_zip = tmp_path / "project.zip"
            shell_zip = tmp_path / "shell.zip"
            self._write_project_zip(source_zip)

            build_inception_shell_project(
                source_zip,
                shell_zip,
                project_name="Sanitized review",
                project_slug="sanitized-review",
            )

            with zipfile.ZipFile(shell_zip, "r") as zip_file:
                project = json.loads(zip_file.read("exportedproject.json"))
            self.assertEqual(project["name"], "Sanitized review")
            self.assertEqual(project["slug"], "sanitized-review")
            self.assertEqual(
                project["description"],
                "Original description.\n\nSanitized export (sanitized).",
            )

    def test_keep_source_documents_preserves_source_metadata_and_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            source_zip = tmp_path / "project.zip"
            shell_zip = tmp_path / "shell.zip"
            self._write_project_zip(source_zip)

            result = build_inception_shell_project(
                source_zip,
                shell_zip,
                clear_source_documents=False,
                include_source_files=True,
            )

            self.assertEqual(result.source_document_count, 1)
            with zipfile.ZipFile(shell_zip, "r") as zip_file:
                names = set(zip_file.namelist())
                project = json.loads(zip_file.read("exportedproject.json"))
            self.assertIn("source/doc.txt", names)
            self.assertEqual([doc.get("name") for doc in project["source_documents"]], ["doc.txt"])
            self.assertEqual(project["annotation_documents"], [])

    def test_invalid_explicit_slug_is_rejected_before_inception_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            source_zip = tmp_path / "project.zip"
            shell_zip = tmp_path / "shell.zip"
            self._write_project_zip(source_zip)

            with self.assertRaisesRegex(InceptionShellProjectError, "3-40 characters"):
                build_inception_shell_project(
                    source_zip,
                    shell_zip,
                    project_slug="snomed-pp-project-fmatthies-sanitized-2026-08-18-075955",
                )

    def test_long_auto_slug_is_shortened_to_inception_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            source_zip = tmp_path / "project.zip"
            shell_zip = tmp_path / "shell.zip"
            self._write_project_zip(source_zip)

            build_inception_shell_project(source_zip, shell_zip, sanitized_project_suffix="very-long-sanitized-suffix")

            with zipfile.ZipFile(shell_zip, "r") as zip_file:
                project = json.loads(zip_file.read("exportedproject.json"))
            self.assertLessEqual(len(project["slug"]), 40)
            self.assertRegex(project["slug"], r"^[a-z][a-z0-9_-]{2,39}$")

    def test_refuses_in_place_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            source_zip = tmp_path / "project.zip"
            self._write_project_zip(source_zip)

            with self.assertRaises(InceptionShellProjectError):
                build_inception_shell_project(source_zip, source_zip, force=True)


if __name__ == "__main__":
    unittest.main()
