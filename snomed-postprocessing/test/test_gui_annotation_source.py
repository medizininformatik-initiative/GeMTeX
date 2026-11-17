"""Installed Streamlit widget flow for SQLite project replacement."""
from pathlib import Path
import tempfile
import unittest

from streamlit.testing.v1 import AppTest

from test.test_annotation_source import FIXTURE, make_store


class GuiAnnotationSourceTest(unittest.TestCase):
    def test_sqlite_backed_review_cannot_run_cas_writeback(self):
        for source in ("annotations.sqlite", str(FIXTURE / "project.zip")):
            with self.subTest(source=source):
                app = AppTest.from_string(f'''
import pathlib
import streamlit as st
from snomed_post_processing.gui.streamlit.sanitization_run_tab import _render_sanitization_run_controls
st.session_state["zip_file"] = pathlib.Path({source!r})
st.session_state["sanitization_suggestions_metadata"] = {{"store_scope": "*:annotation"}}
_render_sanitization_run_controls([], "{{}}", selected_count=1, has_invalid_selected_rows=False)
''').run()
                self.assertFalse(app.exception, str(app.exception))
                self.assertTrue(next(widget for widget in app.button if widget.label == "Run sanitization").disabled)
                self.assertTrue(any("read-only" in item.value for item in app.info))

    def test_sidebar_scope_and_policy_check_need_no_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = make_store(Path(directory) / "annotations.sqlite")
            original = store.read_bytes()
            app = AppTest.from_string(f'''
import streamlit as st
from snomed_post_processing.gui.streamlit.sidebar import render_sidebar
from snomed_post_processing.gui.streamlit.policy_tab import render_policy_tab
st.session_state.setdefault("annotation_store_sqlite_path_text", {str(store)!r})
st.session_state.setdefault("snomed_hdf5_path_text", {str(FIXTURE / "policy.hdf5")!r})
from unittest.mock import patch
def source_mode(*args, **kwargs):
    return "Server path" if kwargs.get("key") in ("annotation_store_sqlite_source", "snomed_hdf5_source") else kwargs["default"]
# AppTest cannot round-trip single-value segmented controls in this Streamlit version.
with patch("streamlit.segmented_control", side_effect=source_mode):
    inputs = render_sidebar()
    render_policy_tab(inputs)
''').run(timeout=10)
            next(widget for widget in app.selectbox if widget.label == "Annotation source").set_value("Annotation store (SQLite)").run()
            self.assertFalse(app.exception, str(app.exception))
            self.assertTrue(next(widget for widget in app.button if widget.label == "Run policy check").disabled)
            self.assertNotIn("critical_findings", app.session_state)
            next(widget for widget in app.button if widget.label == "Inspect SQLite scopes").click().run()
            self.assertFalse(app.exception, str(app.exception))
            self.assertEqual(app.session_state["annotation_store_scope"], "*:annotation")
            self.assertNotIn("critical_findings", app.session_state)
            next(widget for widget in app.button if widget.label == "Run policy check").click().run(timeout=10)
            self.assertFalse(app.exception, str(app.exception))
            self.assertEqual(len(app.session_state["critical_findings"]), 10)
            self.assertEqual(app.session_state["critical_findings_store_scope"], "*:annotation")
            self.assertEqual(store.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
