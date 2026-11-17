"""Offline checks for the parallel GUI packages and relocated script entry point."""
import importlib
import pathlib
import subprocess
import sys
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from snomed_post_processing.gui.streamlit.sidebar import GuiInputs


class StreamlitRelocationTest(unittest.TestCase):
    def test_gui_namespace_does_not_import_either_framework(self):
        result = subprocess.run(
            [sys.executable, "-I", "-c", "import sys; import snomed_post_processing.gui; assert 'streamlit' not in sys.modules; assert 'nicegui' not in sys.modules"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_relocated_script_launches_with_no_project_or_remote_calls(self):
        package = importlib.import_module("snomed_post_processing.gui.streamlit")
        app_path = pathlib.Path(package.__file__).with_name("app.py")
        inputs = GuiInputs(
            load_annotators=False, hdf5_file=None, annotation_types_text="gemtex.Concept",
            ignore_overlap_types_text="", ignore_overlap_mode="overlap", id_prefix="", id_feature="id",
            data_dir=pathlib.Path("."), target_view="policy",
        )
        with patch("snomed_post_processing.gui.streamlit.sidebar.render_sidebar", return_value=inputs), patch(
            "snomed_post_processing.gui.streamlit.policy_tab.render_policy_tab"
        ) as policy, patch(
            "snomed_post_processing.gui.streamlit.sanitization_check_tab.render_sanitization_check_tab"
        ) as suggestions, patch(
            "snomed_post_processing.gui.streamlit.sanitization_run_tab.render_sanitization_run_tab"
        ) as review:
            app = AppTest.from_file(str(app_path)).run(timeout=10)
        self.assertFalse(app.exception)
        self.assertEqual([tab.label for tab in app.tabs], ["1. Check policy", "2. Suggest policy sanitization", "3. Review & apply"])
        for renderer in (policy, suggestions, review):
            renderer.assert_called_once_with(inputs)


if __name__ == "__main__":
    unittest.main()
