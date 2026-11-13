"""Manual review/artifact equivalence on artificial inputs; no network/project writes."""
import asyncio
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from snomed_post_processing.gui.nicegui.demo import create_demo_state
from snomed_post_processing.gui.nicegui.review import ReviewError, ReviewSession, load_review
from snomed_post_processing.gui.nicegui.suggestions import load_suggestions_preview
from snomed_post_processing.sanitization.decisions_json import read_sanitization_decisions_json
from test.test_nicegui_suggestions import payload, encoded, fake_ui, upload_event, open_context, switch_document

FIXTURE = Path(__file__).parent / "projects/synthetic-annotator-scope"


def state():
    return load_suggestions_preview(encoded(payload()))


def artifact(decisions, metadata=None):
    return encoded(dict(schema="snomed-post-processing.sanitization-decisions", schema_version=1,
                        decisions=decisions, metadata=metadata or {}))


class ReviewSessionTest(unittest.TestCase):
    def test_navigation_does_not_stage_or_save_and_demo_cannot_export(self):
        source = state()
        source.select_finding(source.findings[0].row_id)
        source.preview_candidate(source.findings[0].candidates[0].row_id)
        review = ReviewSession(source)
        self.assertFalse(review.dirty)
        decisions, _ = read_sanitization_decisions_json(io.StringIO(review.export_text()))
        self.assertFalse(decisions[0]["apply"])
        self.assertFalse(decisions[0]["reviewed_by_human"])
        with self.assertRaises(ReviewError):
            ReviewSession(create_demo_state()).export_text()

    def test_candidate_is_only_saved_by_explicit_save_and_roundtrips(self):
        source = state(); row = source.findings[0]; review = ReviewSession(source)
        review.stage(row.row_id, row.candidates[1].row_id)
        self.assertFalse(review.saved)
        with self.assertRaisesRegex(ReviewError, "Save choices"):
            review.export_text()
        review.mark_document(row.row_id, True)
        review.save()
        restored = load_review(review.export_text().encode(), source)
        self.assertEqual(restored.saved, review.saved)
        self.assertEqual(restored.reviewed_documents, {row.document})
        item = restored.saved[0]
        self.assertEqual(item["replacement_code"], row.candidates[1].code)
        self.assertEqual(item["source_code"], row.code)
        self.assertEqual(item["covered_text"], row.text)
        self.assertTrue(item["apply"] and item["valid_choice"] and item["reviewed_by_human"])

    def test_delete_and_manual_review_are_exclusive_saved_actions_with_backend_flags(self):
        for action, resolved in (("delete", True), ("manual_edit", False)):
            with self.subTest(action=action):
                source = state(); row = source.findings[0]; review = ReviewSession(source)
                review.stage(row.row_id, row.candidates[0].row_id)
                review.stage(row.row_id, action=action)
                self.assertTrue(review.dirty)
                self.assertEqual(review.saved, {})
                review.save()
                item = json.loads(review.export_text())["decisions"][0]
                self.assertEqual(item["action"], action)
                self.assertEqual(item["delete_annotation"], action == "delete")
                self.assertEqual(item["manual_edit"], action == "manual_edit")
                self.assertEqual(item["resolved"], resolved)
                self.assertFalse(item["apply"])
                self.assertFalse(item["valid_choice"])
                self.assertTrue(item["reviewed_by_human"])
                self.assertIsNone(item["replacement_code"])
                self.assertNotIn("manual_candidate", item)
                self.assertFalse(review.protected(row))  # Local actions remain reversible.
                restored = load_review(review.export_text().encode(), source)
                self.assertTrue(restored.protected(row))  # Existing import protection is unchanged.
                self.assertEqual(json.loads(restored.export_text())["decisions"][0], item)
                review.stage(row.row_id); review.save()
                self.assertEqual(review.saved[0]["action"], "none")

    def test_accept_suggestion_uses_unique_saved_proposal_not_inspected_or_first_candidate(self):
        data = payload(); data["suggestions"][0]["replacement_code"] = "990000202"
        source = load_suggestions_preview(encoded(data)); row = source.findings[0]
        source.select_finding(row.row_id); source.preview_candidate(row.candidates[2].row_id)
        review = ReviewSession(source)
        review.accept_suggestion(row.row_id)
        self.assertEqual(review.saved, {})
        review.save()
        self.assertEqual(review.saved[0]["replacement_code"], "990000202")
        self.assertEqual(review.saved[0]["manual_candidate_ordinal"], 1)
        self.assertEqual(source.selected_candidate_id, row.candidates[2].row_id)

    def test_accept_suggestion_rejects_missing_unavailable_context_only_and_duplicate_proposals(self):
        for kind in ("missing", "unavailable", "context_only", "duplicate"):
            with self.subTest(kind=kind):
                data = payload(); suggestion = data["suggestions"][0]
                suggestion["replacement_code"] = "990000201"
                if kind == "missing":
                    suggestion["replacement_code"] = None
                elif kind == "unavailable":
                    suggestion["replacement_code"] = "990000404"
                elif kind == "context_only":
                    suggestion["candidates"] = suggestion["candidates"][1:]
                else:
                    duplicate = copy.deepcopy(suggestion["candidates"][0])
                    duplicate.update(source="snogit", source_member="toy.dat")
                    suggestion["candidates"].append(duplicate)
                source = load_suggestions_preview(encoded(data)); review = ReviewSession(source)
                with self.assertRaisesRegex(ReviewError, "unique selectable saved proposal"):
                    review.accept_suggestion(source.findings[0].row_id)
                self.assertFalse(review.dirty)

    def test_nonreplacement_actions_cannot_smuggle_candidate_evidence(self):
        source = state(); row = source.findings[0]; review = ReviewSession(source)
        for action in ("delete", "manual_edit", "none", "unsupported"):
            with self.assertRaises(ReviewError):
                review.stage(row.row_id, row.candidates[0].row_id, action=action)
        with self.assertRaises(ReviewError):
            review.stage(row.row_id, action="replace")
        self.assertFalse(review.dirty)

    def test_keep_is_explicit_and_not_deletion_or_clear_id(self):
        source = state(); row = source.findings[0]; review = ReviewSession(source)
        review.stage(row.row_id); review.save()
        item = review.saved[0]
        self.assertEqual(item["action"], "none")
        self.assertIsNone(item["replacement_code"])
        self.assertFalse(item["apply"] or item["delete_annotation"] or item["manual_edit"])
        self.assertTrue(item["reviewed_by_human"])
        self.assertEqual(review.status(row), "Saved Keep")

    def test_context_foreign_snapshot_and_foreign_finding_are_rejected(self):
        source = state(); row = source.findings[0]; review = ReviewSession(source)
        for finding_id, candidate_id in ((row.row_id, row.candidates[-1].row_id),
                                         (row.row_id, state().findings[0].candidates[0].row_id),
                                         ("stale", None)):
            with self.subTest(finding_id=finding_id), self.assertRaises(ReviewError):
                review.stage(finding_id, candidate_id)
        self.assertFalse(review.dirty)

    def test_discard_preserves_saved_choices_and_flags(self):
        source = state(); row = source.findings[0]; review = ReviewSession(source)
        review.stage(row.row_id); review.mark_document(row.row_id, True); review.save()
        saved = copy.deepcopy(review.saved)
        review.stage(row.row_id, row.candidates[0].row_id); review.mark_document(row.row_id, False)
        review.discard()
        self.assertEqual(review.saved, saved)
        self.assertEqual(review.reviewed_documents, {row.document})

    def test_invalid_batch_is_not_partially_saved(self):
        source = state(); review = ReviewSession(source)
        review.stage(source.findings[0].row_id)
        review.drafts["stale"] = None
        with self.assertRaises(ReviewError): review.save()
        self.assertFalse(review.saved)

    def test_fingerprint_detects_changed_candidates_and_old_index_identity(self):
        source = state(); original = ReviewSession(source).export_text().encode()
        changed = payload(); changed["suggestions"][0]["candidates"][0]["score"] = 3
        with self.assertRaisesRegex(ReviewError, "match"):
            load_review(original, load_suggestions_preview(encoded(changed)))
        data = json.loads(original); data["metadata"].pop("nicegui_suggestions_sha256")
        data["decisions"][0]["source_code"] = "DO_NOT_ECHO"
        with self.assertRaises(ReviewError) as error: load_review(encoded(data), source)
        self.assertNotIn("DO_NOT_ECHO", str(error.exception))

    def test_import_validates_scope_without_renumbering(self):
        data = json.loads((FIXTURE / "suggestions.json").read_text())
        data["metadata"]["annotators"] = ["alice"]
        source = load_suggestions_preview(encoded(data))
        review = load_review((FIXTURE / "staged-decisions.json").read_bytes(), source)
        decisions, metadata = read_sanitization_decisions_json(io.StringIO(review.export_text()))
        self.assertTrue(all(item["annotator"] == "alice" for item in decisions))
        self.assertEqual(metadata["annotators"], ["alice"])
        self.assertEqual(sorted(review.saved), [1, 2, 3, 8])
        broader = load_suggestions_preview((FIXTURE / "suggestions.json").read_bytes())
        with self.assertRaisesRegex(ReviewError, "narrower"):
            load_review(review.export_text().encode(), broader)

    def test_streamlit_fixture_roundtrip_preserves_rules_choices_and_provenance(self):
        source = load_suggestions_preview((FIXTURE / "suggestions.json").read_bytes())
        content = (FIXTURE / "staged-decisions.json").read_bytes()
        expected = json.loads(content)
        review = load_review(content, source)
        decisions, metadata = read_sanitization_decisions_json(io.StringIO(review.export_text()))
        self.assertEqual(decisions, expected["decisions"])
        for key in ("concept_rules", "concept_rule_scope", "id_feature", "id_prefix", "automatic_reviewed_documents"):
            self.assertEqual(metadata[key], expected["metadata"][key])
        reserved = next(row for row in source.findings if review.protected(row))
        with self.assertRaisesRegex(ReviewError, "protected"):
            review.stage(reserved.row_id)

    def test_imported_manual_edit_and_delete_are_protected(self):
        source = state(); base = json.loads(ReviewSession(source).export_text())
        for action in ("manual_edit", "delete", "clear_id"):
            data = copy.deepcopy(base); data["decisions"][0]["action"] = action
            review = load_review(encoded(data), source)
            with self.assertRaisesRegex(ReviewError, "protected"):
                review.stage(source.findings[0].row_id)
            self.assertEqual(json.loads(review.export_text())["decisions"], data["decisions"])

    def test_unrelated_save_preserves_imported_automatic_provenance(self):
        source = load_suggestions_preview((FIXTURE / "suggestions.json").read_bytes())
        review = load_review((FIXTURE / "staged-decisions.json").read_bytes(), source)
        before = copy.deepcopy(review.saved[1])
        row = next(row for row in source.findings if row.suggestion_index == 2)
        review.stage(row.row_id); review.save()
        self.assertEqual(review.saved[1], before)
        auto_row = next(row for row in source.findings if row.suggestion_index == 1)
        review.stage(auto_row.row_id); review.save()
        self.assertNotIn("automatic_condition", review.saved[1])
        self.assertTrue(review.saved[1]["reviewed_by_human"])

    def test_duplicate_code_channels_keep_exact_manual_candidate_evidence(self):
        data = payload()
        candidates = data["suggestions"][0]["candidates"]
        candidates[1].update(code=candidates[0]["code"], source="snogit", source_member="toy.dat")
        source = load_suggestions_preview(encoded(data)); row = source.findings[0]
        review = ReviewSession(source)
        review.stage(row.row_id, row.candidates[1].row_id); review.save()
        self.assertEqual(review.saved[0]["manual_candidate_ordinal"], 1)
        self.assertEqual(review.saved[0]["manual_candidate"]["source"], "snogit")
        exported = review.export_text().encode()
        self.assertEqual(load_review(exported, source).saved, review.saved)
        changed = json.loads(exported); changed["decisions"][0]["manual_candidate_ordinal"] = 0
        with self.assertRaises(ReviewError): load_review(encoded(changed), source)

    def test_document_confirmation_protects_keep_rows_and_removes_automatic_ownership(self):
        source = load_suggestions_preview((FIXTURE / "suggestions.json").read_bytes())
        review = load_review((FIXTURE / "staged-decisions.json").read_bytes(), source)
        row = next(row for row in source.findings if row.suggestion_index == 1)
        review.mark_document(row.row_id, True); review.save()
        self.assertTrue(review.saved[1]["reviewed_by_human"])
        self.assertNotIn("automatic_condition", review.saved[1])
        self.assertNotIn(row.document, json.loads(review.export_text())["metadata"]["automatic_reviewed_documents"])
        row = next(row for row in source.findings if row.suggestion_index == 2)
        review.mark_document(row.row_id, True); review.save()
        self.assertTrue(all(item["reviewed_by_human"] for item in review.saved.values() if item["document"] == row.document))
        review.mark_document(row.row_id, False); review.save()
        self.assertNotIn(row.document, review.reviewed_documents)
        self.assertTrue(review.saved[2]["reviewed_by_human"])  # Unmark is not manual Undo.

    def test_bad_imports_are_private_and_never_modify_current_review(self):
        source = state(); current = ReviewSession(source)
        base = json.loads(current.export_text())
        broken = [b"DO_NOT_ECHO", b"[]", b"\xff", b"[" * 1500]
        for edit in (lambda d: d["decisions"].append(copy.deepcopy(d["decisions"][0])),
                     lambda d: d["decisions"][0].update(suggestion_index=True),
                     lambda d: d["decisions"][0].update(apply="yes"),
                     lambda d: d["metadata"].update(annotators="DO_NOT_ECHO"),
                     lambda d: d["decisions"][0].update(apply=True, valid_choice=True, replacement_code="DO_NOT_ECHO")):
            data = copy.deepcopy(base); edit(data); broken.append(encoded(data))
        for content in broken:
            with self.subTest(content=content[:20]), self.assertRaises(ReviewError) as error:
                load_review(content, source)
            self.assertNotIn("DO_NOT_ECHO", str(error.exception))
        self.assertFalse(current.dirty or current.saved)

    def test_export_does_not_copy_unscoped_suggestions_contexts(self):
        data = payload()
        data["metadata"].update(annotators=["alice"], id_feature="custom_id",
                                finding_contexts=[dict(annotator="bob", context="DO_NOT_EXPORT")])
        source = load_suggestions_preview(encoded(data))
        text = ReviewSession(source).export_text()
        self.assertNotIn("DO_NOT_EXPORT", text)
        self.assertEqual(json.loads(text)["metadata"]["id_feature"], "custom_id")
        decisions = json.loads(text)
        decisions["metadata"]["annotators"] = []
        decisions["metadata"]["finding_contexts"] = [dict(annotator="bob", context="DO_NOT_EXPORT")]
        self.assertNotIn("DO_NOT_EXPORT", load_review(encoded(decisions), source).export_text())

    def test_size_limit_bom_and_no_hdf5_or_network_access(self):
        source = state(); content = ReviewSession(source).export_text().encode()
        with patch("h5py.File", side_effect=AssertionError()), patch("requests.sessions.Session.request", side_effect=AssertionError()):
            load_review(b"\xef\xbb\xbf" + content, source)
        with patch("snomed_post_processing.gui.nicegui.review.MAX_DECISIONS_BYTES", 2):
            with self.assertRaisesRegex(ReviewError, "50 MiB"): load_review(b"123", source)


