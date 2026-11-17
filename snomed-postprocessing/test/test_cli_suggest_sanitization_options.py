import pathlib
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from snomed_post_processing.cli.app import suggest_sanitization_cli


class TestSuggestSanitizationCliOptions(unittest.TestCase):
    def test_release_view_options_are_exposed(self):
        result = CliRunner().invoke(suggest_sanitization_cli, ["--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--bm25-semantic-tag-boost-percent", result.output)
        self.assertIn("--target-view", result.output)
        self.assertIn("policy", result.output)
        self.assertIn("release", result.output)
        self.assertIn("--custom-blacklist", result.output)
        self.assertIn("--enforce-embedded-blacklist", result.output)
        self.assertNotIn("--release-exclude-blacklist", result.output)
        self.assertNotIn("--release-include-blacklist", result.output)

    def test_semantic_tag_boost_is_forwarded_with_ten_percent_default(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            pathlib.Path("concepts.hdf5").touch()
            pathlib.Path("findings.json").write_text("{}", encoding="utf-8")
            arguments = ["--lists-path", "concepts.hdf5", "--critical-findings", "findings.json", "--output", "report.md"]
            for extra, expected in (([], 10.0), (["--bm25-semantic-tag-boost-percent", "37"], 37.0)):
                with patch("snomed_post_processing.cli.app.run_sanitization_check") as pipeline:
                    result = runner.invoke(suggest_sanitization_cli, arguments + extra)
                    self.assertEqual(result.exit_code, 0, result.output)
                    self.assertEqual(pipeline.call_args.kwargs["bm25_semantic_tag_boost_percent"], expected)
            for invalid in ("-1", "101"):
                result = runner.invoke(suggest_sanitization_cli, arguments + ["--bm25-semantic-tag-boost-percent", invalid])
                self.assertNotEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
