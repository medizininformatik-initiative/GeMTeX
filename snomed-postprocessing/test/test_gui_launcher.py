"""Launcher tests never start a server or contact INCEpTION."""
import io
import pathlib
import runpy
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from types import ModuleType
from unittest.mock import patch

from snomed_post_processing.gui import app


class GuiLauncherTest(unittest.TestCase):
    def command(self, *arguments):
        frontend = pathlib.Path(app.__file__).resolve().parent / "streamlit" / "app.py"
        self.assertTrue(frontend.is_file())
        return [sys.executable, "-m", "streamlit", "run", str(frontend), *arguments]

    def test_default_workspace_forwards_explicit_arguments_and_exit_code(self):
        with patch("snomed_post_processing.gui.nicegui.frontend.main", return_value=17) as frontend, patch.object(
            app.subprocess, "call"
        ) as streamlit:
            result = app.main(["--port", "8081"])
        self.assertEqual(result, 17)
        frontend.assert_called_once_with(["--port", "8081"])
        streamlit.assert_not_called()

    def test_defaults_to_command_line_arguments(self):
        with patch.object(sys, "argv", ["launcher", "--show"]), patch(
            "snomed_post_processing.gui.nicegui.frontend.main", return_value=0
        ) as frontend:
            self.assertEqual(app.main(), 0)
        frontend.assert_called_once_with(["--show"])

    def test_explicit_empty_arguments_do_not_inherit_runner_arguments(self):
        with patch.object(sys, "argv", ["test-runner", "--unrelated"]), patch(
            "snomed_post_processing.gui.nicegui.frontend.main", return_value=0
        ) as frontend:
            self.assertEqual(app.main([]), 0)
        frontend.assert_called_once_with([])

    def test_direct_script_execution_uses_main_and_propagates_exit_code(self):
        with patch.object(sys, "argv", [app.__file__]), patch(
            "snomed_post_processing.gui.nicegui.frontend.main", return_value=7
        ) as frontend, self.assertRaises(SystemExit) as exited:
            runpy.run_path(app.__file__, run_name="__main__")
        self.assertEqual(exited.exception.code, 7)
        frontend.assert_called_once_with([])

    def test_reload_multiprocessing_child_reenters_without_exiting_bootstrap(self):
        with patch.object(sys, "argv", [app.__file__, "--frontend", "nicegui", "--reload"]), patch(
            "snomed_post_processing.gui.nicegui.frontend.main", return_value=0
        ) as frontend:
            runpy.run_path(app.__file__, run_name="__mp_main__")
        frontend.assert_called_once_with(["--reload"])

    def test_explicit_streamlit_selector_is_not_forwarded(self):
        with patch.object(app.subprocess, "call", return_value=0) as launch:
            self.assertEqual(app.main(["--frontend", "streamlit", "--server.port", "8502"]), 0)
        launch.assert_called_once_with(self.command("--server.port", "8502"))

    def test_file_launch_does_not_shadow_frameworks_and_restores_search_path(self):
        directory = str(pathlib.Path(app.__file__).resolve().parent)
        original = [directory, *sys.path]

        def check_path(arguments):
            self.assertNotIn(directory, sys.path)
            return 0

        with patch.object(sys, "path", original[:]), patch(
            "snomed_post_processing.gui.nicegui.frontend.main", side_effect=check_path
        ):
            self.assertEqual(app.main(["--frontend", "nicegui"]), 0)
            self.assertEqual(sys.path, original)
        with patch.object(sys, "path", original[:]), patch(
            "snomed_post_processing.gui.nicegui.frontend.main", side_effect=RuntimeError("startup failed")
        ):
            with self.assertRaisesRegex(RuntimeError, "startup failed"):
                app.main(["--frontend", "nicegui"])
            self.assertEqual(sys.path, original)

    def test_cached_local_nicegui_aliases_are_removed(self):
        directory = pathlib.Path(app.__file__).resolve().parent / "nicegui"
        local = ModuleType("nicegui")
        local.__file__ = str(directory / "__init__.py")
        child = ModuleType("nicegui.app")
        child.__file__ = str(directory / "app.py")

        def check_aliases(arguments):
            self.assertNotIn("nicegui", sys.modules)
            self.assertNotIn("nicegui.app", sys.modules)
            self.assertIn("snomed_post_processing.gui.nicegui.frontend", sys.modules)
            return 0

        with patch("snomed_post_processing.gui.nicegui.frontend.main", side_effect=check_aliases), patch.dict(
            sys.modules, {"nicegui": local, "nicegui.app": child}
        ):
            self.assertEqual(app.main(["--frontend", "nicegui"]), 0)

    def test_cached_installed_sdk_is_not_removed(self):
        sdk = ModuleType("nicegui")
        sdk.__file__ = str(pathlib.Path(sys.prefix) / "Lib/site-packages/nicegui/__init__.py")

        def check_sdk(arguments):
            self.assertIs(sys.modules["nicegui"], sdk)
            return 0

        with patch("snomed_post_processing.gui.nicegui.frontend.main", side_effect=check_sdk), patch.dict(
            sys.modules, {"nicegui": sdk}
        ):
            self.assertEqual(app.main(["--frontend", "nicegui"]), 0)

    def test_invalid_or_missing_frontend_starts_neither_server(self):
        for arguments in (["--frontend", "workspace"], ["--frontend", "other"], ["--frontend"]):
            with self.subTest(arguments=arguments), patch.object(app.subprocess, "call") as launch, patch(
                "snomed_post_processing.gui.nicegui.frontend.main"
            ) as frontend, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exited:
                    app.main(arguments)
                self.assertEqual(exited.exception.code, 2)
                launch.assert_not_called()
                frontend.assert_not_called()

    def test_backend_help_is_forwarded_to_default_workspace(self):
        with patch("snomed_post_processing.gui.nicegui.frontend.main", return_value=0) as frontend:
            self.assertEqual(app.main(["--help"]), 0)
        frontend.assert_called_once_with(["--help"])

    def test_importing_launcher_does_not_import_gui_frameworks(self):
        result = subprocess.run(
            [sys.executable, "-I", "-c", "import sys; import snomed_post_processing.gui.app; assert 'streamlit' not in sys.modules; assert 'nicegui' not in sys.modules"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