class ReviewUiTest(unittest.IsolatedAsyncioTestCase):
    async def setup_page(self):
        ui, grids, labels = fake_ui()
        source_handler = ui.upload.call_args.kwargs["on_upload"]
        review_handler = next(call.kwargs["on_upload"] for call in ui.upload.call_args_list if call.kwargs["label"].startswith("Load reviewed"))
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await source_handler(upload_event(encoded(payload())))
        buttons = {call.args[0]: call.kwargs.get("on_click") for call in ui.button.call_args_list if call.args}
        return ui, grids, labels, source_handler, review_handler, buttons

    async def test_click_stage_save_flags_and_download_are_deliberate(self):
        ui, grids, labels, _, _, buttons = await self.setup_page()
        row = grids[0].options["rowData"][0]
        grids[0].on.call_args.args[1](SimpleNamespace(args={"data": row}))
        candidate = grids[1].options["rowData"][0]
        grids[1].on.call_args.args[1](SimpleNamespace(args={"data": candidate}))
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Unreviewed")
        open_context(ui, grids[1], candidate)["Apply"].callback(None)
        self.assertIn("Pending replacement", grids[0].options["rowData"][0]["review"])
        await buttons["Download reviewed decisions JSON"]()
        ui.download.content.assert_not_called()
        ui.document_buttons[-1].callback(None); buttons["Save choices"]()
        await buttons["Download reviewed decisions JSON"]()
        data = json.loads(ui.download.content.call_args.args[0])
        self.assertTrue(data["decisions"][0]["reviewed_by_human"])
        self.assertEqual(data["metadata"]["reviewed_documents"], ["toy.txt"])

    async def test_context_actions_target_clicked_row_and_require_save(self):
        ui, grids, labels, _, _, buttons = await self.setup_page()
        row = grids[0].options["rowData"][0]
        actions = open_context(ui, grids[0], row)
        self.assertEqual(list(actions), ["Accept Suggestion", "Delete", "Manual Review", "Keep Original"])
        self.assertFalse(actions["Accept Suggestion"].enabled)
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Unreviewed")
        actions["Delete"].callback(None)
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Pending deletion")
        buttons["Save choices"]()
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Saved deletion")
        open_context(ui, grids[0], row)["Manual Review"].callback(None)
        buttons["Save choices"]()
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Saved manual review")
        candidate = grids[1].options["rowData"][0]
        current = open_context(ui, grids[1], candidate)
        self.assertEqual(list(current), ["Apply"])
        self.assertTrue(current["Apply"].enabled)
        current["Apply"].callback(None)
        self.assertIn("Pending replacement", grids[0].options["rowData"][0]["review"])
        actions["Delete"].callback(None)  # A previously opened menu must not target newer navigation.
        self.assertIn("Pending replacement", grids[0].options["rowData"][0]["review"])
        self.assertIn("no longer matches", ui.notify.call_args.args[0])

    async def test_findings_accept_saved_proposal_candidates_apply_inspected_target_and_keep_is_in_menu(self):
        ui, grids, labels, source_handler, _, buttons = await self.setup_page()
        data = payload(); data["suggestions"][0]["replacement_code"] = "990000202"
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await source_handler(upload_event(encoded(data)))
        row = grids[0].options["rowData"][0]
        open_context(ui, grids[0], row)
        first = grids[1].options["rowData"][0]
        self.assertEqual(list(open_context(ui, grids[1], first)), ["Apply"])
        actions = open_context(ui, grids[0], row)
        self.assertTrue(actions["Accept Suggestion"].enabled)
        self.assertNotIn("Apply", actions)
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Unreviewed")
        actions["Accept Suggestion"].callback(None)
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Pending replacement: 990000202")
        open_context(ui, grids[1], first)["Apply"].callback(None)
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Pending replacement: 990000201")
        open_context(ui, grids[0], row)["Keep Original"].callback(None)
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Pending Keep")
        self.assertNotIn("Keep original", buttons)
        buttons["Save choices"]()
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Saved Keep")

    async def test_carousel_groups_documents_preserves_review_and_exports_all_original_indices(self):
        ui, grids, labels, source_handler, _, buttons = await self.setup_page()
        data = payload()
        data["suggestions"][0]["replacement_code"] = "990000202"
        other = copy.deepcopy(data["suggestions"][0]); other["finding"]["document"] = "other.txt"
        same = copy.deepcopy(data["suggestions"][0]); same["finding"]["annotator"] = "Bob"
        data["suggestions"].extend([other, same])
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await source_handler(upload_event(encoded(data)))
        self.assertEqual(len(grids), 2)  # One reused workspace, not a grid pair per document.
        self.assertNotIn("document", [column["field"] for column in grids[0].options["columnDefs"]])
        self.assertEqual([row["suggestion_index"] for row in grids[0].options["rowData"]], [0, 2])
        open_context(ui, grids[0], grids[0].options["rowData"][0])["Keep Original"].callback(None)
        switch_document(ui, 1)
        self.assertEqual([row["suggestion_index"] for row in grids[0].options["rowData"]], [1])
        self.assertEqual(grids[1].options["rowData"], [])
        other_row = grids[0].options["rowData"][0]
        open_context(ui, grids[0], other_row)["Accept Suggestion"].callback(None)
        switch_document(ui, 0)
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Pending Keep")
        self.assertEqual(open_context(ui, grids[0], other_row), {})  # Late events from hidden slides are rejected.
        buttons["Save choices"]()
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Saved Keep")
        await buttons["Download reviewed decisions JSON"]()
        decisions = json.loads(ui.download.content.call_args.args[0])["decisions"]
        self.assertEqual([item["suggestion_index"] for item in decisions], [0, 1, 2])
        self.assertEqual(decisions[1]["replacement_code"], "990000202")
        switch_document(ui, 1)
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Saved replacement: 990000202")

    async def test_carousel_ignores_old_source_navigation_and_handles_empty_artifacts(self):
        ui, grids, _, source_handler, _, _ = await self.setup_page()
        carousel = ui.carousel.return_value
        old_token = carousel.value
        data = payload(); data["suggestions"] = []
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await source_handler(upload_event(encoded(data)))
            self.assertEqual(grids[0].options["rowData"], [])
            carousel.set_visibility.assert_called_with(False)
            await source_handler(upload_event(encoded(payload())))
        before = grids[0].options["rowData"]
        carousel.on_value_change.call_args.args[0](SimpleNamespace(value=old_token))
        self.assertIs(grids[0].options["rowData"], before)
        carousel.set_visibility.assert_called_with(True)

    async def test_context_menu_anchors_to_clicked_table_not_surrounding_page(self):
        ui, grids, _, _, _, _ = await self.setup_page()
        menu = ui.context_menu.return_value.props.return_value
        open_context(ui, grids[0], grids[0].options["rowData"][0])
        menu.props.__setitem__.assert_called_with("target", f"#{grids[0].html_id}")
        open_context(ui, grids[1], grids[1].options["rowData"][0])
        menu.props.__setitem__.assert_called_with("target", f"#{grids[1].html_id}")

    async def test_context_menu_does_not_follow_navigation_to_another_finding(self):
        ui, grids, labels, source_handler, _, _ = await self.setup_page()
        content = (FIXTURE / "suggestions.json").read_bytes()
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await source_handler(upload_event(content))
        first, second = grids[0].options["rowData"][:2]
        actions = open_context(ui, grids[0], first)
        grids[0].on.call_args.args[1](SimpleNamespace(args={"data": second}))
        actions["Delete"].callback(None)
        self.assertTrue(all(row["review"] == "Unreviewed" for row in grids[0].options["rowData"]))
        open_context(ui, grids[0], second)["Delete"].callback(None)
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Unreviewed")
        self.assertEqual(grids[0].options["rowData"][1]["review"], "Pending deletion")

    async def test_demo_protected_import_and_old_snapshot_menus_cannot_stage(self):
        ui, grids, labels = fake_ui()
        demo = open_context(ui, grids[0], grids[0].options["rowData"][0])
        self.assertTrue(all(not item.enabled for item in demo.values()))
        demo["Delete"].callback(None)
        self.assertNotIn("Pending", grids[0].options["rowData"][0]["review"])
        ui, grids, labels, source_handler, import_handler, _ = await self.setup_page()
        row = grids[0].options["rowData"][0]
        actions = open_context(ui, grids[0], row)
        data = json.loads(ReviewSession(state()).export_text())
        data["decisions"][0].update(action="delete", delete_annotation=True)
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await import_handler(upload_event(encoded(data)))
        actions["Delete"].callback(None)
        protected = open_context(ui, grids[0], row)
        self.assertTrue(all(not item.enabled for item in protected.values()))
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await source_handler(upload_event(encoded(payload())))
        count = len(ui.context_items)
        open_context(ui, grids[0], row)
        self.assertEqual(len(ui.context_items), count)
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Unreviewed")

    async def test_import_restores_saved_document_color_and_failed_import_retains_it(self):
        ui, grids, labels, _, handler, _ = await self.setup_page()
        review = ReviewSession(state())
        review.mark_document(review.source.findings[0].row_id, True); review.save()
        content = review.export_text().encode()
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await handler(upload_event(content))
            self.assertTrue(grids[0].options["rowData"][0]["document_reviewed"])
            await handler(upload_event(b"invalid"))
            self.assertTrue(grids[0].options["rowData"][0]["document_reviewed"])

    async def test_document_color_uses_saved_flags_not_pending_changes(self):
        ui, grids, labels, source_handler, _, buttons = await self.setup_page()
        definitions = grids[0].options["columnDefs"]
        self.assertEqual(definitions[-1]["field"], "ignored")
        self.assertNotIn("document_reviewed", [column["field"] for column in definitions])
        self.assertNotIn("document", [column["field"] for column in definitions])
        heading = next(label for label in reversed(labels) if label.text == "toy.txt")
        grids[0].on.call_args.args[1](SimpleNamespace(args={"data": grids[0].options["rowData"][0]}))
        toggle = ui.document_buttons[-1]
        self.assertEqual(toggle.props_data["icon"], "check_circle_outline")
        toggle.callback(None)
        self.assertEqual(toggle.props_data["color"], "amber-8")
        self.assertEqual(toggle.props_data["icon"], "check_circle")
        self.assertFalse(grids[0].options["rowData"][0]["document_reviewed"])
        buttons["Save choices"]()
        self.assertEqual(toggle.props_data["color"], "green-7")
        self.assertTrue(grids[0].options["rowData"][0]["document_reviewed"])
        self.assertIn("text-green-700", heading.classes.call_args.kwargs["add"])
        toggle.callback(None)
        self.assertEqual(toggle.props_data["color"], "amber-8")
        self.assertEqual(toggle.props_data["icon"], "check_circle_outline")
        self.assertTrue(grids[0].options["rowData"][0]["document_reviewed"])
        buttons["Discard pending changes"]()
        self.assertEqual(toggle.props_data["color"], "green-7")
        self.assertTrue(grids[0].options["rowData"][0]["document_reviewed"])
        toggle.callback(None); buttons["Save choices"]()
        self.assertEqual(toggle.props_data["color"], "grey-6")
        self.assertFalse(grids[0].options["rowData"][0]["document_reviewed"])
        self.assertIn("text-green-700", heading.classes.call_args.kwargs["remove"])
        toggle.callback(None); buttons["Save choices"]()
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await source_handler(upload_event(encoded(payload()), "new.json"))
        self.assertFalse(grids[0].options["rowData"][0]["document_reviewed"])

    async def test_header_toggle_works_without_selecting_finding_and_rejects_old_source(self):
        ui, grids, labels, source_handler, _, buttons = await self.setup_page()
        toggle = ui.document_buttons[-1]
        self.assertTrue(toggle.enabled)
        self.assertNotIn("Mark document reviewed", buttons)
        self.assertNotIn("Unmark document reviewed", buttons)
        toggle.callback(None)
        self.assertEqual(toggle.props_data["color"], "amber-8")
        self.assertTrue(any("pending; Save choices" in label.text for label in labels))
        self.assertFalse(grids[0].options["rowData"][0]["document_reviewed"])
        buttons["Save choices"]()
        self.assertTrue(grids[0].options["rowData"][0]["document_reviewed"])
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await source_handler(upload_event(encoded(payload())))
        toggle.callback(None)
        self.assertIn("older upload", ui.notify.call_args.args[0])
        self.assertFalse(grids[0].options["rowData"][0]["document_reviewed"])
        ui, grids, _ = fake_ui()
        self.assertTrue(all(not button.enabled for button in ui.document_buttons))
        ui.document_buttons[0].callback(None)
        self.assertFalse(grids[0].options["rowData"][0]["document_reviewed"])

    async def test_bad_import_and_new_source_reset(self):
        ui, grids, labels, source_handler, review_handler, buttons = await self.setup_page()
        grids[0].on.call_args.args[1](SimpleNamespace(args={"data": grids[0].options["rowData"][0]}))
        open_context(ui, grids[0], grids[0].options["rowData"][0])["Keep Original"].callback(None)
        buttons["Save choices"]()
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await review_handler(upload_event(b"DO_NOT_ECHO"))
            self.assertEqual(grids[0].options["rowData"][0]["review"], "Saved Keep")
            await source_handler(upload_event(encoded(payload()), "new.json"))
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Unreviewed")
        self.assertFalse(any("DO_NOT_ECHO" in label.text for label in labels))

    async def test_slow_download_is_rejected_after_a_new_manual_choice(self):
        ui, grids, labels, _, _, buttons = await self.setup_page()
        started, finish = asyncio.Event(), asyncio.Event()
        async def delayed(function):
            started.set(); await finish.wait(); return function()
        with patch("nicegui.run.io_bound", side_effect=delayed):
            pending = asyncio.create_task(buttons["Download reviewed decisions JSON"]())
            await asyncio.wait_for(started.wait(), 2)
            grids[0].on.call_args.args[1](SimpleNamespace(args={"data": grids[0].options["rowData"][0]}))
            open_context(ui, grids[0], grids[0].options["rowData"][0])["Keep Original"].callback(None)
            buttons["Save choices"]()
            finish.set(); await pending
        ui.download.content.assert_not_called()
        self.assertTrue(any("Review changed while preparing" in call.args[0] for call in ui.notify.call_args_list))

    async def test_read_error_and_size_rejection_preserve_review_without_echo(self):
        ui, grids, labels, _, handler, buttons = await self.setup_page()
        rows = grids[0].options["rowData"]
        event = upload_event(b"small"); event.file.size = lambda: 50 * 1024 * 1024 + 1
        await handler(event); event.file.read.assert_not_awaited()
        event = upload_event(b"small"); event.file.read.side_effect = OSError("DO_NOT_ECHO")
        await handler(event)
        self.assertIs(rows, grids[0].options["rowData"])
        self.assertFalse(any("DO_NOT_ECHO" in label.text for label in labels))

    async def test_newer_import_wins_and_pages_are_isolated(self):
        first = await self.setup_page(); second = await self.setup_page()
        ui, grids, labels, _, handler, buttons = first
        empty = ReviewSession(state()).export_text().encode()
        review = ReviewSession(state()); review.stage(review.source.findings[0].row_id); review.save()
        keep = review.export_text().encode()
        started, finish = asyncio.Event(), asyncio.Event()
        async def delayed(function, content, source):
            if content == empty:
                started.set(); await finish.wait()
            return function(content, source)
        with patch("nicegui.run.io_bound", side_effect=delayed):
            slow = asyncio.create_task(handler(upload_event(empty)))
            await asyncio.wait_for(started.wait(), 2)
            await handler(upload_event(keep)); finish.set(); await slow
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Saved Keep")
        self.assertEqual(second[1][0].options["rowData"][0]["review"], "Unreviewed")

    async def test_new_source_and_demo_reset_supersede_pending_decision_import(self):
        for reset_demo in (False, True):
            ui, grids, labels, source_handler, handler, buttons = await self.setup_page()
            content = ReviewSession(state()).export_text().encode()
            started, finish = asyncio.Event(), asyncio.Event()
            async def delayed(function, data, name_or_state):
                if function is load_review:
                    started.set(); await finish.wait()
                return function(data, name_or_state)
            with patch("nicegui.run.io_bound", side_effect=delayed):
                pending = asyncio.create_task(handler(upload_event(content)))
                await asyncio.wait_for(started.wait(), 2)
                if reset_demo:
                    buttons["Use synthetic demo"]()
                else:
                    await source_handler(upload_event(encoded(payload()), "new.json"))
                finish.set(); await pending
            self.assertFalse(any("restored; prior" in label.text for label in labels))
            self.assertTrue(any(label.text == ("Source: Synthetic demo" if reset_demo else "Source: new.json") for label in labels))

    async def test_pending_import_never_overwrites_new_manual_change(self):
        ui, grids, labels, _, review_handler, buttons = await self.setup_page()
        content = ReviewSession(state()).export_text().encode()
        started, finish = asyncio.Event(), asyncio.Event()
        async def delayed(function, *args):
            started.set(); await finish.wait(); return function(*args)
        with patch("nicegui.run.io_bound", side_effect=delayed):
            task = asyncio.create_task(review_handler(upload_event(content)))
            await asyncio.wait_for(started.wait(), 2)
            grids[0].on.call_args.args[1](SimpleNamespace(args={"data": grids[0].options["rowData"][0]}))
            open_context(ui, grids[0], grids[0].options["rowData"][0])["Keep Original"].callback(None)
            finish.set(); await task
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Pending Keep")
        self.assertTrue(any("Review changed while importing" in label.text for label in labels))


if __name__ == "__main__":
    unittest.main()
