"""Masked CSV matches NiceGUI overview fields without changing its source."""
import copy
import csv
import io
from types import SimpleNamespace
import unittest

from snomed_post_processing.gui.nicegui.suggestion_ui import masked_preview_csv


class MaskedOverviewTest(unittest.TestCase):
    def test_only_identity_columns_change_and_export_order_is_stable(self):
        rows = [SimpleNamespace(document=document, annotator=annotator, code="00123", status="Manual",
                                proposed_code="00456", candidate_count=2, text="Clinical name, café\nsecond line")
                for document, annotator in (("private-b", "Bob"), ("private-a", "Alice"), ("private-b", "Alice"))]
        preview = SimpleNamespace(findings=rows)
        before = copy.deepcopy([vars(row) for row in rows])
        content = masked_preview_csv(preview)
        self.assertTrue(content.startswith(b"\xef\xbb\xbf"))
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        exported = list(reader)
        self.assertEqual(reader.fieldnames, ["Document", "Annotator", "Source code", "Status", "Replacement code", "Candidate count", "Top candidates", "Diagnostic candidates (not selectable)", "Covered text"])
        self.assertEqual([row["Document"] for row in exported], ["document-1", "document-2", "document-1"])
        self.assertEqual([row["Annotator"] for row in exported], ["annotator-1", "annotator-2", "annotator-2"])
        for row in exported:
            self.assertEqual(row["Source code"], "00123")
            self.assertEqual(row["Replacement code"], "00456")
            self.assertEqual(row["Status"], "Manual")
            self.assertEqual(row["Candidate count"], "2")
            self.assertEqual(row["Covered text"], rows[0].text)
        self.assertEqual([vars(row) for row in rows], before)

    def test_export_uses_artifact_scope_not_unfiltered_suggestions(self):
        import json
        from pathlib import Path
        from snomed_post_processing.gui.nicegui.suggestions import load_suggestions_preview
        content = json.loads((Path(__file__).parent / "projects/synthetic-annotator-scope/suggestions.json").read_text(encoding="utf-8"))
        content["metadata"]["annotators"] = ["alice"]
        preview = load_suggestions_preview(json.dumps(content).encode(), "scoped.json")
        exported = list(csv.DictReader(io.StringIO(masked_preview_csv(preview).decode("utf-8-sig"))))
        self.assertEqual(len(exported), 5)
        self.assertEqual(len(preview.source_suggestions), 10)
        self.assertEqual({row["Annotator"] for row in exported}, {"annotator-1"})

    def test_empty_overview_retains_headers(self):
        content = masked_preview_csv(SimpleNamespace(findings=()))
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        self.assertEqual(list(reader), [])
        self.assertIn("Document", reader.fieldnames)
        self.assertIn("Annotator", reader.fieldnames)


if __name__ == "__main__":
    unittest.main()
