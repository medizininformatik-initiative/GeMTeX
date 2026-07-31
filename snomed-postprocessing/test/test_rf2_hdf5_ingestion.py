import pathlib
import tempfile
import unittest
import zipfile

import h5py

from snomed_post_processing.rf2 import (
    discover_snapshot_members,
    write_snapshot_hdf5_from_rf2_zip,
)


BASE = "SnomedCT_InternationalRF2_PRODUCTION_20260401T120000Z"


def _write_rf2_zip(path: pathlib.Path):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("__MACOSX/._ignored.txt", "not\trf2\n")
        zf.writestr(
            f"{BASE}/Snapshot/Terminology/sct2_Concept_Snapshot_INT_20260401.txt",
            "id\teffectiveTime\tactive\tmoduleId\tdefinitionStatusId\n"
            "100\t20260401\t1\t900000000000207008\t900000000000074008\n"
            "200\t20260401\t1\t900000000000207008\t900000000000074008\n"
            "250\t20260401\t1\t900000000000207008\t900000000000074008\n"
            "300\t20260401\t0\t900000000000207008\t900000000000074008\n",
        )
        zf.writestr(
            f"{BASE}/Snapshot/Terminology/sct2_Description_Snapshot-en_INT_20260401.txt",
            "id\teffectiveTime\tactive\tmoduleId\tconceptId\tlanguageCode\ttypeId\tterm\tcaseSignificanceId\n"
            "d1\t20260401\t1\t900000000000207008\t100\ten\t900000000000003001\tOld thing (finding)\t900000000000448009\n"
            "d2\t20260401\t1\t900000000000207008\t200\ten\t900000000000003001\tNew thing (finding)\t900000000000448009\n"
            "d4\t20260401\t1\t900000000000207008\t250\ten\t900000000000003001\tPolicy root child (procedure)\t900000000000448009\n"
            "d3\t20260401\t1\t900000000000207008\t300\ten\t900000000000003001\tInactive thing (finding)\t900000000000448009\n",
        )
        zf.writestr(
            f"{BASE}/Snapshot/Refset/Content/der2_cRefset_AssociationSnapshot_INT_20260401.txt",
            "id\teffectiveTime\tactive\tmoduleId\trefsetId\treferencedComponentId\ttargetComponentId\n"
            "a1\t20260401\t1\t900000000000207008\t900000000000526001\t300\t200\n"
            "a2\t20260401\t0\t900000000000207008\t900000000000527005\t100\t200\n",
        )
        zf.writestr(
            f"{BASE}/Snapshot/Terminology/sct2_Relationship_Snapshot_INT_20260401.txt",
            "id\teffectiveTime\tactive\tmoduleId\tsourceId\tdestinationId\trelationshipGroup\ttypeId\tcharacteristicTypeId\tmodifierId\n"
            "r1\t20260401\t1\t900000000000207008\t100\t200\t0\t116680003\t900000000000011006\t900000000000451002\n"
            "r2\t20260401\t1\t900000000000207008\t250\t200\t0\t116680003\t900000000000011006\t900000000000451002\n",
        )


