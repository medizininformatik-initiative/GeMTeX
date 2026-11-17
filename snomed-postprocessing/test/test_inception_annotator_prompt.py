"""Click prompt tests without project processing or network calls."""
import io
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import click
from click.testing import CliRunner

from snomed_post_processing.inception.io import prompt_for_names


class AnnotatorPromptTest(unittest.TestCase):
    def choose(self, text, names=None):
        selected = []

        @click.command()
        def command():
            selected.append(prompt_for_names({"carol", "alice", "bob"} if names is None else names))

        result = CliRunner().invoke(command, input=text)
        return result, selected

    def test_zero_or_one_annotator_does_not_prompt(self):
        for names in (set(), {"Alice"}):
            with self.subTest(names=names), patch("click.confirm") as confirm, patch("click.prompt") as prompt:
                self.assertIsNone(prompt_for_names(names))
                confirm.assert_not_called()
                prompt.assert_not_called()

    def test_include_all_returns_none_without_selection(self):
        result, selected = self.choose("y\n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(selected, [None])
        self.assertNotIn("Select annotators", result.output)

    def test_numbered_selection_is_sorted_and_preserves_original_names(self):
        result, selected = self.choose("n\n1,3\n", {"carol", "Alice", "bob"})
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(selected, [["Alice", "carol"]])
        self.assertIn("1. Alice\n2. bob\n3. carol", result.output)

    def test_include_all_defaults_to_no(self):
        result, selected = self.choose("\n2\n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(selected, [["bob"]])

    def test_whitespace_duplicates_and_selection_order(self):
        result, selected = self.choose("n\n 3, 1, 3 \n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(selected, [["carol", "alice"]])

    def test_names_with_commas_are_selected_by_number(self):
        result, selected = self.choose("n\n1\n", {"Alice, MD", "Bob Smith"})
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(selected, [["Alice, MD"]])

    def test_invalid_selection_reprompts_without_including_all(self):
        for invalid in (" ", ",", "1,", ",1", "1,,2", "0", "-1", "4", "alice", "1.5", "1 2", "1,999"):
            with self.subTest(invalid=invalid):
                result, selected = self.choose(f"n\n{invalid}\n2\n")
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(selected, [["bob"]])
                self.assertIn("Error:", result.output)

    def test_blank_selection_reprompts(self):
        result, selected = self.choose("n\n\n2\n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(selected, [["bob"]])
        self.assertGreaterEqual(result.output.count("Select annotators"), 2)

    def test_eof_aborts_instead_of_including_all(self):
        # Click 8.1's CliRunner treats exhausted input as blank lines, not EOF.
        # Inject real EOFError at each prompt instead of looping in the runner.
        for inputs in ([EOFError], ["n", EOFError], ["n", "", EOFError], ["n", "0", EOFError]):
            with self.subTest(inputs=inputs), patch(
                "click.termui.visible_prompt_func", side_effect=inputs
            ), redirect_stdout(io.StringIO()):
                with self.assertRaises(click.Abort):
                    prompt_for_names({"alice", "bob"})

    def test_keyboard_interrupt_aborts_at_both_prompts(self):
        with patch("click.termui.visible_prompt_func", side_effect=KeyboardInterrupt), redirect_stdout(io.StringIO()):
            with self.assertRaises(click.Abort):
                prompt_for_names({"alice", "bob"})
        with patch("click.confirm", return_value=False), patch(
            "click.termui.visible_prompt_func", side_effect=KeyboardInterrupt
        ), redirect_stdout(io.StringIO()):
            with self.assertRaises(click.Abort):
                prompt_for_names({"alice", "bob"})

    def test_pipeline_forbid_prompt_and_cancellation_guards(self):
        from snomed_post_processing.pipelines import document_logging as pipeline

        class ReachedProcessing(Exception):
            pass

        with tempfile.TemporaryDirectory() as directory:
            project = pathlib.Path(directory) / "project.zip"
            policy = pathlib.Path(directory) / "policy.hdf5"
            project.touch()
            policy.touch()
            for forbid_prompt in (True, False):
                with self.subTest(forbid_prompt=forbid_prompt), patch.object(
                    pipeline, "get_project_zip", return_value=project
                ), patch.object(pipeline, "set_log_level"), patch.object(
                    pipeline, "get_annotator_names", return_value=({"alice", "bob"}, False)
                ), patch.object(pipeline, "prompt_for_names", side_effect=click.Abort) as prompt, patch.object(
                    pipeline, "process_inception_zip", side_effect=ReachedProcessing
                ) as process:
                    with self.assertRaises(ReachedProcessing if forbid_prompt else click.Abort):
                        pipeline.run_log_documents(
                            process_path=str(project), lists_path=str(policy), ip="localhost", port=8080,
                            use_secure_protocol=False, inception_username=None, inception_password=None,
                            inception_project=None, log_level="INFO", keep_export=False, omit_dump=True,
                            forbid_prompt=forbid_prompt, annotation_type=("gemtex.Concept",),
                            ignore_overlap_type=(), ignore_overlap_mode="overlap",
                        )
                    if forbid_prompt:
                        prompt.assert_not_called()
                        self.assertIsNone(process.call_args.kwargs["annotator_filter"])
                    else:
                        prompt.assert_called_once()
                        process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
