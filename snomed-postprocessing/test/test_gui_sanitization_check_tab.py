import pathlib
import tempfile
import unittest

import h5py
import numpy as np

from snomed_post_processing.gui.sanitization_check_tab import (
    _enforce_embedded_blacklist,
    _resolve_custom_blacklist_indices,
    _uses_custom_blacklist,
)


class GuiSanitizationCheckHelpersTest(unittest.TestCase):
    def _write_hdf5(self, path: pathlib.Path) -> None:
        string_dtype = h5py.string_dtype(encoding="utf-8")
        with h5py.File(path, "w") as h5_file:
            concepts = h5_file.create_group("concepts")
            concepts.create_dataset(
                "codes",
                data=np.asarray(["100", "200", "300", "400"], dtype=object),
                dtype=string_dtype,
            )
            concepts.create_dataset(
                "fsn",
                data=np.asarray(
                    [
                        "Root procedure (procedure)",
                        "Child procedure (procedure)",
                        "Other finding (finding)",
                        "Other disorder (disorder)",
                    ],
                    dtype=object,
                ),
                dtype=string_dtype,
            )
            concepts.create_dataset("active", data=np.asarray([True, True, True, True], dtype=bool))
            concepts.create_dataset(
                "ancestors_index",
                data=np.asarray([[0, 0], [0, 1], [1, 0], [1, 0]], dtype=np.int64),
            )
            concepts.create_dataset(
                "ancestor_concept_index",
                data=np.asarray([0], dtype=np.int64),
            )
            concepts.create_dataset(
                "ancestor_distance",
                data=np.asarray([1], dtype=np.int64),
            )

    def test_release_blacklist_mode_helpers(self):
        self.assertFalse(_enforce_embedded_blacklist("none"))
        self.assertFalse(_uses_custom_blacklist("none"))
        self.assertTrue(_enforce_embedded_blacklist("embedded"))
        self.assertFalse(_uses_custom_blacklist("embedded"))
        self.assertFalse(_enforce_embedded_blacklist("custom"))
        self.assertTrue(_uses_custom_blacklist("custom"))
        self.assertTrue(_enforce_embedded_blacklist("embedded+custom"))
        self.assertTrue(_uses_custom_blacklist("embedded+custom"))

    def test_resolve_custom_blacklist_indices_from_gui_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            hdf5_path = tmp_path / "concepts.hdf5"
            blacklist_path = tmp_path / "custom_blacklist.txt"
            self._write_hdf5(hdf5_path)
            blacklist_path.write_text("100\nfinding\n", encoding="utf-8")

            resolved_path, indices = _resolve_custom_blacklist_indices(
                hdf5_path,
                blacklist_path,
            )

        self.assertEqual(resolved_path, blacklist_path)
        self.assertEqual(indices, frozenset({0, 1, 2}))


if __name__ == "__main__":
    unittest.main()