class TestRf2Hdf5Ingestion(unittest.TestCase):
    def test_discover_snapshot_members_ignores_macos_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = pathlib.Path(tmp) / "rf2.zip"
            _write_rf2_zip(zip_path)

            members = discover_snapshot_members(zip_path)

        self.assertTrue(members.concept.endswith("sct2_Concept_Snapshot_INT_20260401.txt"))
        self.assertTrue(members.description.endswith("sct2_Description_Snapshot-en_INT_20260401.txt"))
        self.assertTrue(members.association.endswith("der2_cRefset_AssociationSnapshot_INT_20260401.txt"))

    def test_add_blacklist_policy_reuses_existing_concepts(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = pathlib.Path(tmp) / "rf2.zip"
            output_path = pathlib.Path(tmp) / "rf2.hdf5"
            _write_rf2_zip(zip_path)

            first_summary = write_snapshot_hdf5_from_rf2_zip(
                zip_path,
                output_path,
                whitelist_root_codes=["200"],
            )
            second_summary = write_snapshot_hdf5_from_rf2_zip(
                zip_path,
                output_path,
                blacklist_filter_tags=["finding"],
            )

            with h5py.File(output_path, "r") as h5_file:
                self.assertIn("whitelist", h5_file["policy_views"])
                self.assertIn("blacklist", h5_file["policy_views"])
                whitelist_group = h5_file["policy_views/whitelist/0"]
                blacklist_group = h5_file["policy_views/blacklist/0"]
                whitelist_indices = whitelist_group["concept_index"][:].tolist()
                blacklist_indices = blacklist_group["concept_index"][:].tolist()
                whitelist_policy_date = whitelist_group.attrs["policy_date"]
                blacklist_policy_date = blacklist_group.attrs["policy_date"]

        self.assertEqual(first_summary.whitelist_count, 3)
        self.assertEqual(second_summary.blacklist_count, 2)
        self.assertEqual(whitelist_indices, [0, 1, 2])
        self.assertEqual(blacklist_indices, [0, 1])
        self.assertEqual(whitelist_policy_date, "20260401")
        self.assertEqual(blacklist_policy_date, "20260401")

    def test_snapshot_policy_date_must_match_release_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = pathlib.Path(tmp) / "rf2.zip"
            output_path = pathlib.Path(tmp) / "rf2.hdf5"
            _write_rf2_zip(zip_path)

            with self.assertRaisesRegex(ValueError, "Snapshot release date"):
                write_snapshot_hdf5_from_rf2_zip(
                    zip_path,
                    output_path,
                    whitelist_root_codes=["200"],
                    policy_date="20240401",
                )

    def test_rf2_parser_allows_large_fields(self):
        long_term = "A" * 140000 + " (finding)"
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = pathlib.Path(tmp) / "rf2-long-field.zip"
            output_path = pathlib.Path(tmp) / "rf2-long-field.hdf5"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr(
                    f"{BASE}/Snapshot/Terminology/sct2_Concept_Snapshot_INT_20260401.txt",
                    "id\teffectiveTime\tactive\tmoduleId\tdefinitionStatusId\n"
                    "100\t20260401\t1\t900000000000207008\t900000000000074008\n",
                )
                zf.writestr(
                    f"{BASE}/Snapshot/Terminology/sct2_Description_Snapshot-en_INT_20260401.txt",
                    "id\teffectiveTime\tactive\tmoduleId\tconceptId\tlanguageCode\ttypeId\tterm\tcaseSignificanceId\n"
                    f"d1\t20260401\t1\t900000000000207008\t100\ten\t900000000000003001\t{long_term}\t900000000000448009\n",
                )

            summary = write_snapshot_hdf5_from_rf2_zip(
                zip_path,
                output_path,
                include_associations=False,
            )

            with h5py.File(output_path, "r") as h5_file:
                fsn = h5_file["concepts/fsn"][0].decode()

        self.assertEqual(summary.concept_count, 1)
        self.assertEqual(fsn, long_term)

    def test_write_snapshot_hdf5_with_historical_associations(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = pathlib.Path(tmp) / "rf2.zip"
            output_path = pathlib.Path(tmp) / "rf2.hdf5"
            _write_rf2_zip(zip_path)

            summary = write_snapshot_hdf5_from_rf2_zip(
                zip_path,
                output_path,
                include_ancestors=True,
                whitelist_root_codes=["200"],
                blacklist_filter_tags=["finding"],
                blacklist_root_codes=["200"],
                write_legacy_policy_groups=True,
            )

            with h5py.File(output_path, "r") as h5_file:
                concept_codes = [x.decode() for x in h5_file["concepts/codes"][:]]
                fsns = [x.decode() for x in h5_file["concepts/fsn"][:]]
                semantic_tags = [x.decode() for x in h5_file["concepts/semantic_tags"][:]]
                semantic_tag_ids = h5_file["concepts/semantic_tag_id"][:].tolist()
                active = h5_file["concepts/active"][:].tolist()
                source_indices = h5_file["historical_associations/source_index"][:].tolist()
                target_indices = h5_file["historical_associations/target_index"][:].tolist()
                association_types = [x.decode() for x in h5_file["historical_associations/association_types"][:]]
                association_type_ids = h5_file["historical_associations/association_type_id"][:].tolist()
                whitelist_indices = h5_file["policy_views/whitelist/0/concept_index"][:].tolist()
                blacklist_indices = h5_file["policy_views/blacklist/0/concept_index"][:].tolist()
                legacy_whitelist_codes = [x.decode() for x in h5_file["whitelist/0/codes"][:]]
                legacy_blacklist_codes = [x.decode() for x in h5_file["blacklist/0/codes"][:]]
                whitelist_policy_date = h5_file["policy_views/whitelist/0"].attrs["policy_date"]
                blacklist_release_date = h5_file["policy_views/blacklist/0"].attrs["release_date"]
                self.assertIn("ancestors_index", h5_file["concepts"])
                self.assertNotIn("source_code", h5_file["historical_associations"])

        self.assertEqual(summary.concept_count, 4)
        self.assertEqual(summary.fsn_count, 4)
        self.assertEqual(summary.association_count, 1)
        self.assertEqual(summary.whitelist_count, 3)
        self.assertEqual(summary.blacklist_count, 3)
        self.assertEqual(concept_codes, ["100", "200", "250", "300"])
        self.assertEqual(fsns, ["Old thing (finding)", "New thing (finding)", "Policy root child (procedure)", "Inactive thing (finding)"])
        self.assertEqual(semantic_tags, ["finding", "procedure"])
        self.assertEqual(semantic_tag_ids, [0, 0, 1, 0])
        self.assertEqual(active, [True, True, True, False])
        self.assertEqual(source_indices, [3])
        self.assertEqual(target_indices, [1])
        self.assertEqual(association_types, ["REPLACED_BY"])
        self.assertEqual(association_type_ids, [0])
        self.assertEqual(whitelist_indices, [0, 1, 2])
        self.assertEqual(blacklist_indices, [0, 1, 2])
        self.assertEqual(legacy_whitelist_codes, ["100", "200", "250"])
        self.assertEqual(legacy_blacklist_codes, ["100", "200", "250"])
        self.assertEqual(whitelist_policy_date, "20260401")
        self.assertEqual(blacklist_release_date, "20260401")


if __name__ == "__main__":
    unittest.main()
