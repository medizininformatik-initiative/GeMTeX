import pathlib
import tempfile
import unittest

import h5py
import numpy as np

from snomed_post_processing.hdf5_handling.policy import (
    candidate_validity_from_sets,
    read_allowed_candidate_indices,
    read_candidate_validity_sets,
)


class TestCandidateValidity(unittest.TestCase):
    def _write_hdf5(self, path: pathlib.Path):
        with h5py.File(path, "w") as h5_file:
            concepts = h5_file.create_group("concepts")
            concepts.create_dataset("active", data=np.asarray([True, True, False, True], dtype=bool))
            policy_views = h5_file.create_group("policy_views")
            whitelist = policy_views.create_group("whitelist").create_group("0")
            whitelist.create_dataset("concept_index", data=np.asarray([0], dtype=np.int64))
            blacklist = policy_views.create_group("blacklist").create_group("0")
            blacklist.create_dataset("concept_index", data=np.asarray([3], dtype=np.int64))

    def test_policy_candidate_validity_requires_whitelist_and_excludes_blacklist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "concepts.hdf5"
            self._write_hdf5(path)
            with h5py.File(path, "r") as h5_file:
                sets = read_candidate_validity_sets(h5_file, mode="policy")
                whitelisted = candidate_validity_from_sets(sets, 0)
                active_not_whitelisted = candidate_validity_from_sets(sets, 1)
                inactive = candidate_validity_from_sets(sets, 2)
                blacklisted = candidate_validity_from_sets(sets, 3)
                missing = candidate_validity_from_sets(sets, 99)
                allowed = read_allowed_candidate_indices(h5_file, mode="policy")

        self.assertTrue(whitelisted.acceptable)
        self.assertEqual(whitelisted.in_whitelist, True)
        self.assertFalse(active_not_whitelisted.acceptable)
        self.assertEqual(active_not_whitelisted.reason, "concept is not in whitelist")
        self.assertFalse(inactive.acceptable)
        self.assertEqual(inactive.reason, "concept is inactive")
        self.assertFalse(blacklisted.acceptable)
        self.assertEqual(blacklisted.reason, "concept is not in whitelist")
        self.assertFalse(missing.acceptable)
        self.assertEqual(allowed, frozenset({0}))

    def test_release_candidate_validity_does_not_require_whitelist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "concepts.hdf5"
            self._write_hdf5(path)
            with h5py.File(path, "r") as h5_file:
                sets = read_candidate_validity_sets(h5_file, mode="release", exclude_blacklist=True)
                active_not_whitelisted = sets.check_index(1)
                blacklisted = sets.check_index(3)
                allowed = read_allowed_candidate_indices(h5_file, mode="release", exclude_blacklist=True)

        self.assertTrue(active_not_whitelisted.acceptable)
        self.assertIsNone(active_not_whitelisted.in_whitelist)
        self.assertEqual(active_not_whitelisted.reason, "concept is active in release view")
        self.assertFalse(blacklisted.acceptable)
        self.assertEqual(blacklisted.reason, "concept is in blacklist")
        self.assertEqual(allowed, frozenset({0, 1}))

    def test_release_candidate_validity_can_ignore_blacklist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "concepts.hdf5"
            self._write_hdf5(path)
            with h5py.File(path, "r") as h5_file:
                sets = read_candidate_validity_sets(h5_file, mode="release", exclude_blacklist=False)
                blacklisted = sets.check_index(3)
                allowed = read_allowed_candidate_indices(h5_file, mode="release", exclude_blacklist=False)

        self.assertTrue(blacklisted.acceptable)
        self.assertTrue(blacklisted.in_blacklist)
        self.assertIsNone(blacklisted.in_whitelist)
        self.assertEqual(allowed, frozenset({0, 1, 3}))


if __name__ == "__main__":
    unittest.main()
