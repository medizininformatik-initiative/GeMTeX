import json
import pathlib
import tempfile
import unittest
import zipfile

import cassis
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
            "name": "Example SNOMED project",
            "slug": "example-snomed-project",
            "description": "Original project description.",
            "source_documents": [
                {
                    "name": "doc.txt",
                    "state": "ANNOTATION_FINISHED",
                }
            ],
        }
        with zipfile.ZipFile(path, "w") as zip_file:
            zip_file.writestr("exportedproject.json", json.dumps(exported_project))
            zip_file.writestr("TypeSystem.xml", typesystem.to_xml())
            zip_file.writestr("annotation/doc.txt/annotator-a.xmi", cas.to_xmi())
            zip_file.writestr("annotation_ser/doc.txt/annotator-a.ser", b"serialized cas")

    def test_sanitized_export_updates_project_name_slug_and_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            input_zip = tmp_path / "project.zip"
            output_zip = tmp_path / "sanitized.zip"
            self._write_project_zip(input_zip)

            result = run_sanitization(input_zip, [], output_zip)

            self.assertEqual(result.decision_count, 0)
            with zipfile.ZipFile(output_zip, "r") as zip_file:
                project = json.loads(zip_file.read("exportedproject.json"))
            self.assertEqual(project["name"], "Example SNOMED project (sanitized)")
            self.assertEqual(project["slug"], "example-snomed-project-sanitized")
            self.assertEqual(
                project["description"],
                "Original project description.\n\nSanitized export (sanitized).",
            )

    def test_manual_edit_decision_adds_marker_and_keeps_original_annotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            input_zip = tmp_path / "project.zip"
            output_zip = tmp_path / "sanitized.zip"
            self._write_project_zip(input_zip)
            decisions = [
                {
                    "suggestion_index": 0,
                    "action": "manual_edit",
                    "manual_edit": True,
                    "delete_annotation": False,
                    "apply": False,
                    "valid_choice": False,
                    "annotator": "annotator-a",
                    "document": "doc.txt",
                    "source_code": "233604007",
                    "covered_text": "pneumonia",
                    "offset": [12, 21],
                    "layer": "gemtex.Concept",
                    "replacement_code": "999999",
                    "replacement_fsn": "Replacement concept (finding)",
                    "suggestion_status": "BM25 suggestion",
                    "review_note": "expert review required",
                }
            ]

            result = run_sanitization(input_zip, decisions, output_zip)

            self.assertEqual(result.changed_annotation_count, 1)
            self.assertEqual(result.unmatched_decisions, ())
            with zipfile.ZipFile(output_zip, "r") as zip_file:
                typesystem = cassis.load_typesystem(zip_file.open("TypeSystem.xml"))
                cas = cassis.load_cas_from_xmi(
                    zip_file.open("annotation/doc.txt/annotator-a.xmi"),
                    typesystem=typesystem,
                    lenient=True,
                )
                concepts = list(cas.select("gemtex.Concept"))
                markers = list(cas.select("webanno.custom.ManualReview"))
                project = json.loads(zip_file.read("exportedproject.json"))

            self.assertEqual(len(concepts), 1)
            self.assertEqual(concepts[0].get("id"), "http://snomed.info/id/233604007")
            self.assertEqual(len(markers), 1)
            self.assertEqual((markers[0].begin, markers[0].end), (12, 21))
            self.assertEqual(markers[0].get("source_code"), "233604007")
            self.assertEqual(markers[0].get("suggested_replacement"), "999999 — Replacement concept (finding)")
            self.assertIn("webanno.custom.ManualReview", {layer.get("name") for layer in project.get("layers", [])})

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
