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
from test.test_nicegui_suggestions import payload, encoded, fake_ui, upload_event

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
        buttons = {call.args[0]: call.kwargs.get("on_click") for call in ui.button.call_args_list}
        return ui, grids, labels, source_handler, review_handler, buttons

    async def test_click_stage_save_flags_and_download_are_deliberate(self):
        ui, grids, labels, _, _, buttons = await self.setup_page()
        row = grids[0].options["rowData"][0]
        grids[0].on.call_args.args[1](SimpleNamespace(args={"data": row}))
        candidate = grids[1].options["rowData"][0]
        grids[1].on.call_args.args[1](SimpleNamespace(args={"data": candidate}))
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Unreviewed")
        buttons["Use candidate"]()
        self.assertIn("Pending replacement", grids[0].options["rowData"][0]["review"])
        await buttons["Download reviewed decisions JSON"]()
        ui.download.content.assert_not_called()
        buttons["Mark document reviewed"](); buttons["Save choices"]()
        await buttons["Download reviewed decisions JSON"]()
        data = json.loads(ui.download.content.call_args.args[0])
        self.assertTrue(data["decisions"][0]["reviewed_by_human"])
        self.assertEqual(data["metadata"]["reviewed_documents"], ["toy.txt"])

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
        document = next(column for column in definitions if column["field"] == "document")
        self.assertIn("document_reviewed === true", document[":cellStyle"])
        self.assertIn("'inherit'", document[":cellStyle"])  # Reset styling when review is unmarked.
        grids[0].on.call_args.args[1](SimpleNamespace(args={"data": grids[0].options["rowData"][0]}))
        buttons["Mark document reviewed"]()
        self.assertFalse(grids[0].options["rowData"][0]["document_reviewed"])
        buttons["Save choices"]()
        self.assertTrue(grids[0].options["rowData"][0]["document_reviewed"])
        buttons["Unmark document reviewed"]()
        self.assertTrue(grids[0].options["rowData"][0]["document_reviewed"])
        buttons["Discard pending changes"]()
        self.assertTrue(grids[0].options["rowData"][0]["document_reviewed"])
        buttons["Unmark document reviewed"](); buttons["Save choices"]()
        self.assertFalse(grids[0].options["rowData"][0]["document_reviewed"])
        buttons["Mark document reviewed"](); buttons["Save choices"]()
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await source_handler(upload_event(encoded(payload()), "new.json"))
        self.assertFalse(grids[0].options["rowData"][0]["document_reviewed"])

    async def test_bad_import_and_new_source_reset(self):
        ui, grids, labels, source_handler, review_handler, buttons = await self.setup_page()
        grids[0].on.call_args.args[1](SimpleNamespace(args={"data": grids[0].options["rowData"][0]}))
        buttons["Keep original"](); buttons["Save choices"]()
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
            buttons["Keep original"](); buttons["Save choices"]()
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
            buttons["Keep original"]()
            finish.set(); await task
        self.assertEqual(grids[0].options["rowData"][0]["review"], "Pending Keep")
        self.assertTrue(any("Review changed while importing" in label.text for label in labels))


if __name__ == "__main__":
    unittest.main()
