import io
import unittest

from snomed_post_processing.findings_io import (
    read_critical_findings_json,
    write_critical_findings_json,
)
from snomed_post_processing.uima_processing import CriticalFinding, IgnoreOverlap


class TestFindingsIo(unittest.TestCase):
    def test_round_trips_critical_findings_json(self):
        findings = [
            CriticalFinding(
                annotator="annotator-a",
                document="doc.txt",
                code="123456",
                covered_text="alpha therapy",
                offset=(10, 23),
                list_type="whitelist",
                reason="not_in_whitelist",
                layer="gemtex.Concept",
                fsn="Old alpha concept (procedure)",
                ignored=True,
                ignore_overlaps=(
                    IgnoreOverlap(
                        layer="webanno.custom.No_Human",
                        offset=(9, 24),
                        text="alpha therapy",
                    ),
                ),
            )
        ]
        buffer = io.StringIO()

        write_critical_findings_json(findings, buffer, metadata={"command": "test"})
        buffer.seek(0)
        loaded = read_critical_findings_json(buffer)

        self.assertEqual(loaded, findings)

    def test_high_volume_models_do_not_allocate_instance_dictionaries(self):
        finding = CriticalFinding("a", "doc", "123", "text", (0, 4), "whitelist", "not_in_whitelist")
        overlap = IgnoreOverlap("ignore.Layer", (0, 4), "text")

        self.assertFalse(hasattr(finding, "__dict__"))
        self.assertFalse(hasattr(overlap, "__dict__"))

    def test_rejects_wrong_schema(self):
        buffer = io.StringIO('{"schema": "wrong", "schema_version": 1, "findings": []}')

        with self.assertRaisesRegex(ValueError, "Unsupported critical findings schema"):
            read_critical_findings_json(buffer)


if __name__ == "__main__":
    unittest.main()
