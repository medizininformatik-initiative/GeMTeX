import io
import json
import pathlib
import tempfile
import unittest
import zipfile
from unittest import mock

import cassis
from cassis import Cas, TypeSystem

from snomed_post_processing.pipelines.inception_deployment import (
    _prepare_remote_upload_cas_bytes,
    deploy_inception_sanitized_project,
)


class TestInceptionDeployment(unittest.TestCase):
    def _write_shell_zip(self, path: pathlib.Path):
        with zipfile.ZipFile(path, "w") as zip_file:
            zip_file.writestr("exportedproject.json", json.dumps({"name": "shell"}))

    def _jsoncas_bytes(self, *, concept_outside_sentence: bool = False) -> bytes:
        typesystem = TypeSystem()
        sentence_type = typesystem.create_type(
            "de.tudarmstadt.ukp.dkpro.core.api.segmentation.type.Sentence",
            supertypeName="uima.tcas.Annotation",
        )
        concept_type = typesystem.create_type(
            "webanno.custom.Concept", supertypeName="uima.tcas.Annotation"
        )
        typesystem.create_feature(concept_type, "id", "uima.cas.String")
        dmd_type = typesystem.create_type(
            "de.tudarmstadt.ukp.dkpro.core.api.metadata.type.DocumentMetaData",
            supertypeName="uima.cas.TOP",
        )
        cas = Cas(typesystem=typesystem, sofa_string="First sentence.\n \nHeading Gap\n \nconcept outside", sofa_mime="text/plain")
        Sentence = typesystem.get_type(sentence_type.name)
        Concept = typesystem.get_type(concept_type.name)
        DocumentMetaData = typesystem.get_type(dmd_type.name)
        cas.add(Sentence(begin=0, end=16))
        cas.add(Sentence(begin=15, end=16))
        if concept_outside_sentence:
            cas.add(Concept(begin=32, end=39, id="123"))
            cas.add(Concept(begin=40, end=47, id="456"))
        else:
            cas.add(Concept(begin=0, end=5, id="123"))
        cas.add(DocumentMetaData())
        return cas.to_json().encode("utf-8")

    def _write_artifacts(self, directory: pathlib.Path):
        directory.mkdir(parents=True, exist_ok=True)
        artifact = directory / "doc__ann-anna.json"
        artifact.write_bytes(self._jsoncas_bytes())
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

    def test_prepare_remote_upload_cas_bytes_adds_metadata_and_sentence_coverage(self):
        repaired = _prepare_remote_upload_cas_bytes(
            self._jsoncas_bytes(concept_outside_sentence=True), "jsoncas"
        )
        cas = cassis.load_cas_from_json(io.BytesIO(repaired))
        sentences = list(cas.select("de.tudarmstadt.ukp.dkpro.core.api.segmentation.type.Sentence"))
        concepts = list(cas.select("webanno.custom.Concept"))
        metadata = list(cas.select("de.tudarmstadt.ukp.clarin.webanno.api.type.CASMetadata"))
        self.assertEqual(len(concepts), 2)
        self.assertTrue(metadata)
        sentence_spans = sorted((s.begin, s.end) for s in sentences)
        sentence_texts = [cas.sofa_string[b:e] for b, e in sentence_spans]
        self.assertTrue(all(text and not text[0].isspace() and not text[-1].isspace() for text in sentence_texts))
        for previous, current in zip(sentence_spans, sentence_spans[1:]):
            self.assertLessEqual(previous[1], current[0])
        self.assertTrue(any(s.begin <= 18 <= s.end and s.begin <= 29 <= s.end for s in sentences))
        for concept in concepts:
            self.assertTrue(any(s.begin <= concept.begin <= s.end for s in sentences))
            self.assertTrue(any(s.begin <= concept.end <= s.end for s in sentences))
        self.assertEqual(
            list(cas.select("de.tudarmstadt.ukp.dkpro.core.api.metadata.type.DocumentMetaData")),
            [],
        )

    def test_apply_creates_source_document_from_cas_artifact_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            shell_zip = tmp_path / "shell.zip"
            artifacts_dir = tmp_path / "artifacts"
            self._write_shell_zip(shell_zip)
            self._write_artifacts(artifacts_dir)

            class Obj:
                pass

            project = Obj()
            project.project_id = 42
            project.project_name = "shell"
            document = Obj()
            document.document_id = 7
            annotation = Obj()
            annotation.annotation_state = "NEW"
            api = Obj()
            api.import_project = mock.Mock(return_value=project)
            api.create_document = mock.Mock(return_value=document)
            api.create_annotation = mock.Mock(return_value=annotation)
            client = Obj()
            client.api = api

            with mock.patch(
                "snomed_post_processing.pipelines.inception_deployment._pycaprio_client",
                return_value=client,
            ):
                result = deploy_inception_sanitized_project(
                    shell_project=shell_zip,
                    upload_artifacts_dir=artifacts_dir,
                    inception_url="http://localhost:8080",
                    username="admin",
                    password="password",
                    annotation_user="admin",
                    apply=True,
                )

            self.assertTrue(result.applied)
            kwargs = api.create_document.call_args.kwargs
            self.assertEqual(kwargs["document_format"], "jsoncas")
            self.assertNotEqual(kwargs["document_format"], "text")
            api.create_annotation.assert_called_once()
            self.assertEqual(api.create_annotation.call_args.kwargs["annotation_format"], "jsoncas")

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
