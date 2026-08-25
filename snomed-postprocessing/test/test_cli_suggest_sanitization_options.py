import unittest

from click.testing import CliRunner

from snomed_post_processing.cli.app import suggest_sanitization_cli


class TestSuggestSanitizationCliOptions(unittest.TestCase):
    def test_release_view_options_are_exposed(self):
        result = CliRunner().invoke(suggest_sanitization_cli, ["--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--target-view", result.output)
        self.assertIn("policy", result.output)
        self.assertIn("release", result.output)
        self.assertIn("--custom-blacklist", result.output)
        self.assertIn("--enforce-embedded-blacklist", result.output)
        self.assertNotIn("--release-exclude-blacklist", result.output)
        self.assertNotIn("--release-include-blacklist", result.output)


if __name__ == "__main__":
    unittest.main()
