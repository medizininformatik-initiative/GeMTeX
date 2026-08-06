import json
import pathlib
import tempfile
import unittest
import zipfile

from cassis import Cas, TypeSystem

from snomed_post_processing.uima_processing import get_annotator_names, process_inception_zip


class TestInceptionXmiZipProcessing(unittest.TestCase):
    def _write_xmi_only_project_zip(self, path: pathlib.Path):
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

    def test_xmi_only_project_zip_is_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_zip = pathlib.Path(tmp) / "project.zip"
            self._write_xmi_only_project_zip(project_zip)

            annotators, only_ser = get_annotator_names(project_zip)
            corpus = process_inception_zip(project_zip)

        self.assertEqual(annotators, {"annotator-a"})
        self.assertFalse(only_ser)
        self.assertIn("annotator-a", corpus.annotators)
        self.assertIn("doc.txt", corpus.annotators["annotator-a"].documents)
        document = corpus.annotators["annotator-a"].documents["doc.txt"]
        self.assertEqual(document.snomed_codes.tolist(), [b"233604007"])
        self.assertEqual(document.text.tolist(), ["pneumonia"])


if __name__ == "__main__":
    unittest.main()
