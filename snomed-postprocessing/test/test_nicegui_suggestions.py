"""Read-only suggestions import and page callbacks, using artificial data only."""
import asyncio
import copy
import io
import json
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import nullcontext

from snomed_post_processing.gui.nicegui.page import build_page, _finding_rows, _candidate_rows
from snomed_post_processing.gui.nicegui.suggestions import (
    MAX_SUGGESTIONS_BYTES, SuggestionsPreviewError, load_suggestions_preview,
)
from snomed_post_processing.sanitization.json_io import read_sanitization_suggestions_json_with_metadata


def payload():
    def candidate(code, score, source="snomed_fsn"):
        return dict(type="semantic_bm25", code=code, fsn="Toy FSN (qualifier)", score=score,
                    lexical_score=0.123456789012345, semantic_tag="qualifier", active=True,
                    in_whitelist=True, in_blacklist=False, source=source,
                    matched_term="Original (matched) term", source_member="toy.dat" if source == "snogit" else None)
    return dict(schema="snomed-post-processing.sanitization-suggestions", schema_version=1,
                metadata=dict(annotators=[], target_view="policy", cache_path="/never-open-this.hdf5"),
                suggestions=[dict(
                    type="semantic_bm25", status="ambiguous_replacement", replacement_code="1234567890123456789012345",
                    finding=dict(annotator="Alice", document="toy.txt", code="1234567890123456789012345",
                                 covered_text=" 0042 ± <script>toy</script> ", offset=[2, 17], layer="toy.Concept",
                                 fsn="Original source FSN (qualifier)", list_type="whitelist", reason="not_in_whitelist", ignored=True),
                    reason="Original saved rationale", score=9.0000000001, candidate_count=7,
                    retrieval_limits=["candidate-cap: evidence incomplete"],
                    candidates=[candidate("990000201", 9.0000000001), candidate("990000202", 9.0), candidate("990000203", 4.0)],
                    context_candidates=[candidate("990000201", 12.0, "snogit")],
                )])


def encoded(data):
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def fake_ui(state=None):
    ui = MagicMock()
    grids, labels = [], []

    def grid(options):
        element = MagicMock()
        element.options = options
        element.html_id = f"c_test_grid_{len(grids)}"
        element.classes.return_value = element
        grids.append(element)
        return element

    def label(text=""):
        element = MagicMock()
        element.text = text
        element.classes.return_value = element
        element.set_text.side_effect = lambda value: setattr(element, "text", value)
        labels.append(element)
        return element

    ui.context_items = []

    def menu_item(text, on_click):
        element = MagicMock()
        element.text, element.callback, element.enabled = text, on_click, True
        element.set_enabled.side_effect = lambda value: setattr(element, "enabled", value)
        ui.context_items.append(element)
        return element

    ui.document_buttons = []

    def button(*args, **kwargs):
        element = MagicMock()
        element.props.return_value = element.classes.return_value = element.tooltip.return_value = element
        element.props_data = {}
        element.props.__setitem__.side_effect = element.props_data.__setitem__
        element.set_enabled.side_effect = lambda value: setattr(element, "enabled", value)
        if "icon" in kwargs:
            element.callback = kwargs["on_click"]
            ui.document_buttons.append(element)
        return element

    ui.button.side_effect = button
    ui.tooltip.side_effect = label
    carousel = MagicMock()
    carousel.props.return_value = carousel.classes.return_value = carousel
    carousel.set_value.side_effect = lambda value: setattr(carousel, "value", value)
    ui.carousel.return_value = carousel
    ui.menu_item.side_effect = menu_item
    ui.aggrid.side_effect = grid
    ui.label.side_effect = label
    with patch("snomed_post_processing.gui.nicegui.page.PolicyCheckControls"), \
            patch("snomed_post_processing.gui.nicegui.page.PreviewState", return_value=state) if state is not None else nullcontext():
        build_page(ui, MagicMock())
    return ui, grids, labels


def switch_document(ui, index):
    carousel = ui.carousel.return_value
    token = f"{carousel.value.rsplit(':', 1)[0]}:{index}"
    carousel.set_value(token)
    carousel.on_value_change.call_args.args[0](SimpleNamespace(value=token))


def open_context(ui, grid, row):
    handler = next(call.args[1] for call in grid.on.call_args_list if call.args[0] == "contextmenu")
    previous = len(ui.context_items)
    handler(SimpleNamespace(sender=grid, args={"data": row, "clientX": 50, "clientY": 100}))
    return {item.text: item for item in ui.context_items[previous:]}


