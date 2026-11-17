"""Reusable review context on artificial text/CAS only; no GUI or network needed."""
import copy
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from snomed_post_processing import review_context as module
from snomed_post_processing.review_context import ReviewContext


class ReviewContextTest(unittest.TestCase):
    def finding(self, **changes):
        values = dict(document="doc.txt.xmi", annotator="alice", code="123", offset=(14, 21), covered_text="covered")
        values.update(changes)
        return SimpleNamespace(**values)

    def metadata(self):
        return {"finding_contexts": [dict(document="doc.txt.xmi", annotator="alice", code="123",
                                         offset=[14, 21], context="saved snippet")]}

    def test_project_text_precedes_metadata_and_preserves_two_word_window(self):
        text = "one two three covered four five six"
        context = ReviewContext.from_metadata(self.metadata(), document_texts={"doc.txt": text})
        self.assertEqual(context.label(self.finding()), "… two three [covered] four five …")
        self.assertEqual(context.document_texts["doc.txt"], text)
        self.assertEqual(context.missing_documents([self.finding()]), [])

    def test_metadata_fallback_uses_full_identity_and_integer_offsets(self):
        context = ReviewContext.from_metadata(self.metadata())
        self.assertEqual(context.label(self.finding(offset=("14", "21"))), "saved snippet")
        for change in (dict(document="other.txt"), dict(annotator="bob"), dict(code="456"), dict(offset=(0, 7))):
            self.assertEqual(context.label(self.finding(**change)), "No full document context loaded.")
        self.assertEqual(context.missing_documents([self.finding(), self.finding(document="other.txt")]), ["other.txt"])

    def test_malformed_metadata_entries_are_skipped_without_mutating_input(self):
        metadata = self.metadata()
        metadata["finding_contexts"].extend([None, "invalid", {"offset": [1]}, {"offset": ["bad", 3]}])
        original = copy.deepcopy(metadata)
        context = ReviewContext.from_metadata(metadata)
        self.assertEqual(len(context.finding_contexts), 1)
        self.assertEqual(metadata, original)

    def test_placeholders_character_fallback_and_display_truncation_are_unchanged(self):
        self.assertEqual(ReviewContext().label(self.finding()), "No full document context loaded.")
        self.assertEqual(ReviewContext().label(self.finding(covered_text="")), "No document text context available.")
        context = ReviewContext({"doc.txt": "abcDEFghi"})
        self.assertEqual(context.label(self.finding(offset=(-3, 6))), "… [abcDEF] ghi …")
        text = "X" * 90
        context = ReviewContext({"doc.txt": text})
        self.assertIn("[" + "X" * 79 + "…]", context.label(self.finding(offset=(0, 90))))
        self.assertEqual(context.document_texts["doc.txt"], text)

    def test_zip_extraction_honors_normalized_scope_and_document_aliases(self):
        data = (Path(__file__).parent / "projects/synthetic-annotator-scope/project.zip").read_bytes()
        with patch.object(module, "_load_cas_from_zip_member", wraps=module._load_cas_from_zip_member) as loader:
            context = ReviewContext.from_project_zip(data, "project.zip", annotators=(" Alice ", "ALICE"))
        self.assertEqual(loader.call_count, 3)
        self.assertTrue(all("alice" in call.args[1].lower() for call in loader.call_args_list))
        self.assertTrue(context.document_text("rules.txt"))
        self.assertEqual(context.document_text("rules.txt.xmi"), context.document_text("rules.txt"))

    def test_instances_are_independent_and_metadata_paths_are_not_followed(self):
        first, second = ReviewContext(), ReviewContext()
        first.document_texts["doc"] = "artificial"
        self.assertEqual(second.document_texts, {})
        with patch("builtins.open", side_effect=AssertionError("must not open metadata paths")):
            context = ReviewContext.from_metadata({"project_path": "/not-opened.zip", **self.metadata()})
        self.assertEqual(context.label(self.finding()), "saved snippet")

    def test_import_does_not_load_either_gui_framework(self):
        script = "import sys; from snomed_post_processing.review_context import ReviewContext; assert 'streamlit' not in sys.modules; assert 'nicegui' not in sys.modules"
        subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
