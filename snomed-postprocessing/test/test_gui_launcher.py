"""Launcher tests never start a server or contact INCEpTION."""
import pathlib
import runpy
import subprocess
import sys
import unittest
from unittest.mock import patch

from snomed_post_processing.gui import app


class GuiLauncherTest(unittest.TestCase):
    def command(self, *arguments):
        frontend = pathlib.Path(app.__file__).resolve().parent / "streamlit" / "app.py"
        self.assertTrue(frontend.is_file())
        return [sys.executable, "-m", "streamlit", "run", str(frontend), *arguments]

    def test_forwards_explicit_arguments_and_exit_code(self):
        with patch.object(app.subprocess, "call", return_value=17) as launch:
            result = app.main(["--server.port", "8502"])
        self.assertEqual(result, 17)
        launch.assert_called_once_with(self.command("--server.port", "8502"))

    def test_defaults_to_command_line_arguments(self):
        with patch.object(sys, "argv", ["launcher", "--server.headless", "true"]), patch.object(
            app.subprocess, "call", return_value=0
        ) as launch:
            self.assertEqual(app.main(), 0)
        launch.assert_called_once_with(self.command("--server.headless", "true"))

    def test_explicit_empty_arguments_do_not_inherit_runner_arguments(self):
        with patch.object(sys, "argv", ["test-runner", "--unrelated"]), patch.object(
            app.subprocess, "call", return_value=0
        ) as launch:
            self.assertEqual(app.main([]), 0)
        launch.assert_called_once_with(self.command())

    def test_direct_script_execution_uses_main_and_propagates_exit_code(self):
        with patch.object(sys, "argv", [app.__file__]), patch.object(
            app.subprocess, "call", return_value=7
        ) as launch, self.assertRaises(SystemExit) as exited:
            runpy.run_path(app.__file__, run_name="__main__")
        self.assertEqual(exited.exception.code, 7)
        launch.assert_called_once_with(self.command())

    def test_importing_launcher_does_not_import_gui_frameworks(self):
        result = subprocess.run(
            [sys.executable, "-I", "-c", "import sys; import snomed_post_processing.gui.app; assert 'streamlit' not in sys.modules; assert 'nicegui' not in sys.modules"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