def upload_event(content, name="suggestions.json"):
    return SimpleNamespace(file=SimpleNamespace(name=name, size=lambda: len(content), read=AsyncMock(return_value=content)))


class SuggestionsPreviewTest(unittest.TestCase):
    def test_reuses_existing_reader_and_retains_all_backend_data(self):
        content = encoded(payload())
        expected, metadata = read_sanitization_suggestions_json_with_metadata(io.StringIO(content.decode()))
        state = load_suggestions_preview(content, "uploaded.json")
        self.assertEqual(state.source_suggestions, tuple(expected))
        self.assertEqual(state.metadata, metadata)
        self.assertEqual(state.source_name, "uploaded.json")
        row = state.findings[0]
        self.assertEqual(row.text, expected[0].finding.covered_text)
        self.assertEqual(row.offset, (2, 17))
        self.assertEqual(row.source_fsn, expected[0].finding.fsn)
        self.assertEqual(row.reason, expected[0].reason)
        self.assertTrue(row.ignored)
        self.assertEqual(row.candidate_count, 7)
        self.assertEqual(row.retrieval_limits, expected[0].retrieval_limits)
        self.assertEqual(row.proposed_code, expected[0].replacement_code)
        self.assertIsNone(state.selected_finding_id)
        self.assertIsNone(state.selected_candidate_id)

    def test_uses_backend_reader_directly(self):
        with patch("snomed_post_processing.sanitization.json_io.read_sanitization_suggestions_json_with_metadata",
                   wraps=read_sanitization_suggestions_json_with_metadata) as reader:
            load_suggestions_preview(encoded(payload()))
        reader.assert_called_once()

    def test_scope_keeps_original_indices_and_case_insensitive_matching(self):
        data = payload()
        data["suggestions"] *= 3
        data = copy.deepcopy(data)
        data["suggestions"][0] = copy.deepcopy(data["suggestions"][0])
        data["suggestions"][0]["finding"]["annotator"] = "bob"
        data["metadata"]["annotators"] = [" ALICE ", "alice"]
        state = load_suggestions_preview(encoded(data))
        self.assertEqual(len(state.source_suggestions), 3)
        self.assertEqual([row.suggestion_index for row in state.findings], [1, 2])
        self.assertEqual(state.source_annotators, ("alice",))
        self.assertEqual(state.metadata["annotators"], [" ALICE ", "alice"])
        excluded_id = state.findings[0].row_id.rsplit(":", 1)[0] + ":0"
        with self.assertRaises(ValueError):
            state.select_finding(excluded_id)

    def test_invalid_saved_scope_is_not_broadened_silently(self):
        for scope in ("alice", 4, [4], {"alice": True}):
            data = payload()
            data["metadata"]["annotators"] = scope
            with self.subTest(scope=scope), self.assertRaises(SuggestionsPreviewError):
                load_suggestions_preview(encoded(data))

    def test_ties_scores_and_string_codes_are_preserved(self):
        state = load_suggestions_preview(encoded(payload()))
        candidates = state.findings[0].candidates
        self.assertEqual([item.rank for item in candidates], [1, 1, 3, None])
        self.assertEqual([item.score for item in candidates], [9.0000000001, 9.0, 4.0, 12.0])
        self.assertIsInstance(_finding_rows(state)[0]["code"], str)
        self.assertEqual(_finding_rows(state)[0]["code"], "1234567890123456789012345")
        self.assertEqual(dict(candidates[0].details)["Lexical score"], 0.123456789012345)

    def test_same_code_in_distinct_channels_and_roles_has_distinct_identity(self):
        data = payload()
        data["suggestions"][0]["candidates"].append(copy.deepcopy(data["suggestions"][0]["context_candidates"][0]))
        state = load_suggestions_preview(encoded(data))
        finding = state.findings[0]
        self.assertEqual(len({item.row_id for item in finding.candidates}), 5)
        state.select_finding(finding.row_id)
        selected = state.preview_candidate(finding.candidates[-1].row_id)
        self.assertEqual(selected.code, "990000201")
        self.assertFalse(selected.selectable)
        self.assertEqual(dict(selected.details)["Source"], "snogit")
        self.assertEqual(dict(selected.details)["Source member"], "toy.dat")

    def test_duplicate_findings_are_not_merged(self):
        data = payload()
        data["suggestions"].append(copy.deepcopy(data["suggestions"][0]))
        state = load_suggestions_preview(encoded(data))
        self.assertEqual([row.suggestion_index for row in state.findings], [0, 1])
        self.assertNotEqual(state.findings[0].row_id, state.findings[1].row_id)

    def test_new_artifact_invalidates_old_row_and_candidate_ids(self):
        content = encoded(payload())
        before, after = load_suggestions_preview(content), load_suggestions_preview(content)
        with self.assertRaises(ValueError):
            after.select_finding(before.findings[0].row_id)
        after.select_finding(after.findings[0].row_id)
        with self.assertRaises(ValueError):
            after.preview_candidate(before.findings[0].candidates[0].row_id)

    def test_empty_json_artifact_and_utf8_bom_are_supported(self):
        data = payload()
        data["suggestions"] = []
        state = load_suggestions_preview(b"\xef\xbb\xbf" + encoded(data))
        self.assertEqual(state.findings, ())
        self.assertEqual(state.source_suggestions, ())

    def test_malformed_inputs_do_not_expose_uploaded_content_in_errors(self):
        broken = []
        for key, value in (("schema", "DO_NOT_ECHO"), ("schema_version", 999), ("suggestions", {})):
            data = payload()
            data[key] = value
            broken.append(encoded(data))
        data = payload()
        data["suggestions"][0]["status"] = "DO_NOT_ECHO"
        broken.append(encoded(data))
        data = payload()
        data["suggestions"][0]["finding"]["offset"] = ["DO_NOT_ECHO"]
        broken.append(encoded(data))
        for content in [b"DO_NOT_ECHO", b"[]", b"\xff", b"[" * 1500 + b"0" + b"]" * 1500, *broken]:
            with self.subTest(content=content[:20]), self.assertRaises(SuggestionsPreviewError) as error:
                load_suggestions_preview(content)
            self.assertNotIn("DO_NOT_ECHO", str(error.exception))

    def test_server_size_limit_is_enforced_without_large_allocation(self):
        with patch("snomed_post_processing.gui.nicegui.suggestions.MAX_SUGGESTIONS_BYTES", 2):
            with self.assertRaisesRegex(SuggestionsPreviewError, "50 MiB"):
                load_suggestions_preview(b"123")

    def test_loading_opens_no_hdf5_or_network_source(self):
        with patch("h5py.File", side_effect=AssertionError("must not open policy")), patch(
            "requests.sessions.Session.request", side_effect=AssertionError("must not contact API")
        ):
            load_suggestions_preview(encoded(payload()))

    def test_synthetic_fixture_structured_suggestions_are_retained(self):
        content = (pathlib.Path(__file__).parent / "projects/synthetic-annotator-scope/suggestions.json").read_bytes()
        expected, metadata = read_sanitization_suggestions_json_with_metadata(io.StringIO(content.decode()))
        state = load_suggestions_preview(content)
        self.assertEqual(state.source_suggestions, tuple(expected))
        self.assertEqual(state.metadata, metadata)
        self.assertEqual([row.suggestion_index for row in state.findings], list(range(len(expected))))
        self.assertTrue(any(row.policy_issue == "exclusion list" for row in state.findings))


