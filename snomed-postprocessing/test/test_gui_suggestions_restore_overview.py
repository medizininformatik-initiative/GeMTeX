"""Tab 2 previews saved suggestions without regenerating them or requiring source inputs."""
import dataclasses
import io
import pathlib
import tempfile
import unittest

from streamlit.testing.v1 import AppTest

from snomed_post_processing.sanitization import sanitization_suggestions_json_text
from test.test_automatic_conditions import suggestion
from test.test_semantic_bm25_sanitization import _write_compact_hdf5


APP = '''
import pathlib
from types import SimpleNamespace
from unittest.mock import patch
import streamlit as st
from snomed_post_processing.gui.streamlit.sidebar import GuiInputs
from snomed_post_processing.gui.streamlit.sanitization_check_tab import render_sanitization_check_tab
inputs = GuiInputs(
    load_annotators=False, hdf5_file=st.session_state.get("test_hdf5"),
    annotation_types_text="gemtex.Concept", ignore_overlap_types_text="",
    ignore_overlap_mode="overlap", id_prefix="", id_feature="id",
    data_dir=pathlib.Path(st.session_state["test_root"]),
    annotators=st.session_state.get("test_scope", ()),
)
def select_source(label, **kwargs):
    source = st.session_state.get("test_source") if kwargs["key"] == "sanitization_check_suggestions_json" else None
    return SimpleNamespace(value=source, source="Server path", path=source)
with patch("streamlit.segmented_control", side_effect=lambda *args, **kwargs: kwargs["default"]), \
     patch("snomed_post_processing.gui.streamlit.sanitization_check_tab.render_file_source_selector", side_effect=select_source), \
     patch("snomed_post_processing.gui.streamlit.sanitization_check_tab.SanitizationResolver") as resolver, \
     patch("snomed_post_processing.gui.streamlit.sanitization_check_tab.apply_semantic_bm25_fallback",
           return_value=st.session_state["test_suggestions"]):
    resolver.return_value.suggest_all.return_value = st.session_state["test_suggestions"]
    render_sanitization_check_tab(inputs)
    st.session_state["test_resolver_calls"] = resolver.call_count
'''


class GuiSuggestionsRestoreOverviewTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        self.suggestions = [
            dataclasses.replace(item, finding=dataclasses.replace(item.finding, annotator=annotator))
            for item, annotator in ((suggestion(0), "bob"), (suggestion(1), "alice"))
        ]
        self.path = self.root / "suggestions.json"
        self.path.write_text(sanitization_suggestions_json_text(self.suggestions), encoding="utf-8")
        self.app = AppTest.from_string(APP)
        self.app.session_state["test_root"] = str(self.root)
        self.app.session_state["test_source"] = self.path
        self.app.session_state["test_suggestions"] = self.suggestions

    def run_app(self):
        self.app.run()
        self.assertFalse(self.app.exception, str(self.app.exception))
        self.assertFalse(self.app.error, str(self.app.error))

    def overview(self):
        tables = [frame.value for frame in self.app.dataframe if "Source code" in frame.value.columns]
        self.assertEqual(len(tables), 1)
        return tables[0]

    def test_restore_shows_one_overview_without_hdf5_and_persists_across_reruns(self):
        self.run_app()
        self.assertEqual(self.overview()["Source code"].tolist(), ["1000", "1001"])
        self.assertEqual(self.app.session_state["test_resolver_calls"], 0)
        self.assertTrue(next(button for button in self.app.button if button.label == "Generate sanitization suggestions").disabled)
        self.assertIn("Download masked overview CSV", {item.label for item in self.app.get("download_button")})
        self.run_app()
        self.assertEqual(self.overview()["Source code"].tolist(), ["1000", "1001"])
        self.assertEqual(self.app.session_state["test_resolver_calls"], 0)

    def test_overview_respects_scope_without_renumbering_or_mutating_saved_suggestions(self):
        self.app.session_state["test_scope"] = ("alice",)
        self.run_app()
        self.assertEqual(self.overview()["Annotator"].tolist(), ["alice"])
        self.assertEqual(self.overview()["#"].tolist(), [2])
        self.assertEqual(len(self.app.session_state["sanitization_suggestions"]), 2)

    def test_narrower_saved_scope_is_not_shown_as_broader_coverage(self):
        self.path.write_text(sanitization_suggestions_json_text(
            self.suggestions[1:], metadata={"annotators": ["alice"]}), encoding="utf-8")
        self.run_app()
        self.assertFalse(any("Source code" in frame.value.columns for frame in self.app.dataframe))
        self.assertTrue(any("narrower annotator scope" in item.value for item in self.app.warning))

    def test_empty_restore_has_explicit_overview_message(self):
        self.path.write_text(sanitization_suggestions_json_text([]), encoding="utf-8")
        self.run_app()
        self.assertTrue(any("No sanitization suggestions to preview" in item.value for item in self.app.info))

    def test_uploaded_json_also_shows_the_persistent_overview(self):
        upload = io.BytesIO(self.path.read_bytes())
        upload.name = "uploaded-suggestions.json"
        self.app.session_state["test_source"] = upload
        self.run_app()
        self.assertEqual(len(self.overview()), 2)
        self.run_app()
        self.assertEqual(len(self.overview()), 2)

    def test_failed_import_keeps_the_last_successful_overview(self):
        self.run_app()
        malformed = self.root / "invalid.json"
        malformed.write_text("not JSON", encoding="utf-8")
        self.app.session_state["test_source"] = malformed
        self.app.run()
        self.assertFalse(self.app.exception, str(self.app.exception))
        self.assertTrue(any("Could not load sanitization suggestions JSON" in item.value for item in self.app.error))
        self.assertEqual(self.overview()["Source code"].tolist(), ["1000", "1001"])

    def test_session_overview_remains_after_file_selector_is_cleared(self):
        self.run_app()
        self.app.session_state["test_source"] = None
        self.run_app()
        self.assertEqual(len(self.overview()), 2)

    def test_generation_updates_the_same_overview_without_duplicate_widget_keys(self):
        self.app.session_state["test_hdf5"] = self.root / "concepts.hdf5"
        _write_compact_hdf5(self.root / "concepts.hdf5")
        self.app.session_state["critical_findings"] = [item.finding for item in self.suggestions]
        self.run_app()
        self.assertEqual(len(self.overview()), 2)
        next(box for box in self.app.checkbox if box.label == "Use SNOGIT/interface terms for BM25 candidates").uncheck()
        next(button for button in self.app.button if button.label == "Apply suggestion settings").click().run()
        next(button for button in self.app.button if button.label == "Generate sanitization suggestions").click().run()
        self.assertFalse(self.app.exception, str(self.app.exception))
        self.assertFalse(self.app.error, str(self.app.error))
        self.assertEqual(self.app.session_state["test_resolver_calls"], 1)
        self.assertEqual(len(self.overview()), 2)
        self.run_app()
        self.assertEqual(len(self.overview()), 2)


if __name__ == "__main__":
    unittest.main()
