import io
import pathlib
import tempfile
import unittest

import h5py
import numpy as np

from snomed_post_processing.uima_processing import (
    DocumentAnnotations,
    IgnoreOverlap,
    TemporaryContainer,
    TemporaryCorpus,
    create_log_from_results,
    spans_match,
)


class TestIgnoreOverlapReporting(unittest.TestCase):
    def test_span_match_modes(self):
        self.assertTrue(spans_match((10, 20), (15, 25), "overlap"))
        self.assertFalse(spans_match((10, 20), (20, 25), "overlap"))
        self.assertTrue(spans_match((10, 20), (10, 20), "exact"))
        self.assertFalse(spans_match((10, 20), (10, 21), "exact"))
        self.assertTrue(spans_match((12, 18), (10, 20), "covered-by"))
        self.assertTrue(spans_match((10, 20), (12, 18), "contains"))

    def test_blacklist_logging_handles_actionable_and_ignored_split(self):
        corpus = TemporaryCorpus(
            annotators={
                "annotator-a": TemporaryContainer(
                    max_length=2,
                    documents={
                        "doc.txt": DocumentAnnotations(
                            snomed_codes=np.asarray([b"222", b"333"], dtype="bytes"),
                            offsets=np.asarray([(10, 20), (30, 40)], dtype="i,i"),
                            text=np.asarray(["ignored", "actionable"], dtype=np.dtypes.StringDType),
                            layers=np.asarray(["gemtex.Concept", "gemtex.Concept"], dtype=np.dtypes.StringDType),
                            length=2,
                            ignore_mask=np.asarray([True, False], dtype=bool),
                            ignore_overlaps=[
                                [IgnoreOverlap(layer="webanno.custom.No_Human", offset=(10, 20), text="ignored")],
                                [],
                            ],
                        )
                    },
                )
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            hdf5_path = pathlib.Path(tmp) / "lists.hdf5"
            with h5py.File(hdf5_path, "w") as h5_file:
                blacklist = h5_file.create_group("blacklist").create_group("0")
                blacklist.create_dataset("codes", data=np.asarray([b"222", b"333"]))
                blacklist.create_dataset("fsn", data=np.asarray([b"Ignored concept (finding)", b"Actionable concept (finding)"]))

            log_doc = io.StringIO()
            log_doc_masked = io.StringIO()
            err_docs = create_log_from_results(corpus, log_doc, log_doc_masked, hdf5_path)

        report = log_doc.getvalue()
        self.assertEqual(err_docs, 1)
        self.assertIn("# Blacklist\n", report)
        self.assertIn("333", report)
        self.assertIn("Actionable concept (finding)", report)
        self.assertIn("# Ignored faulty concepts", report)
        self.assertIn("## Blacklist", report)
        self.assertIn("222", report)
        self.assertIn("Ignored concept (finding)", report)
        self.assertNotIn("Overlap Details", report)

    def test_document_analysis_error_skips_only_bad_document(self):
        corpus = TemporaryCorpus(
            annotators={
                "annotator-a": TemporaryContainer(
                    max_length=1,
                    documents={
                        "bad.txt": DocumentAnnotations(
                            snomed_codes=np.asarray([b"222"], dtype="bytes"),
                            offsets=np.asarray([(10, 20)], dtype="i,i"),
                            text=np.asarray(["bad"], dtype=np.dtypes.StringDType),
                            layers=np.asarray(["gemtex.Concept"], dtype=np.dtypes.StringDType),
                            length=2,  # Deliberately inconsistent to trigger document-level safety net.
                            ignore_mask=np.asarray([False, False], dtype=bool),
                            ignore_overlaps=[[], []],
                        ),
                        "good.txt": DocumentAnnotations(
                            snomed_codes=np.asarray([b"333"], dtype="bytes"),
                            offsets=np.asarray([(30, 40)], dtype="i,i"),
                            text=np.asarray(["good"], dtype=np.dtypes.StringDType),
                            layers=np.asarray(["gemtex.Concept"], dtype=np.dtypes.StringDType),
                            length=1,
                            ignore_mask=np.asarray([False], dtype=bool),
                            ignore_overlaps=[[]],
                        ),
                    },
                )
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            hdf5_path = pathlib.Path(tmp) / "lists.hdf5"
            with h5py.File(hdf5_path, "w") as h5_file:
                blacklist = h5_file.create_group("blacklist").create_group("0")
                blacklist.create_dataset("codes", data=np.asarray([b"222", b"333"]))
                blacklist.create_dataset("fsn", data=np.asarray([b"Bad concept (finding)", b"Good concept (finding)"]))

            log_doc = io.StringIO()
            log_doc_masked = io.StringIO()
            err_docs = create_log_from_results(corpus, log_doc, log_doc_masked, hdf5_path)

        report = log_doc.getvalue()
        self.assertEqual(err_docs, 1)
        self.assertIn("good.txt", report)
        self.assertIn("333", report)
        self.assertIn("Skipped documents (blacklist)", report)
        self.assertIn("bad.txt", report)
        self.assertIn("IndexError", report)

    def test_ignored_whitelist_fault_is_reported_but_not_counted_critical(self):
        corpus = TemporaryCorpus(
            annotators={
                "annotator-a": TemporaryContainer(
                    max_length=1,
                    documents={
                        "doc.txt": DocumentAnnotations(
                            snomed_codes=np.asarray([b"222"], dtype="bytes"),
                            offsets=np.asarray([(10, 20)], dtype="i,i"),
                            text=np.asarray(["faulty text"], dtype=np.dtypes.StringDType),
                            layers=np.asarray(["gemtex.Concept"], dtype=np.dtypes.StringDType),
                            length=1,
                            ignore_mask=np.asarray([True], dtype=bool),
                            ignore_overlaps=[
                                [
                                    IgnoreOverlap(
                                        layer="gemtex.DoNotCheck",
                                        offset=(9, 21),
                                        text="faulty text",
                                    )
                                ]
                            ],
                        )
                    },
                )
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            hdf5_path = pathlib.Path(tmp) / "lists.hdf5"
            with h5py.File(hdf5_path, "w") as h5_file:
                whitelist = h5_file.create_group("whitelist").create_group("0")
                whitelist.create_dataset("codes", data=np.asarray([b"111"]))
                whitelist.create_dataset("fsn", data=np.asarray([b"Allowed concept (finding)"]))

            log_doc = io.StringIO()
            log_doc_masked = io.StringIO()
            err_docs = create_log_from_results(corpus, log_doc, log_doc_masked, hdf5_path)

        report = log_doc.getvalue()
        self.assertEqual(err_docs, 0)
        self.assertIn("# Ignored faulty concepts", report)
        self.assertIn("## Whitelist", report)
        self.assertIn("gemtex.DoNotCheck", report)
        self.assertIn("222", report)
        self.assertNotIn("Overlap Details", report)
        self.assertNotRegex(report, r"(?m)^# Whitelist$")


if __name__ == "__main__":
    unittest.main()