class SuggestionsUploadPageTest(unittest.IsolatedAsyncioTestCase):
    async def test_saved_context_reuses_annotation_line_without_staging_or_changing_covered_text(self):
        ui, grids, labels = fake_ui()
        data = payload()
        finding = data["suggestions"][0]["finding"]
        snippet = "… before [ 0042 ± <script>toy</script> ] after …"
        data["metadata"]["finding_contexts"] = [dict(
            document=finding["document"], annotator=finding["annotator"], code=finding["code"],
            offset=finding["offset"], context=snippet,
        )]
        handler = ui.upload.call_args.kwargs["on_upload"]
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await handler(upload_event(encoded(data)))
        row = grids[0].options["rowData"][0]
        grids[0].on.call_args.args[1](SimpleNamespace(args={"data": row}))
        annotation = labels[next(index for index, label in enumerate(labels) if label.text == "Annotation") + 1]
        self.assertEqual(annotation.text, snippet)
        self.assertEqual(row["text"], finding["covered_text"])
        self.assertEqual(row["review"], "Unreviewed")
        ui.html.assert_not_called()
        ui.markdown.assert_not_called()
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await handler(upload_event(b"not JSON"))
        self.assertEqual(annotation.text, snippet)  # Failed loads retain the current context.
        data["metadata"]["finding_contexts"] = 42
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await handler(upload_event(encoded(data)))
        self.assertEqual(annotation.text, "")
        grids[0].on.call_args.args[1](SimpleNamespace(args={"data": grids[0].options["rowData"][0]}))
        self.assertEqual(annotation.text, finding["covered_text"])

    async def test_context_uses_original_scoped_index_and_clears_on_document_navigation(self):
        import copy
        ui, grids, labels = fake_ui()
        data = payload()
        alice = data["suggestions"][0]
        bob = copy.deepcopy(alice); bob["finding"]["annotator"] = "Bob"
        other = copy.deepcopy(alice); other["finding"]["document"] = "other.txt"
        data["suggestions"] = [bob, alice, other]
        data["metadata"]["annotators"] = ["alice"]
        data["metadata"]["finding_contexts"] = [
            dict(document=item["finding"]["document"], annotator=item["finding"]["annotator"],
                 code=item["finding"]["code"], offset=item["finding"]["offset"], context=text)
            for item, text in ((bob, "Excluded Bob context"), (alice, "Alice surrounding context"))
        ]
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await ui.upload.call_args.kwargs["on_upload"](upload_event(encoded(data)))
        row = grids[0].options["rowData"][0]
        self.assertEqual(row["suggestion_index"], 1)
        grids[0].on.call_args.args[1](SimpleNamespace(args={"data": row}))
        annotation = labels[next(index for index, label in enumerate(labels) if label.text == "Annotation") + 1]
        self.assertEqual(annotation.text, "Alice surrounding context")
        self.assertFalse(any(label.text == "Excluded Bob context" for label in labels))
        switch_document(ui, 1)
        self.assertEqual(annotation.text, "")
        grids[0].on.call_args.args[1](SimpleNamespace(args={"data": grids[0].options["rowData"][0]}))
        self.assertEqual(annotation.text, other["finding"]["covered_text"])

    async def test_detail_cleanup_hides_internal_counts_and_places_proposal_with_rationale(self):
        ui, grids, labels = fake_ui()
        self.assertNotIn("suggestion_index", [column["field"] for column in grids[0].options["columnDefs"]])
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await ui.upload.call_args.kwargs["on_upload"](upload_event(encoded(payload())))
        row = grids[0].options["rowData"][0]
        self.assertEqual(row["suggestion_index"], 0)  # Identity/export index is retained internally.
        grids[0].on.call_args.args[1](SimpleNamespace(args={"data": row}))
        self.assertFalse(any("Original index" in label.text or "Saved candidate count" in label.text for label in labels))
        heading = next(index for index, label in enumerate(labels) if label.text == "Suggestion rationale & retrieval")
        proposal = labels[heading + 1]
        self.assertEqual(proposal.text, "Saved proposed SCTID: 1234567890123456789012345 (not automatically accepted)")
        self.assertEqual(labels[heading + 2].text, "Original saved rationale")
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await ui.upload.call_args.kwargs["on_upload"](upload_event(encoded(payload())))
        self.assertEqual(proposal.text, "")

    async def test_upload_replaces_data_and_stale_clicks_are_rejected(self):
        ui, grids, labels = fake_ui()
        findings, candidates = grids
        handler = ui.upload.call_args.kwargs["on_upload"]
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await handler(upload_event(encoded(payload()), "previous.json"))
            old_row = findings.options["rowData"][0]
            await handler(upload_event(encoded(payload()), "real-suggestions.json"))
        self.assertTrue(any(label.text == "Source: real-suggestions.json" for label in labels))
        row = findings.options["rowData"][0]
        self.assertNotEqual(row["row_id"], old_row["row_id"])
        select = findings.on.call_args[0][1]
        select(SimpleNamespace(args={"data": old_row}))
        ui.notify.assert_called_once()
        self.assertEqual(candidates.options["rowData"], [])
        select(SimpleNamespace(args={"data": row}))
        selected = candidates.options["rowData"][-1]
        self.assertIn("Context only", selected["role"])
        candidates.on.call_args[0][1](SimpleNamespace(args={"data": selected}))
        self.assertTrue(any("Diagnostic context only" in label.text for label in labels))
        self.assertTrue(any("Source member: toy.dat" in label.text for label in labels))
        self.assertTrue(any("candidate-cap: evidence incomplete" in label.text for label in labels))
        self.assertTrue(any(" 0042 ± <script>toy</script> " == label.text for label in labels))
        ui.html.assert_not_called()
        ui.markdown.assert_not_called()
        self.assertNotIn("Use candidate", [call.args[0] for call in ui.button.call_args_list if call.args])
        actions = open_context(ui, candidates, selected)
        self.assertFalse(actions["Apply"].enabled)  # Diagnostic context remains non-selectable.
        self.assertEqual(findings.options["rowData"][0]["review"], "Unreviewed")

    async def test_bad_upload_keeps_previous_preview_and_metadata(self):
        ui, grids, labels = fake_ui()
        handler = ui.upload.call_args.kwargs["on_upload"]
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await handler(upload_event(encoded(payload()), "valid.json"))
            old_rows = grids[0].options["rowData"]
            await handler(upload_event(b"DO_NOT_ECHO", "bad.json"))
        self.assertIs(grids[0].options["rowData"], old_rows)
        self.assertTrue(any(label.text == "Source: valid.json" for label in labels))
        self.assertTrue(any("Current preview unchanged" in label.text for label in labels))
        self.assertFalse(any("DO_NOT_ECHO" in label.text for label in labels))

    async def test_oversized_upload_is_rejected_before_reading(self):
        ui, grids, labels = fake_ui()
        old_rows = grids[0].options["rowData"]
        event = upload_event(b"small")
        event.file.size = lambda: MAX_SUGGESTIONS_BYTES + 1
        await ui.upload.call_args.kwargs["on_upload"](event)
        event.file.read.assert_not_awaited()
        self.assertIs(grids[0].options["rowData"], old_rows)
        self.assertTrue(any("50 MiB" in label.text for label in labels))

    async def test_read_failure_is_private_and_preserves_preview(self):
        ui, grids, labels = fake_ui()
        rows = grids[0].options["rowData"]
        event = upload_event(b"ignored")
        event.file.read.side_effect = OSError("DO_NOT_ECHO_PRIVATE_PATH")
        await ui.upload.call_args.kwargs["on_upload"](event)
        self.assertIs(grids[0].options["rowData"], rows)
        self.assertTrue(any("Could not read" in label.text for label in labels))
        self.assertFalse(any("DO_NOT_ECHO" in label.text for label in labels))

    async def test_unrecognized_metadata_mode_does_not_break_publication(self):
        ui, grids, labels = fake_ui()
        data = payload()
        data["metadata"]["target_view"] = ["unknown"]
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await ui.upload.call_args.kwargs["on_upload"](upload_event(encoded(data), "valid.json"))
        self.assertTrue(any(label.text == "Source: valid.json" for label in labels))
        self.assertTrue(any("Saved replacement mode: not recorded" in label.text for label in labels))

    async def test_page_imports_do_not_share_state(self):
        first, first_grids, _ = fake_ui()
        _, second_grids, second_labels = fake_ui()
        second_rows = second_grids[0].options["rowData"]
        with patch("nicegui.run.io_bound", new=AsyncMock(side_effect=lambda function, *args: function(*args))):
            await first.upload.call_args.kwargs["on_upload"](upload_event(encoded(payload()), "first.json"))
        self.assertIs(second_grids[0].options["rowData"], second_rows)
        self.assertTrue(any(label.text == "Source: No suggestions loaded" for label in second_labels))

    async def test_newer_upload_wins_if_previous_reader_finishes_late(self):
        ui, grids, labels = fake_ui()
        handler = ui.upload.call_args.kwargs["on_upload"]
        started, finish = asyncio.Event(), asyncio.Event()

        async def reader(function, content, name):
            if name == "slow.json":
                started.set()
                await finish.wait()
            return load_suggestions_preview(content, name)

        with patch("nicegui.run.io_bound", side_effect=reader):
            previous = asyncio.create_task(handler(upload_event(encoded(payload()), "slow.json")))
            await asyncio.wait_for(started.wait(), timeout=2)
            await handler(upload_event(encoded(payload()), "newer.json"))
            finish.set()
            await previous
        self.assertTrue(any(label.text == "Source: newer.json" for label in labels))

    async def test_page_starts_empty_until_suggestions_are_uploaded(self):
        ui, grids, labels = fake_ui()
        self.assertEqual(grids[0].options["rowData"], [])
        self.assertEqual(grids[1].options["rowData"], [])
        self.assertEqual(ui.document_buttons, [])
        self.assertTrue(any(label.text == "Source: No suggestions loaded" for label in labels))


if __name__ == "__main__":
    unittest.main()
