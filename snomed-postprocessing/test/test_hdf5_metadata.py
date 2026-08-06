import pathlib
import tempfile
import unittest

import h5py
import numpy as np

from snomed_post_processing.hdf5_metadata import (
    inspect_hdf5_metadata,
    format_hdf5_metadata_summary,
)

_STRING_DTYPE = h5py.string_dtype(encoding="utf-8")


class TestHdf5MetadataSummary(unittest.TestCase):
    def test_summarizes_compact_sanitization_ready_hdf5(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hdf5_path = pathlib.Path(tmpdir) / "concepts.hdf5"
            with h5py.File(hdf5_path, "w") as h5_file:
                concepts = h5_file.create_group("concepts")
                concepts.attrs["policy_date"] = "20240401"
                concepts.attrs["release_date"] = "20260401"
                concepts.attrs["rf2_view"] = "full"
                concepts.create_dataset("codes", data=np.asarray(["100", "200"], dtype=object), dtype=_STRING_DTYPE)
                concepts.create_dataset("fsn", data=np.asarray(["Old (finding)", "New (finding)"], dtype=object), dtype=_STRING_DTYPE)
                concepts.create_dataset("active", data=np.asarray([False, True], dtype=bool))
                concepts.create_dataset("semantic_tags", data=np.asarray(["finding"], dtype=object), dtype=_STRING_DTYPE)
                concepts.create_dataset("ancestors_index", data=np.asarray([0, 0, 0], dtype=np.int64))
                concepts.create_dataset("ancestors_codes", data=np.asarray([], dtype=object), dtype=_STRING_DTYPE)
                concepts.create_dataset("ancestors_distance", data=np.asarray([], dtype=np.int64))

                policy_views = h5_file.create_group("policy_views")
                whitelist = policy_views.create_group("whitelist").create_group("0")
                whitelist.create_dataset("concept_index", data=np.asarray([1], dtype=np.int64))
                blacklist = policy_views.create_group("blacklist").create_group("0")
                blacklist.create_dataset("concept_index", data=np.asarray([], dtype=np.int64))

                hist = h5_file.create_group("historical_associations")
                hist.create_dataset("source_index", data=np.asarray([0], dtype=np.int64))
                hist.create_dataset("target_index", data=np.asarray([1], dtype=np.int64))
                hist.create_dataset("association_type_id", data=np.asarray([0], dtype=np.int64))
                hist.create_dataset("association_types", data=np.asarray(["REPLACED_BY"], dtype=object), dtype=_STRING_DTYPE)
                hist.create_dataset("effective_time", data=np.asarray(["20240131"], dtype=object), dtype=_STRING_DTYPE)
                hist.create_dataset("active", data=np.asarray([True], dtype=bool))
                hist.create_dataset("refset_id", data=np.asarray(["900000000000526001"], dtype=object), dtype=_STRING_DTYPE)

            summary = inspect_hdf5_metadata(hdf5_path)
            text = format_hdf5_metadata_summary(summary)
            markdown = format_hdf5_metadata_summary(summary, markdown=True, include_path=False)

        self.assertTrue(summary.sanitization_ready)
        self.assertEqual(summary.concept_count, 2)
        self.assertEqual(summary.active_concept_count, 1)
        self.assertEqual(summary.historical_association_type_counts, (("REPLACED_BY", 1),))
        self.assertIn("Sanitization-ready: yes", text)
        self.assertIn("whitelist/0: 1 concepts", text)
        self.assertIn("  - REPLACED_BY: 1", text)
        self.assertNotIn("Types:", text)
        self.assertIn("### HDF5 metadata summary", markdown)
        self.assertNotIn(str(hdf5_path), markdown)


if __name__ == "__main__":
    unittest.main()
