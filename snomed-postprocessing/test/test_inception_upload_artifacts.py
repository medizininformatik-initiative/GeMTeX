import io
import json
import pathlib
import tempfile
import unittest
import zipfile

import cassis
from cassis import Cas, TypeSystem

from snomed_post_processing.pipelines.inception_upload_artifacts import (
    build_inception_upload_artifacts,
)


class TestInceptionUploadArtifacts(unittest.TestCase):
    def _typesystem_and_cas(self):
        typesystem = TypeSystem()
        concept_type = typesystem.create_type(
            "gemtex.Concept", supertypeName="uima.tcas.Annotation"
        )
        typesystem.create_feature(concept_type, "id", "uima.cas.String")
        cas = Cas(typesystem=typesystem, sofa_string="patient has pneumonia", sofa_mime="text/plain")
        Concept = typesystem.get_type("gemtex.Concept")
        cas.add(Concept(begin=12, end=21, id="http://snomed.info/id/233604007"))
        return typesystem, cas

    def _write_project_zip(self, path: pathlib.Path):
        typesystem, cas = self._typesystem_and_cas()
        exported_project = {
            "source_documents": [
                {"name": "doc.txt.xmi", "format": "xmi", "state": "ANNOTATION_FINISHED"},
            ]
        }
        with zipfile.ZipFile(path, "w") as zip_file:
            zip_file.writestr("exportedproject.json", json.dumps(exported_project))
            zip_file.writestr("TypeSystem.xml", typesystem.to_xml())
            zip_file.writestr("annotation/doc.txt.xmi/INITIAL_CAS.xmi", cas.to_xmi())
            zip_file.writestr("annotation_ser/doc.txt.xmi/INITIAL_CAS.ser", b"serialized")
            zip_file.writestr("annotation/doc.txt.xmi/anna.xmi", cas.to_xmi())
            zip_file.writestr("annotation_ser/doc.txt.xmi/anna.ser", b"serialized")
            zip_file.writestr("curation/doc.txt.xmi/CURATION_USER.xmi", cas.to_xmi())

    def test_builds_flattened_sanitized_upload_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            source_zip = tmp_path / "project.zip"
            output_dir = tmp_path / "artifacts"
            self._write_project_zip(source_zip)
            decisions = [
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
                },
                {
                    "action": "delete",
                    "delete_annotation": True,
                    "document": "doc.txt.xmi",
                    "annotator": "CURATION_USER",
                    "source_code": "233604007",
                    "covered_text": "pneumonia",
                    "offset": [12, 21],
                    "layer": "gemtex.Concept",
                },
                {
                    "action": "delete",
                    "delete_annotation": True,
                    "document": "missing.txt",
                    "annotator": "anna",
                    "source_code": "233604007",
                    "covered_text": "pneumonia",
                    "offset": [12, 21],
                    "layer": "gemtex.Concept",
                },
            ]

            result = build_inception_upload_artifacts(
                source_zip, decisions, output_dir, repair_for_remote_upload=False
            )

            self.assertEqual(result.artifact_count, 2)
            remote_names = {artifact.remote_document_name for artifact in result.artifacts}
            self.assertEqual(remote_names, {"doc__ann-anna.xmi", "doc__curation.xmi"})
            self.assertEqual(len(result.unmatched_decisions), 1)
            self.assertEqual(result.unmatched_decisions[0]["document"], "missing.txt")
            self.assertTrue((output_dir / "doc__ann-anna.xmi").exists())
            self.assertTrue((output_dir / "doc__curation.xmi").exists())
            self.assertTrue(result.report_path.exists())

            typesystem, _ = self._typesystem_and_cas()
            anna_cas = cassis.load_cas_from_xmi(
                io.BytesIO((output_dir / "doc__ann-anna.xmi").read_bytes()),
                typesystem=typesystem,
                lenient=True,
            )
            curation_cas = cassis.load_cas_from_xmi(
                io.BytesIO((output_dir / "doc__curation.xmi").read_bytes()),
                typesystem=typesystem,
                lenient=True,
            )
            anna_concepts = list(anna_cas.select("gemtex.Concept"))
            self.assertEqual(anna_concepts[0].get("id"), "http://snomed.info/id/999999")
            self.assertEqual(list(curation_cas.select("gemtex.Concept")), [])

            report = json.loads(result.report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["mode"], "flattened-documents")
            self.assertEqual(report["artifact_count"], 2)
            self.assertEqual(
                {upload["remote_document_name"] for upload in report["uploads"]},
                {"doc__ann-anna.xmi", "doc__curation.xmi"},
            )

    def test_default_artifacts_are_repaired_for_remote_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            source_zip = tmp_path / "project.zip"
            output_dir = tmp_path / "artifacts"
            self._write_project_zip(source_zip)

            result = build_inception_upload_artifacts(source_zip, [], output_dir)

            self.assertTrue(all(artifact.remote_upload_repaired for artifact in result.artifacts))
            self.assertTrue(all(artifact.remote_upload_issue_count == 0 for artifact in result.artifacts))
            report = json.loads(result.report_path.read_text(encoding="utf-8"))
            self.assertTrue(all(upload["remote_upload_repaired"] for upload in report["uploads"]))
            self.assertTrue(all(upload["remote_upload_issue_count"] == 0 for upload in report["uploads"]))

    def test_initial_cas_and_ser_files_are_not_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            source_zip = tmp_path / "project.zip"
            output_dir = tmp_path / "artifacts"
            self._write_project_zip(source_zip)

            result = build_inception_upload_artifacts(source_zip, [], output_dir)

            self.assertEqual(
                {artifact.source_annotator for artifact in result.artifacts},
                {"anna", "CURATION_USER"},
            )
            self.assertNotIn("INITIAL_CAS", {artifact.source_annotator for artifact in result.artifacts})
            self.assertFalse(any(artifact.source_member.endswith(".ser") for artifact in result.artifacts))


if __name__ == "__main__":
    unittest.main()
