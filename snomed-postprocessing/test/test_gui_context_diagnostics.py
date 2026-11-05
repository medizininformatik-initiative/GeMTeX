"""Console diagnostics for review context extraction; no clinical text in logs."""
import io
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

from snomed_post_processing.gui import sanitization_run_tab as tab


class TestContextDiagnostics(unittest.TestCase):
    def extract(self, paths, loader):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w"):
            pass
        with patch.object(tab, "_read_project", return_value={}), \
             patch.object(tab, "_yield_matching_files", return_value=paths), \
             patch.object(tab, "_load_typesystem_from_zip", return_value=None), \
             patch.object(tab, "_load_cas_from_zip_member", side_effect=loader):
            return tab._extract_project_document_texts(data.getvalue(), "project.zip")

    def test_failed_member_is_logged_and_next_member_is_used(self):
        with self.assertLogs(tab.logger, level="WARNING") as logs:
            lookup = self.extract(
                [("doc.txt", ["bad.xmi", "good.xmi"])],
                [ValueError("broken CAS"), SimpleNamespace(sofa_string="private document text")],
            )
        output = "\n".join(logs.output)
        self.assertIn("CAS loading", output)
        self.assertIn("bad.xmi", output)
        self.assertIn("ValueError", output)
        self.assertIn("loaded=1", output)
        self.assertNotIn("private document text", output)
        self.assertEqual(lookup["doc.txt"], "private document text")

    def test_empty_sofa_is_logged(self):
        with self.assertLogs(tab.logger, level="WARNING") as logs:
            lookup = self.extract(
                [("doc.txt", ["empty.xmi"])],
                [SimpleNamespace(sofa_string="", get_sofa=lambda: SimpleNamespace(sofaString=""))],
            )
        self.assertEqual(lookup, {})
        self.assertIn("CAS has no document text", "\n".join(logs.output))

    def test_no_matching_documents_is_logged(self):
        with self.assertLogs(tab.logger, level="WARNING") as logs:
            self.assertEqual(self.extract([], []), {})
        self.assertIn("No matching JSON/XMI", "\n".join(logs.output))

    def test_missing_document_names_logged_once(self):
        finding = SimpleNamespace(document="missing.txt", annotator="user", code="123", offset=(1, 2))
        with patch.object(tab, "st", SimpleNamespace(session_state={})), \
             self.assertLogs(tab.logger, level="WARNING") as logs:
            tab._log_missing_context_documents([SimpleNamespace(finding=finding)], {}, {})
            tab._log_missing_context_documents([SimpleNamespace(finding=finding)], {}, {})
        self.assertEqual(len(logs.output), 1)
        self.assertIn("missing.txt", logs.output[0])

    def test_bad_zip_is_logged_and_empty_lookup_cached(self):
        state = {}
        with patch.object(tab, "st", SimpleNamespace(session_state=state)), \
             patch.object(tab, "_selected_file_key", return_value="test-key"), \
             self.assertLogs(tab.logger, level="WARNING") as logs:
            self.assertEqual(tab._project_document_text_lookup(io.BytesIO(b"not a ZIP")), {})
        self.assertIn("Could not extract review context", "\n".join(logs.output))
        self.assertEqual(state["sanitization_project_text_lookup"], {})


if __name__ == "__main__":
    unittest.main()
