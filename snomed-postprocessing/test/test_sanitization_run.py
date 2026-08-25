import json
import pathlib
import tempfile
import unittest
import zipfile

from cassis import Cas, TypeSystem

from snomed_post_processing.pipelines.sanitization_run import run_sanitization
from snomed_post_processing.uima_processing import process_inception_zip


class TestSanitizationRun(unittest.TestCase):
    def _write_project_zip(self, path: pathlib.Path):
        typesystem = TypeSystem()
        concept_type = typesystem.create_type(
            "gemtex.Concept", supertypeName="uima.tcas.Annotation"
        )
        typesystem.create_feature(concept_type, "id", "uima.cas.String")
        cas = Cas(
            typesystem=typesystem,
            sofa_string="patient has pneumonia",
            sofa_mime="text/plain",
        )
        Concept = typesystem.get_type("gemtex.Concept")
        cas.add(
            Concept(
                begin=12,
                end=21,
                id="http://snomed.info/id/233604007",
            )
        )

        exported_project = {
            "source_documents": [
                {
                    "name": "doc.txt",
                    "state": "ANNOTATION_FINISHED",
                }
            ]
        }
        with zipfile.ZipFile(path, "w") as zip_file:
            zip_file.writestr("exportedproject.json", json.dumps(exported_project))
            zip_file.writestr("TypeSystem.xml", typesystem.to_xml())
            zip_file.writestr("annotation/doc.txt/annotator-a.xmi", cas.to_xmi())
            zip_file.writestr("annotation_ser/doc.txt/annotator-a.ser", b"serialized cas")

    def test_delete_annotation_decision_removes_matching_annotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            input_zip = tmp_path / "project.zip"
            output_zip = tmp_path / "sanitized.zip"
            self._write_project_zip(input_zip)
            decisions = [
                {
                    "suggestion_index": 0,
                    "action": "delete",
                    "delete_annotation": True,
                    "apply": False,
                    "valid_choice": False,
                    "annotator": "annotator-a",
                    "document": "doc.txt",
                    "source_code": "233604007",
                    "covered_text": "pneumonia",
                    "offset": [12, 21],
                    "layer": "gemtex.Concept",
                }
            ]

            result = run_sanitization(input_zip, decisions, output_zip)
            corpus = process_inception_zip(output_zip)

            self.assertEqual(result.changed_annotation_count, 1)
            self.assertEqual(result.applied_decision_count, 1)
            self.assertEqual(result.unmatched_decisions, ())
            document = corpus.annotators["annotator-a"].documents["doc.txt"]
            self.assertEqual(document.snomed_codes.tolist(), [])
            with zipfile.ZipFile(output_zip, "r") as zip_file:
                self.assertFalse(any(name.endswith(".ser") for name in zip_file.namelist()))


if __name__ == "__main__":
    unittest.main()
