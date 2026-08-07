from __future__ import annotations

import pathlib
import tempfile
import unittest

import h5py

from hierarchies import load_snomed_like_hierarchy
from snomed_post_processing.hdf5_handling.dump import (
    _compute_compact_ancestor_arrays,
    dump_codes_to_hdf5,
)
from snomed_post_processing.snomed import ListDumpType


class CompactAncestorExtensionTest(unittest.TestCase):
    def setUp(self):
        self.id_to_fsn, self.parent_map = load_snomed_like_hierarchy()

    def _ancestor_map(self, use_memoization: bool = False) -> dict[str, dict[str, int]]:
        codes, index, ancestor_codes, distances = _compute_compact_ancestor_arrays(
            self.id_to_fsn,
            self.parent_map,
            use_memoization=use_memoization,
        )
        result = {}
        code_values = [str(code) for code in codes.tolist()]
        ancestor_code_values = [str(code) for code in ancestor_codes.tolist()]
        for row, code in enumerate(code_values):
            start, length = index[row]
            result[code] = {
                ancestor_code_values[i]: int(distances[i])
                for i in range(int(start), int(start + length))
            }
        return result

    def test_fixture_is_snomed_like_dag_with_depth_and_multiple_parents(self):
        self.assertGreaterEqual(len(self.id_to_fsn), 12)

        # At least 5 levels deep. Because this fixture has multiple inheritance,
        # the shortest path to the root is 5 while a longer path of 6 also exists:
        # 610000 -> 600000 -> 500000 -> 400000 -> 300000 -> 200000 -> 100000.
        ancestors = self._ancestor_map()["610000"]
        self.assertEqual(ancestors["100000"], 5)

        multi_parent_concepts = [
            code for code, parents in self.parent_map.items() if len(parents) > 1
        ]
        self.assertGreaterEqual(len(multi_parent_concepts), 4)
        self.assertIn("500000", multi_parent_concepts)
        self.assertIn("610000", multi_parent_concepts)
        self.assertIn("910000", multi_parent_concepts)
        self.assertIn("920000", multi_parent_concepts)

    def test_shortest_distances_are_used_with_multiple_inheritance(self):
        ancestors = self._ancestor_map()["610000"]

        self.assertEqual(ancestors["600000"], 1)
        self.assertEqual(ancestors["800000"], 1)
        self.assertEqual(ancestors["500000"], 2)
        self.assertEqual(ancestors["700000"], 2)

        # 300000 can be reached via:
        # - 610000 -> 600000 -> 500000 -> 400000 -> 300000, distance 4
        # - 610000 -> 800000 -> 700000 -> 300000, distance 3
        # The compact closure must store the shortest distance.
        self.assertEqual(ancestors["300000"], 3)

    def test_complex_multi_parent_concept_contains_union_of_ancestors(self):
        ancestors = self._ancestor_map()["920000"]

        expected = {
            "910000": 1,
            "610000": 1,
            "900000": 2,
            "600000": 2,
            "800000": 2,
            "500000": 2,
            "700000": 3,
            "400000": 3,
            "300000": 4,
            "200000": 5,
            "100000": 3,
        }
        for code, distance in expected.items():
            self.assertIn(code, ancestors)
            self.assertEqual(ancestors[code], distance, code)

    def test_disconnected_concept_has_no_ancestors(self):
        ancestors = self._ancestor_map()["999999"]
        self.assertEqual(ancestors, {})

    def test_memoized_and_non_memoized_outputs_are_identical(self):
        non_memoized = _compute_compact_ancestor_arrays(
            self.id_to_fsn, self.parent_map, use_memoization=False
        )
        memoized = _compute_compact_ancestor_arrays(
            self.id_to_fsn, self.parent_map, use_memoization=True
        )

        for left, right in zip(non_memoized, memoized):
            self.assertEqual(left.tolist(), right.tolist())

    def test_hdf5_extension_layout_and_existing_report_layout_coexist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "concepts.hdf5"
            dump_codes_to_hdf5(
                path,
                codes={"200000", "300000", "400000"},
                id_to_fsn_dict=self.id_to_fsn,
                list_type=ListDumpType.WHITELIST,
                parent_map=self.parent_map,
            )

            with h5py.File(path, "r") as h5_file:
                # Existing check/report layout is still present.
                self.assertIn("whitelist", h5_file)
                self.assertIn("0", h5_file["whitelist"])
                self.assertIn("codes", h5_file["whitelist/0"])
                self.assertIn("fsn", h5_file["whitelist/0"])

                # New compact extension is present and self-contained.
                self.assertIn("concepts", h5_file)
                for dataset in [
                    "codes",
                    "fsn",
                    "ancestors_index",
                    "ancestor_concept_index",
                    "ancestor_distance",
                ]:
                    self.assertIn(dataset, h5_file["concepts"])

                codes = h5_file["concepts/codes"][:].astype(str).tolist()
                index = h5_file["concepts/ancestors_index"][:]
                ancestor_indices = h5_file["concepts/ancestor_concept_index"][:]
                distances = h5_file["concepts/ancestor_distance"][:]

                row = codes.index("610000")
                start, length = index[row]
                ancestors = {
                    codes[int(ancestor_indices[i])]: int(distances[i])
                    for i in range(int(start), int(start + length))
                }
                self.assertEqual(ancestors["100000"], 5)
                self.assertEqual(ancestors["300000"], 3)

    def test_hdf5_extension_can_be_written_with_memoization(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "concepts-memoized.hdf5"
            dump_codes_to_hdf5(
                path,
                codes={"200000", "300000", "400000"},
                id_to_fsn_dict=self.id_to_fsn,
                list_type=ListDumpType.WHITELIST,
                parent_map=self.parent_map,
                use_memoization=True,
            )

            with h5py.File(path, "r") as h5_file:
                self.assertIn("concepts", h5_file)
                self.assertEqual(
                    len(h5_file["concepts/codes"]),
                    len(self.id_to_fsn),
                )

    def test_existing_concepts_extension_is_not_overwritten_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "concepts.hdf5"
            dump_codes_to_hdf5(
                path,
                codes={"200000"},
                id_to_fsn_dict=self.id_to_fsn,
                list_type=ListDumpType.WHITELIST,
                parent_map=self.parent_map,
            )

            with h5py.File(path, "r+") as h5_file:
                h5_file["concepts"].attrs["sentinel"] = "keep-me"

            dump_codes_to_hdf5(
                path,
                codes={"300000"},
                id_to_fsn_dict=self.id_to_fsn,
                list_type=ListDumpType.BLACKLIST,
                parent_map=self.parent_map,
            )

            with h5py.File(path, "r") as h5_file:
                self.assertEqual(h5_file["concepts"].attrs["sentinel"], "keep-me")

    def test_force_overwrite_list_does_not_overwrite_existing_concepts_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "concepts.hdf5"
            dump_codes_to_hdf5(
                path,
                codes={"200000"},
                id_to_fsn_dict=self.id_to_fsn,
                list_type=ListDumpType.WHITELIST,
                parent_map=self.parent_map,
            )

            with h5py.File(path, "r+") as h5_file:
                h5_file["concepts"].attrs["sentinel"] = "keep-me"

            dump_codes_to_hdf5(
                path,
                codes={"300000"},
                id_to_fsn_dict=self.id_to_fsn,
                list_type=ListDumpType.BLACKLIST,
                parent_map=self.parent_map,
                force_overwrite=True,
            )

            with h5py.File(path, "r") as h5_file:
                self.assertEqual(h5_file["concepts"].attrs["sentinel"], "keep-me")
                self.assertIn("blacklist", h5_file)

    def test_existing_concepts_extension_is_overwritten_with_force_concepts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "concepts.hdf5"
            dump_codes_to_hdf5(
                path,
                codes={"200000"},
                id_to_fsn_dict=self.id_to_fsn,
                list_type=ListDumpType.WHITELIST,
                parent_map=self.parent_map,
            )

            with h5py.File(path, "r+") as h5_file:
                h5_file["concepts"].attrs["sentinel"] = "remove-me"

            dump_codes_to_hdf5(
                path,
                codes={"300000"},
                id_to_fsn_dict=self.id_to_fsn,
                list_type=ListDumpType.BLACKLIST,
                parent_map=self.parent_map,
                force_overwrite_concepts=True,
            )

            with h5py.File(path, "r") as h5_file:
                self.assertNotIn("sentinel", h5_file["concepts"].attrs)
                self.assertIn("blacklist", h5_file)


if __name__ == "__main__":
    unittest.main()
