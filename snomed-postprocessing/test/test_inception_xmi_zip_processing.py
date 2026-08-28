import json
import logging
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

    def _write_flat_xmi_archive(self, path: pathlib.Path):
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

        with zipfile.ZipFile(path, "w") as zip_file:
            zip_file.writestr("SemGraSCCo_essen/.DS_Store", "ignored")
            zip_file.writestr("__MACOSX/SemGraSCCo_essen/._doc.txt.xmi", "ignored")
            zip_file.writestr("SemGraSCCo_essen/doc.txt.xmi/TypeSystem.xml", typesystem.to_xml())
            zip_file.writestr("SemGraSCCo_essen/doc.txt.xmi/annotator-a.xmi", cas.to_xmi())

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

    def _nested_cas_zip_bytes(self, typesystem: TypeSystem, cas: Cas) -> bytes:
        import io

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as nested_zip:
            nested_zip.writestr("TypeSystem.xml", typesystem.to_xml())
            nested_zip.writestr("annotation.xmi", cas.to_xmi())
        return buffer.getvalue()

    def _write_nested_zip_inception_project(self, path: pathlib.Path):
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
                    "name": "doc.txt.xmi",
                    "format": "xmi",
                    "state": "ANNOTATION_FINISHED",
                }
            ]
        }
        with zipfile.ZipFile(path, "w") as zip_file:
            zip_file.writestr("exportedproject.json", json.dumps(exported_project))
            zip_file.writestr("annotation_ser/doc.txt.xmi/INITIAL_CAS.ser", b"serialized cas")
            zip_file.writestr("annotation/doc.txt.xmi/INITIAL_CAS.zip", self._nested_cas_zip_bytes(typesystem, cas))
            zip_file.writestr("annotation_ser/doc.txt.xmi/Julie.ser", b"serialized cas")
            zip_file.writestr("annotation/doc.txt.xmi/Julie.zip", self._nested_cas_zip_bytes(typesystem, cas))

    def _write_metadata_ser_plus_flat_xmi_archive(self, path: pathlib.Path):
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
            zip_file.writestr("annotation_ser/doc.txt/annotator-ser.ser", b"serialized cas")
            zip_file.writestr("flat/doc.txt.xmi/TypeSystem.xml", typesystem.to_xml())
            zip_file.writestr("flat/doc.txt.xmi/annotator-xmi.xmi", cas.to_xmi())

    def test_flat_xmi_archive_without_exportedproject_json_is_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_zip = pathlib.Path(tmp) / "flat-project.zip"
            self._write_flat_xmi_archive(project_zip)

            annotators, only_ser = get_annotator_names(project_zip)
            corpus = process_inception_zip(project_zip)

        self.assertEqual(annotators, {"annotator-a"})
        self.assertFalse(only_ser)
        self.assertIn("annotator-a", corpus.annotators)
        self.assertIn("doc.txt", corpus.annotators["annotator-a"].documents)
        document = corpus.annotators["annotator-a"].documents["doc.txt"]
        self.assertEqual(document.snomed_codes.tolist(), [b"233604007"])
        self.assertEqual(document.text.tolist(), ["pneumonia"])

    def _write_root_level_flat_xmi_archive(self, path: pathlib.Path):
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
        with zipfile.ZipFile(path, "w") as zip_file:
            zip_file.writestr("TypeSystem.xml", typesystem.to_xml())
            zip_file.writestr("Colon_Fake_E.txt.xmi", cas.to_xmi())

    def test_nested_zip_inception_project_infers_real_annotators(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_zip = pathlib.Path(tmp) / "nested-inception-project.zip"
            self._write_nested_zip_inception_project(project_zip)

            annotators, only_ser = get_annotator_names(project_zip)
            corpus = process_inception_zip(project_zip)

        self.assertEqual(annotators, {"Julie"})
        self.assertFalse(only_ser)
        self.assertIn("Julie", corpus.annotators)
        self.assertIn("doc.txt.xmi", corpus.annotators["Julie"].documents)
        document = corpus.annotators["Julie"].documents["doc.txt.xmi"]
        self.assertEqual(document.snomed_codes.tolist(), [b"233604007"])

    def test_initial_cas_only_project_has_no_selectable_annotators(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_zip = pathlib.Path(tmp) / "initial-only-project.zip"
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
                    {"name": "doc.txt", "state": "ANNOTATION_FINISHED"},
                ]
            }
            with zipfile.ZipFile(project_zip, "w") as zip_file:
                zip_file.writestr("exportedproject.json", json.dumps(exported_project))
                zip_file.writestr("TypeSystem.xml", typesystem.to_xml())
                zip_file.writestr("annotation/doc.txt/INITIAL_CAS.xmi", cas.to_xmi())
                zip_file.writestr("annotation_ser/doc.txt/INITIAL_CAS.ser", b"serialized cas")

            annotators, only_ser = get_annotator_names(project_zip)
            corpus = process_inception_zip(project_zip)

        self.assertEqual(annotators, set())
        self.assertFalse(only_ser)
        self.assertEqual(corpus.annotators, {})

    def test_metadata_ser_export_does_not_hide_flat_xmi_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_zip = pathlib.Path(tmp) / "mixed-project.zip"
            self._write_metadata_ser_plus_flat_xmi_archive(project_zip)

            annotators, only_ser = get_annotator_names(project_zip)
            corpus = process_inception_zip(project_zip)

        self.assertIn("annotator-xmi", annotators)
        self.assertFalse(only_ser)
        self.assertIn("annotator-xmi", corpus.annotators)
        self.assertIn("doc.txt", corpus.annotators["annotator-xmi"].documents)
        document = corpus.annotators["annotator-xmi"].documents["doc.txt"]
        self.assertEqual(document.snomed_codes.tolist(), [b"233604007"])

    def test_root_level_flat_xmi_files_use_synthetic_annotator_not_document_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_zip = pathlib.Path(tmp) / "root-flat-project.zip"
            self._write_root_level_flat_xmi_archive(project_zip)

            annotators, only_ser = get_annotator_names(project_zip)
            corpus = process_inception_zip(project_zip)

        self.assertEqual(annotators, {"flat-archive"})
        self.assertFalse(only_ser)
        self.assertIn("flat-archive", corpus.annotators)
        self.assertIn("Colon_Fake_E.txt", corpus.annotators["flat-archive"].documents)
        document = corpus.annotators["flat-archive"].documents["Colon_Fake_E.txt"]
        self.assertEqual(document.snomed_codes.tolist(), [b"233604007"])

    def test_project_documents_without_cas_are_not_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_zip = pathlib.Path(tmp) / "partial-project.zip"
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
                    {"name": "doc.txt", "state": "ANNOTATION_FINISHED"},
                    {"name": "missing.txt.xmi", "state": "ANNOTATION_FINISHED"},
                ]
            }
            with zipfile.ZipFile(project_zip, "w") as zip_file:
                zip_file.writestr("exportedproject.json", json.dumps(exported_project))
                zip_file.writestr("TypeSystem.xml", typesystem.to_xml())
                zip_file.writestr("annotation/doc.txt/annotator-a.xmi", cas.to_xmi())

            records = []

            class ListHandler(logging.Handler):
                def emit(self, record):
                    records.append(record)

            handler = ListHandler(level=logging.WARNING)
            root_logger = logging.getLogger()
            root_logger.addHandler(handler)
            try:
                get_annotator_names(project_zip)
                process_inception_zip(project_zip)
            finally:
                root_logger.removeHandler(handler)

        missing_cas_warnings = [
            record
            for record in records
            if record.levelno >= logging.WARNING and "No CAS found" in record.getMessage()
        ]
        self.assertEqual(missing_cas_warnings, [])


if __name__ == "__main__":
    unittest.main()
