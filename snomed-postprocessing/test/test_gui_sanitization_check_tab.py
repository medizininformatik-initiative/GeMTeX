import io
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import h5py
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from test.test_semantic_bm25_sanitization import _finding, _write_compact_hdf5
from snomed_post_processing.sanitization.semantic_bm25 import suggest_semantic_bm25
from snomed_post_processing.sanitization_context import masked_overview_csv as _masked_overview_csv

from snomed_post_processing.gui.streamlit.sanitization_check_tab import (
    _enforce_embedded_blacklist,
    _resolve_custom_blacklist_indices,
    _uses_custom_blacklist,
    _suggestion_overview_row,
    _render_suggestion_overview,
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

    def test_overview_issue_uses_display_labels_without_mutating_identifiers(self):
        for raw, label in (("whitelist", "inclusion list"), ("blacklist", "exclusion list"), ("other", "other")):
            with self.subTest(list_type=raw):
                finding = SimpleNamespace(
                    document="doc.txt", annotator="reviewer", code="123",
                    covered_text="example", list_type=raw, offset=(0, 7),
                )
                row = _suggestion_overview_row(1, SimpleNamespace(finding=finding))
                self.assertEqual(row["Issue"], label)
                self.assertEqual(finding.list_type, raw)

    def test_masked_overview_csv_changes_only_identity_columns(self):
        findings = [
            SimpleNamespace(document=document, annotator=annotator, code="0042",
                            covered_text='Alice,\n"clinical ± text"', offset=(10, 20), list_type="whitelist")
            for document, annotator in (("private-a.txt", "Alice"), ("private-a.txt", "Bob"), ("private-b.txt", "Alice"))
        ]
        suggestions = [SimpleNamespace(finding=finding, reason="private-a.txt remains in clinical evidence") for finding in findings]
        original = pd.DataFrame([_suggestion_overview_row(i, item) for i, item in enumerate(suggestions, start=1)])
        before = original.copy(deep=True)
        content = _masked_overview_csv(original)
        restored = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
        self.assertTrue(content.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(list(restored.columns), list(original.columns))
        self.assertEqual(restored["Document"].tolist(), ["document-1", "document-1", "document-2"])
        self.assertEqual(restored["Annotator"].tolist(), ["annotator-1", "annotator-2", "annotator-1"])
        pd.testing.assert_frame_equal(
            restored.drop(columns=["Document", "Annotator"]),
            original.drop(columns=["Document", "Annotator"]).astype(str),
        )
        pd.testing.assert_frame_equal(original, before)
        self.assertEqual(findings[0].document, "private-a.txt")
        self.assertEqual(findings[0].annotator, "Alice")
        self.assertEqual(_masked_overview_csv(original), content)

    def test_overview_download_uses_masked_data_without_triggering_rerun(self):
        suggestion = SimpleNamespace(finding=_finding())
        with patch("snomed_post_processing.gui.streamlit.sanitization_check_tab.st.data_editor") as editor, \
                patch("snomed_post_processing.gui.streamlit.sanitization_check_tab.st.download_button") as download:
            _render_suggestion_overview([suggestion])
        table = editor.call_args.args[0]
        self.assertEqual(table.iloc[0]["Document"], suggestion.finding.document)
        self.assertEqual(download.call_args.kwargs["data"], _masked_overview_csv(table))
        self.assertEqual(download.call_args.kwargs["on_click"], "ignore")
        self.assertEqual(download.call_args.kwargs["mime"], "text/csv")
        self.assertIn("not full anonymization", download.call_args.kwargs["help"])
        with patch("snomed_post_processing.gui.streamlit.sanitization_check_tab.st.download_button") as download:
            _render_suggestion_overview([])
        download.assert_not_called()

    def test_gui_boost_reaches_scoring_and_saved_suggestion_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "concepts.hdf5"
            _write_compact_hdf5(path, blacklist_indices=(3,))
            app = AppTest.from_string('''
from types import SimpleNamespace
from unittest.mock import patch
import streamlit as st
from snomed_post_processing.gui.streamlit.sidebar import GuiInputs
from snomed_post_processing.gui.streamlit.sanitization_check_tab import render_sanitization_check_tab
from snomed_post_processing.sanitization.models import SanitizationSuggestion, SanitizationStatus
from test.test_semantic_bm25_sanitization import _finding
inputs = GuiInputs(
    load_annotators=False, hdf5_file=st.session_state["test_hdf5"], annotation_types_text="gemtex.Concept",
    ignore_overlap_types_text="", ignore_overlap_mode="overlap", id_prefix="", id_feature="id",
    data_dir=st.session_state["test_root"],
)
st.session_state["critical_findings"] = [_finding()]
with patch("streamlit.segmented_control", side_effect=lambda *args, **kwargs: kwargs["default"]), \\
     patch("snomed_post_processing.gui.streamlit.sanitization_check_tab.render_file_source_selector",
           return_value=SimpleNamespace(value=None, source="none", path=None)), \\
     patch("snomed_post_processing.gui.streamlit.sanitization_check_tab.SanitizationResolver") as structured:
    structured.return_value.suggest_all.return_value = [
        SanitizationSuggestion(_finding(), SanitizationStatus.NO_HISTORICAL_ASSOCIATION)
    ]
    render_sanitization_check_tab(inputs)
''')
            app.session_state["test_hdf5"] = path
            app.session_state["test_root"] = pathlib.Path(tmp)
            app.run()
            self.assertFalse(app.exception, str(app.exception))
            next(item for item in app.checkbox if item.label == "Use SNOGIT/interface terms for BM25 candidates").uncheck()
            next(item for item in app.number_input if item.label == "Matching semantic-tag boost (%)").set_value(37.0)
            next(item for item in app.number_input if item.label == "Minimum BM25 score").set_value(0.0)
            next(item for item in app.button if item.label == "Apply suggestion settings").click().run()
            next(item for item in app.button if item.label == "Generate sanitization suggestions").click().run()
            self.assertFalse(app.exception, str(app.exception))
            self.assertFalse(app.error, str(app.error))
            self.assertIn("Download masked overview CSV", {item.label for item in app.get("download_button")})
            settings = app.session_state["sanitization_suggestions_metadata"]["settings"]
            self.assertEqual(settings["bm25_semantic_tag_boost_percent"], 37.0)
            self.assertTrue(settings["bm25_fsn_semantic_tags_excluded"])
            self.assertEqual(settings["bm25_excluded_fsn_postfixes"], ["action"])
            expected = suggest_semantic_bm25(_finding(), path, semantic_tag_boost_percent=37.0, min_score=0, min_lexical_score=0)
            actual = app.session_state["sanitization_suggestions"][0]
            self.assertAlmostEqual(actual.score, expected.score)
            self.assertEqual(actual.replacement_code, expected.replacement_code)
            from snomed_post_processing.gui.streamlit import sanitization_check_tab as tab
            render_editor = tab.st.data_editor
            # AppTest has no cell-edit API for data_editor; supply its returned rows.
            for selected, excluded in (([], []), (["unit of product usage", " Custom "], ["custom", "unit of product usage"])):
                rows = pd.DataFrame([{"Exclude": True, "Postfix": value} for value in selected], columns=["Exclude", "Postfix"])
                def edited_table(frame, **kwargs):
                    return rows if kwargs.get("key") == "bm25_fsn_postfix_editor" else render_editor(frame, **kwargs)
                previous = app.session_state["sanitization_suggestions_metadata"]["settings"]["bm25_excluded_fsn_postfixes"]
                with patch.object(tab.st, "data_editor", side_effect=edited_table):
                    next(item for item in app.button if item.label == "Apply suggestion settings").click().run()
                    self.assertFalse(app.exception, str(app.exception))
                    self.assertEqual(app.session_state["sanitization_suggestions_metadata"]["settings"]["bm25_excluded_fsn_postfixes"], previous)
                    next(item for item in app.button if item.label == "Generate sanitization suggestions").click().run()
                    self.assertFalse(app.exception, str(app.exception))
                    self.assertEqual(app.session_state["sanitization_suggestions_metadata"]["settings"]["bm25_excluded_fsn_postfixes"], excluded)

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
