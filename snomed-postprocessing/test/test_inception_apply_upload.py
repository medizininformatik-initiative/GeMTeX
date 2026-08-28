import json
import pathlib
import tempfile
import unittest
import zipfile

from cassis import Cas, TypeSystem

from snomed_post_processing.pipelines import apply_decisions_and_upload_to_inception
from snomed_post_processing.sanitization.decisions_json import write_sanitization_decisions_json


class TestInceptionApplyUploadPipeline(unittest.TestCase):
    def _write_project_zip(self, path: pathlib.Path):
        typesystem = TypeSystem()
        concept_type = typesystem.create_type("gemtex.Concept", supertypeName="uima.tcas.Annotation")
        typesystem.create_feature(concept_type, "id", "uima.cas.String")
        cas = Cas(typesystem=typesystem, sofa_string="patient has pneumonia", sofa_mime="text/plain")
        Concept = typesystem.get_type("gemtex.Concept")
        cas.add(Concept(begin=12, end=21, id="http://snomed.info/id/233604007"))
        exported_project = {
            "name": "Example project",
            "slug": "example-project",
            "description": "Example",
            "layers": [],
            "source_documents": [
                {"name": "doc.txt.xmi", "format": "xmi", "state": "ANNOTATION_FINISHED"},
            ],
            "annotation_documents": [],
        }
        with zipfile.ZipFile(path, "w") as zip_file:
            zip_file.writestr("exportedproject.json", json.dumps(exported_project))
            zip_file.writestr("TypeSystem.xml", typesystem.to_xml())
            zip_file.writestr("annotation/doc.txt.xmi/anna.xmi", cas.to_xmi())

    def test_pipeline_builds_shell_artifacts_and_dry_run_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            source_zip = tmp_path / "project.zip"
            decisions_path = tmp_path / "decisions.json"
            output_dir = tmp_path / "out"
            self._write_project_zip(source_zip)
            write_sanitization_decisions_json(
                [
                    {
                        "action": "replace",
                        "apply": True,
                        "valid_choice": True,
                        "document": "doc.txt.xmi",
                        "annotator": "anna",
                        "source_code": "233604007",
                        "covered_text": "pneumonia",
                        "offset": [12, 21],
                        "layer": "gemtex.Concept",
                        "replacement_code": "999999",
                    }
                ],
                decisions_path,
            )

            result = apply_decisions_and_upload_to_inception(
                source_project=source_zip,
                decisions_path=decisions_path,
                output_dir=output_dir,
                project_name="Sanitized example",
                project_slug="sanitized-example",
            )

            self.assertTrue(result.shell_project.exists())
            self.assertTrue(result.artifacts_result.report_path.exists())
            self.assertTrue(result.deployment_result.deployment_report_path.exists())
            self.assertTrue(result.pipeline_report_path.exists())
            self.assertTrue(result.dry_run)
            self.assertFalse(result.applied)
            self.assertEqual(result.artifacts_result.artifact_count, 1)
            self.assertEqual(result.deployment_result.planned_upload_count, 1)
            self.assertEqual(result.deployment_result.errors, ())
            report = json.loads(result.pipeline_report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["remote_upload_issue_count"], 0)
            self.assertEqual(report["artifact_count"], 1)


if __name__ == "__main__":
    unittest.main()
