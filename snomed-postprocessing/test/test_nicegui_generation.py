"""Artificial-data checks for generation, rule staging and async publication guards."""
import asyncio
import copy
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from importlib.util import find_spec
import io
import json
import multiprocessing
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from snomed_post_processing.findings_io import read_critical_findings_json_with_metadata
from snomed_post_processing.gui.nicegui.file_sources import SourceFile
from snomed_post_processing.gui.nicegui.review import ReviewError, ReviewSession, load_review
from snomed_post_processing.gui.nicegui.suggestion_jobs import SuggestionJob, create_cache, inspect_members, run_generation, run_rules
from snomed_post_processing.gui.nicegui.suggestion_ui import SuggestionControls, rule_records
from snomed_post_processing.gui.nicegui.suggestions import load_suggestions_preview
from snomed_post_processing.pipelines.policy_check import PolicySettings, check_policy
from snomed_post_processing.pipelines.suggestion_generation import DEFAULT_ASSOCIATIONS, SuggestionSettings, generate_suggestions
from snomed_post_processing.sanitization.concept_rules import DEFAULT_CONCEPT_RULES, rules_json_text
from test.test_nicegui_policy import FIXTURE, inline


class GenerationBackendTest(unittest.TestCase):
    def setUp(self):
        self.findings, self.metadata = read_critical_findings_json_with_metadata(FIXTURE / "critical-findings.json")
        self.settings = SuggestionSettings(semantic_bm25_fallback=False, historical_ancestor_fallback=False,
                                           allowed_association_types=("REPLACED_BY",))

    def generate(self, **kwargs):
        options = dict(hdf5=FIXTURE / "policy.hdf5", findings=self.findings, metadata=self.metadata,
                       policy=PolicySettings(), settings=self.settings, binding="synthetic-binding", project=FIXTURE / "project.zip")
        options.update(kwargs)
        return generate_suggestions(**options)

    def test_synthetic_results_context_and_artifact_roundtrip(self):
        before = {path: (path.stat().st_size, path.stat().st_mtime_ns) for path in FIXTURE.iterdir() if path.is_file()}
        result = self.generate()
        state = load_suggestions_preview(result.json.encode())
        self.assertEqual(len(result.suggestions), 10)
        self.assertEqual(len(state.findings), 10)
        self.assertEqual(sum(item.replacement_code == "990000201" for item in result.suggestions), 2)
        self.assertTrue(state.metadata["finding_contexts"])
        self.assertEqual(state.metadata["id_feature"], "id")
        self.assertEqual(state.metadata["nicegui_generation_binding"], "synthetic-binding")
        self.assertFalse(any(item.get("apply") for item in json.loads(ReviewSession(state).export_text())["decisions"]))
        self.assertEqual(before, {path: (path.stat().st_size, path.stat().st_mtime_ns) for path in FIXTURE.iterdir() if path.is_file()})

    def test_scope_is_normalized_and_narrower_findings_rejected(self):
        result = self.generate(policy=PolicySettings(annotators=(" ALICE ",)))
        state = load_suggestions_preview(result.json.encode())
        self.assertEqual(len(state.findings), 5)
        self.assertEqual(state.source_annotators, ("alice",))
        self.assertEqual({item["annotator"].lower() for item in state.metadata["finding_contexts"]}, {"alice"})
        with self.assertRaisesRegex(ValueError, "narrower"):
            self.generate(metadata={"annotators": ["alice"]})
        with self.assertRaisesRegex(ValueError, "ID settings"):
            self.generate(metadata={"id_feature": "different"})

    def test_defaults_and_bm25_options_are_forwarded_without_cli_changes(self):
        self.assertNotIn("MOVED_FROM", DEFAULT_ASSOCIATIONS)
        self.assertNotIn("REFERS_TO", DEFAULT_ASSOCIATIONS)
        options = SuggestionSettings(snogit_bm25=False, allowed_association_types=(), ancestor_max_distance=None,
                                     ancestor_max_relative_distance=None, bm25_semantic_tag_boost_percent=0)
        with patch("snomed_post_processing.pipelines.suggestion_generation.apply_semantic_bm25_fallback", side_effect=lambda suggestions, *a, **k: suggestions) as bm25:
            result = self.generate(settings=options)
        self.assertEqual(bm25.call_args.kwargs["semantic_tag_boost_percent"], 0)
        self.assertTrue(bm25.call_args.kwargs["allow_blacklist_findings"])
        self.assertEqual(json.loads(result.json)["metadata"]["settings"]["allowed_association_types"], [])
        with self.assertRaisesRegex(ValueError, "SNOGIT"):
            self.generate(settings=SuggestionSettings())
        for settings in (replace(options, bm25_min_score=float("nan")), replace(options, bm25_max_candidates=0),
                         replace(options, bm25_semantic_tag_boost_percent=101), replace(options, ancestor_max_relative_distance=2)):
            with self.assertRaises(ValueError):
                settings.validate()

    def test_real_bm25_and_release_custom_exclusions_use_existing_gates(self):
        result = self.generate(settings=replace(self.settings, semantic_bm25_fallback=True, snogit_bm25=False))
        allowed = {"990000002", "410671006", "990000201", "990000202", "990000203"}
        self.assertTrue(all(candidate.code in allowed for item in result.suggestions for candidate in item.candidates))
        with TemporaryDirectory() as directory:
            custom = Path(directory) / "exclusions.txt"
            custom.write_text("finding\n", encoding="utf-8")
            result = self.generate(settings=replace(self.settings, target_view="release", release_blacklist_mode="custom"), custom=custom)
        self.assertFalse(any(item.replacement_code for item in result.suggestions))
        self.assertGreater(sum(len(item.context_candidates) for item in result.suggestions), 0)

    def test_rule_worker_scans_annotations_without_findings_and_preserves_source(self):
        job = SuggestionJob(SourceFile(FIXTURE / "project.zip"), SourceFile(FIXTURE / "policy.hdf5"), PolicySettings(), self.settings)
        decisions, binding, _ = run_rules(job, DEFAULT_CONCEPT_RULES)
        self.assertEqual(len(decisions), 4)
        self.assertEqual(sum(item["action"] == "clear_id" for item in decisions), 2)
        self.assertEqual(sum(item["policy_overridden"] for item in decisions), 2)
        self.assertEqual(binding, job.binding())
        scoped = replace(job, policy=PolicySettings(annotators=("alice",)))
        self.assertEqual(len(run_rules(scoped, DEFAULT_CONCEPT_RULES)[0]), 2)

    def test_generation_worker_rejects_stale_session_stamps(self):
        job = SuggestionJob(SourceFile(FIXTURE / "project.zip"), SourceFile(FIXTURE / "policy.hdf5"), PolicySettings(), self.settings,
                            session_result=SimpleNamespace(), session_stamps=())
        with self.assertRaisesRegex(ValueError, "current policy"):
            run_generation(job)

    def test_processed_cache_actual_backend_with_named_dat_and_owned_output(self):
        from test.test_semantic_bm25_sanitization import _write_compact_hdf5
        with TemporaryDirectory() as directory:
            root = Path(directory)
            main, source = root / "main.h5", root / "SNOGIT_20260401.dat"
            _write_compact_hdf5(main)
            source.write_text("100\tx\tAlpha therapy\n200\tx\tBeta procedure\n", encoding="utf-8")
            members, _ = inspect_members(SourceFile(source))
            self.assertEqual([member.name for member in members], [source.name])
            cache = create_cache(SourceFile(main), SourceFile(source), (source.name,))
            self.assertTrue(cache.path.is_file())
            from snomed_post_processing.sanitization.snogit_sidecar import validate_snogit_sidecar_compatibility
            validate_snogit_sidecar_compatibility(cache.path, main)


def _native_gil_pause():
    """Simulate native work which, unlike a regular sleep, holds the worker GIL."""
    import ctypes
    if os.name == "nt":
        ctypes.PyDLL("kernel32").Sleep(800)
    else:
        ctypes.PyDLL(None).usleep(800_000)
    return os.getpid()


class GenerationProcessTest(unittest.IsolatedAsyncioTestCase):
    async def test_spawn_roundtrip_retains_uploads_and_keeps_heartbeat_responsive(self):
        # Actual Windows-style spawn, not an inline SDK mock; artificial files only.
        with TemporaryDirectory() as directory:
            owner = TemporaryDirectory(dir=directory)
            root = Path(owner.name)
            for name in ("project.zip", "policy.hdf5"):
                (root / name).write_bytes((FIXTURE / name).read_bytes())
            project, lists = (SourceFile(root / name, owner) for name in ("project.zip", "policy.hdf5"))
            policy = check_policy(project.path, lists.path, PolicySettings())
            job = SuggestionJob(project, lists, policy.settings,
                                SuggestionSettings(snogit_bm25=False, historical_ancestor_fallback=False),
                                session_result=policy, session_stamps=(project.stamp(), lists.stamp()))
            payload = job.for_process()
            self.assertTrue(policy.reports)
            self.assertFalse(payload.session_result.reports)
            self.assertTrue(all(source.owner is None for source in payload.sources))
            self.assertIs(job.project.owner, owner)
            loop = asyncio.get_running_loop()
            with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
                result, preview, snapshot = await loop.run_in_executor(pool, run_generation, payload)
                self.assertEqual(result.binding, job.binding())
                self.assertEqual(len(preview.findings), 10)
                self.assertEqual(len(preview.source_suggestions), 10)
                self.assertEqual(snapshot, (project.stamp(), lists.stamp()))
                task = loop.run_in_executor(pool, _native_gil_pause)
                ticks = [time.monotonic()]
                while not task.done():
                    await asyncio.sleep(0.02)
                    ticks.append(time.monotonic())
                self.assertNotEqual(await task, os.getpid())
                self.assertGreater(len(ticks), 10)
                self.assertLess(max(b - a for a, b in zip(ticks, ticks[1:])), 0.5)
            self.assertTrue(project.path.is_file())
            self.assertTrue(lists.path.is_file())
            owner.cleanup()


@unittest.skipUnless(find_spec("nicegui") is not None, "requires optional NiceGUI extra")
class GenerationControlsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from nicegui import ui, Client
        from nicegui.page import page
        from snomed_post_processing.gui.nicegui.policy_ui import PolicyCheckControls
        from snomed_post_processing.gui.nicegui.review_panel import ReviewPanelControls
        self.ui, self.client = ui, Client(page("/generation-test"))
        with self.client:
            self.policy = PolicyCheckControls(ui)
            banner, source, scope = ui.label(), ui.label(), ui.label()
            with ui.column() as parent:
                self.review = ReviewPanelControls(ui, parent, banner=banner, source=source, scope=scope)
            self.panel = SuggestionControls(ui, self.policy, lambda: self.review)
            self.panel.connect_review()
        self.worker = patch("nicegui.run.io_bound", new=AsyncMock(side_effect=inline))
        self.io = self.worker.start()
        self.cpu_worker = patch("nicegui.run.cpu_bound", new=AsyncMock(side_effect=inline))
        self.cpu = self.cpu_worker.start()
        self.editor = patch.object(self.panel.rule_editor, "get_client_data", new=AsyncMock(side_effect=lambda: copy.deepcopy(self.panel.records)))
        self.editor.start()
        for source, name in ((self.policy.project, "project.zip"), (self.policy.lists, "policy.hdf5")):
            source.mode.set_value("Server path")
            source.path.set_value(str(FIXTURE / name))
        self.panel.bm25.set_value(False)
        self.panel.ancestor.set_value(False)
        self.panel.associations.set_value(["REPLACED_BY"])

    async def asyncTearDown(self):
        self.panel.close()
        self.policy.close()
        self.client.delete()
        self.editor.stop()
        self.worker.stop()
        self.cpu_worker.stop()

    async def checked_generation(self):
        await self.policy.run_check()
        self.assertTrue(self.panel.generate_button.enabled)
        await self.panel.generate()
        self.assertIsNotNone(self.panel.completed, self.panel.status.text)
        self.assertIs(self.cpu.await_args.args[0], run_generation)
        self.assertFalse(any(call.args[0] is run_generation for call in self.io.await_args_list))

    async def test_input_changes_never_process_and_generation_does_not_replace_review(self):
        self.io.assert_not_awaited()
        self.assertIsNone(self.review.state.source_name)
        await self.checked_generation()
        self.assertIsNone(self.review.state.source_name)
        with self.client:
            await self.panel.open_review()
        self.assertEqual(len(self.review.state.findings), 10)
        self.assertFalse(self.review.controls.session.saved)
        self.assertFalse(self.review.controls.session.dirty)
        with patch.object(self.ui.download, "content") as download:
            await self.panel.download("json")
            self.assertEqual(len(json.loads(download.call_args.args[0])["suggestions"]), 10)
        self.panel.score.set_value(2)
        self.assertFalse(self.panel.results.visible)
        before = len(self.review.state.findings)
        await self.panel.open_review()
        self.assertEqual(len(self.review.state.findings), before)

    async def test_restored_suggestions_show_in_tab_two_and_require_explicit_handoff(self):
        from test.test_nicegui_suggestions import upload_event
        content = (FIXTURE / "suggestions.json").read_bytes()
        old_source = load_suggestions_preview(content, "old.json")
        with self.client:
            self.review.publish_generated(old_source)
        session = self.review.controls.session
        session.mark_document(old_source.findings[0].row_id, True)
        session.save()
        self.policy.project.path.set_value("")
        self.policy.lists.path.set_value("")
        await self.panel.load_suggestions(upload_event(content, "restored.json"))
        self.assertTrue(self.panel.results.visible, self.panel.status.text)
        self.assertEqual(len(self.panel.overview.options["rowData"]), 10)
        self.assertIs(self.review.state, old_source)
        self.assertIs(self.review.controls.session, session)
        self.assertTrue(session.reviewed_documents)
        self.policy.prefix.set_value("")
        self.assertTrue(self.panel.results.visible)
        with patch.object(self.ui.download, "content") as download:
            await self.panel.download("json")
            self.assertEqual(download.call_args.args[0], content.decode("utf-8"))
        with self.client:
            await self.panel.open_review()
        self.assertEqual(self.review.state.source_name, "restored.json")
        self.assertFalse(self.review.controls.session.saved)
        self.assertFalse(self.review.controls.session.reviewed_documents)
        self.assertFalse(self.review.controls.session.dirty)
        row = self.review.state.findings[0]
        restored_session = self.review.controls.session
        restored_session.stage(row.row_id, action="none")
        restored_session.save()
        reviewed = restored_session.export_text().encode()
        restored_session.stage(row.row_id, action="delete")
        restored_session.save()
        with self.client:
            await self.review.controls.load(upload_event(reviewed, "reviewed-decisions.json"))
        self.assertEqual(self.review.controls.session.saved[row.suggestion_index]["action"], "none")
        self.cpu.assert_not_awaited()

    async def test_suggestions_restore_failure_and_late_upload_keep_latest_artifact(self):
        from test.test_nicegui_suggestions import upload_event
        content = (FIXTURE / "suggestions.json").read_bytes()
        await self.panel.load_suggestions(upload_event(content, "first.json"))
        previous = self.panel.completed
        await self.panel.load_suggestions(upload_event(b"not-json", "bad.json"))
        self.assertIs(self.panel.completed, previous)
        entered, release = asyncio.Event(), asyncio.Event()
        async def slow_read():
            entered.set()
            await release.wait()
            return content
        event = SimpleNamespace(file=SimpleNamespace(name="older.json", size=lambda: len(content), read=slow_read))
        task = asyncio.create_task(self.panel.load_suggestions(event))
        await entered.wait()
        await self.panel.load_suggestions(upload_event(content, "newer.json"))
        release.set()
        await task
        self.assertEqual(self.panel.completed[1].source_name, "newer.json")
        self.assertIsNone(self.review.state.source_name)

    async def test_saved_findings_explain_missing_hdf5_and_generate_without_project(self):
        self.policy.project.path.set_value("")
        self.policy.lists.path.set_value("")
        content = (FIXTURE / "critical-findings.json").read_bytes()
        async def save(path):
            path.write_bytes(content)
        await self.policy.saved_findings.load(SimpleNamespace(file=SimpleNamespace(
            name="critical-findings.json", size=lambda: len(content), save=save)))
        await self.policy.load_saved()
        self.assertFalse(self.panel.generate_button.enabled)
        self.assertIn("SNOMED HDF5", self.panel.requirements.text)
        self.assertEqual(len(self.panel.generation_blockers()), 1)
        await self.panel.generate()
        self.cpu.assert_not_awaited()
        self.policy.lists.path.set_value(str(FIXTURE / "policy.hdf5"))
        self.assertTrue(self.panel.generate_button.enabled)
        self.assertIn("file validity", self.panel.requirements.text)
        await self.panel.generate()
        self.assertIsNotNone(self.panel.completed, self.panel.status.text)
        self.assertEqual(len(self.panel.completed[1].findings), 10)
        self.assertIsNone(self.panel.completed[2].project)

    async def test_generation_requirements_follow_cache_custom_settings_and_busy_state(self):
        self.assertIn("CriticalFindings JSON", self.panel.requirements.text)
        self.policy.saved_findings.mode.set_value("Server path")
        self.policy.saved_findings.path.set_value(str(FIXTURE / "critical-findings.json"))
        await self.policy.load_saved()
        read_calls = self.io.await_count
        self.panel.bm25.set_value(True)
        self.assertFalse(self.panel.generate_button.enabled)
        self.assertIn("processed SNOGIT cache", self.panel.requirements.text)
        self.panel.snogit.set_value(False)
        self.assertTrue(self.panel.generate_button.enabled)
        self.panel.target.set_value("release")
        self.panel.exclusion.set_value("custom")
        self.assertFalse(self.panel.generate_button.enabled)
        self.assertIn("custom exclusion-list rules", self.panel.requirements.text)
        self.panel.exclusion.set_value("none")
        self.panel.candidates.set_value(None)
        self.assertFalse(self.panel.generate_button.enabled)
        self.assertIn("Correct advanced suggestion settings", self.panel.requirements.text)
        self.panel.candidates.set_value(5)
        self.policy.project.uploading = True
        self.panel.refresh()
        self.assertIn("project ZIP upload", self.panel.requirements.text)
        self.policy.project.uploading = False
        self.panel.busy = True
        self.panel.refresh()
        self.assertFalse(self.panel.generate_button.enabled)
        self.assertIn("Wait for the current", self.panel.requirements.text)
        self.panel.busy = False
        self.panel.refresh()
        self.assertTrue(self.panel.generate_button.enabled)
        self.cpu.assert_not_awaited()
        self.assertEqual(self.io.await_count, read_calls)

    async def test_current_session_requirements_explain_policy_check_and_zip(self):
        self.policy.project.path.set_value("")
        self.assertIn("project ZIP", self.panel.requirements.text)
        self.assertIn("Run Check policy", self.panel.requirements.text)
        self.assertFalse(self.panel.generate_button.enabled)

    async def test_loading_annotators_normalizes_typed_scope_without_broadening(self):
        self.policy.annotators.set_options({" ALICE ": "Alice", "absent": "absent"}, value=[" ALICE ", "absent"])
        await self.policy.load_annotators()
        self.assertEqual(self.policy.settings().annotators, ("absent", "alice"))
        self.assertEqual(set(self.policy.annotators.value), {"absent", "alice"})

    async def test_saved_findings_source_supports_server_files_without_policy_check(self):
        self.policy.saved_findings.mode.set_value("Server path")
        self.policy.saved_findings.path.set_value(str(FIXTURE / "critical-findings.json"))
        await self.policy.load_saved()
        await self.panel.generate()
        self.assertIsNotNone(self.panel.completed, self.panel.status.text)
        self.assertIsNotNone(self.policy.imported_source)
        self.assertEqual(set(self.policy.result.reports), {"critical-findings.json"})

    async def test_restored_findings_bom_is_supported_and_changed_source_is_not_reused(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "findings.json"
            content = (FIXTURE / "critical-findings.json").read_bytes()
            path.write_bytes(b"\xef\xbb\xbf" + content)
            self.policy.saved_findings.mode.set_value("Server path")
            self.policy.saved_findings.path.set_value(str(path))
            await self.policy.load_saved()
            await self.panel.generate()
            previous = self.panel.completed
            self.assertIsNotNone(previous, self.panel.status.text)
            path.write_bytes(content + b" ")
            await self.panel.generate()
            self.assertIs(self.panel.completed, previous)
            self.assertIn("Generation failed", self.panel.status.text)

    async def test_generation_failure_keeps_success_and_late_worker_is_discarded(self):
        await self.checked_generation()
        previous = self.panel.completed
        with patch("snomed_post_processing.gui.nicegui.suggestion_ui.run_generation", side_effect=ValueError("private contents")):
            await self.panel.generate()
        self.assertIs(self.panel.completed, previous)
        self.assertNotIn("private contents", self.panel.status.text)
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed(function, *args, **kwargs):
            if function is run_generation:
                entered.set()
                await release.wait()
            return function(*args, **kwargs)
        with patch("nicegui.run.cpu_bound", side_effect=delayed):
            task = asyncio.create_task(self.panel.generate())
            await entered.wait()
            self.policy.prefix.set_value("")
            release.set()
            await task
        self.assertIs(self.panel.completed, previous)
        self.assertFalse(self.panel.results.visible)

    async def test_rules_stage_then_save_checkbox_choices_and_preserve_on_reapply(self):
        with self.client:
            await self.panel.apply_rules()
        session = self.review.controls.session
        self.assertEqual(len(session.draft_rules), 4, self.panel.status.text)
        self.assertTrue(session.dirty)
        with self.assertRaises(ReviewError):
            session.export_text()
        self.review.controls.command("save")
        self.assertEqual(len(session.rules), 4)
        self.assertFalse(session.dirty)
        row = dict(self.review.rule_grid.options["rowData"][0], apply=False)
        self.review.toggle_rule(SimpleNamespace(args={"data": row}))
        self.review.controls.command("save")
        self.assertFalse(session.rules[0]["apply"])
        self.assertTrue(session.rules[0]["rule_reviewed_by_human"])
        with self.client:
            await self.panel.apply_rules()
        self.assertEqual(sum(not item["apply"] for item in session.draft_rules), 1)
        self.review.controls.command("save")
        text = session.export_text()
        restored = load_review(text.encode(), self.review.state)
        self.assertEqual(len(restored.rules), 4)
        self.assertTrue(any(not item["apply"] for item in restored.rules))
        self.panel.clear_rules()
        self.assertEqual(session.effective_rules, [])
        self.review.controls.command("save")
        self.assertFalse(json.loads(session.export_text())["decisions"])
        self.assertEqual(len(self.panel.records), 2)

    async def test_generation_handoff_preserves_same_input_saved_rule_choices(self):
        with self.client:
            await self.panel.apply_rules()
        self.review.controls.session.save()
        row = dict(self.review.rule_grid.options["rowData"][0], apply=False)
        self.review.toggle_rule(SimpleNamespace(args={"data": row}))
        self.review.controls.session.save()
        await self.checked_generation()
        with self.client:
            await self.panel.open_review()
        self.assertEqual(len(self.review.controls.session.rules), 4)
        self.assertEqual(sum(not item["apply"] for item in self.review.controls.session.rules), 1)
        self.assertFalse(self.review.controls.session.invalid_rules)
        self.assertEqual(len(self.review.state.findings), 10)

    async def test_uploaded_snogit_keeps_filename_for_member_recognition(self):
        self.panel.snogit_source.mode.set_value("Upload")
        content = b"990000201\tx\tSynthetic term\n"
        async def save(path):
            path.write_bytes(content)
        event = SimpleNamespace(file=SimpleNamespace(name="SNOGIT_20260401.dat", size=lambda: len(content), save=save))
        await self.panel.snogit_source.load(event)
        self.assertEqual(self.panel.snogit_source.snapshot().path.name, event.file.name)
        await self.panel.inspect_snogit()
        self.assertEqual(self.panel.members.value, [event.file.name])

    async def test_restored_rule_edits_require_reapply_and_original_annotation_validation(self):
        with self.client:
            await self.panel.apply_rules()
        self.review.controls.session.save()
        self.review.controls.refresh()
        row = dict(self.review.rule_grid.options["rowData"][0], apply=False)
        self.review.toggle_rule(SimpleNamespace(args={"data": row}))
        self.review.controls.session.save()
        text = self.review.controls.session.export_text()
        self.review.controls.session = load_review(text.encode(), self.review.state)
        self.assertIsNone(self.review.controls.session.active_rule_binding)
        with self.client:
            await self.panel.apply_rules()
        self.assertIsNotNone(self.review.controls.session.active_rule_binding)
        self.assertTrue(any(not item["apply"] for item in self.review.controls.session.effective_rules))
        self.review.controls.session.save()
        # A forged saved annotation identity cannot become an editable local rule.
        payload = json.loads(text)
        payload["decisions"][0]["offset"] = [999, 1000]
        self.review.controls.session = load_review(json.dumps(payload).encode(), self.review.state)
        with self.client:
            await self.panel.apply_rules()
        self.assertIsNone(self.review.controls.session.active_rule_binding)

    async def test_rules_and_manual_choices_conflict_without_overwriting_manual(self):
        await self.checked_generation()
        with self.client:
            await self.panel.open_review()
        session = self.review.controls.session
        source = next(row for row in self.review.state.findings if row.code == "410680006")
        session.stage(source.row_id)
        session.save()
        saved = copy.deepcopy(session.saved)
        with self.client:
            await self.panel.apply_rules()
        self.assertTrue(session.rule_conflicts()[1])
        with self.assertRaisesRegex(ReviewError, "conflict"):
            session.save()
        self.assertEqual(session.saved, saved)
        self.review.keep_manual_rules()
        session.save()
        self.assertEqual(session.saved, saved)
        self.assertEqual(len(session.rules), 3)

    async def test_rule_inputs_and_external_files_guard_export_and_clear_recovers(self):
        with self.client:
            await self.panel.apply_rules()
        session = self.review.controls.session
        session.save()
        self.policy.annotators.set_options({"alice": "Alice"}, value=["alice"])
        self.assertTrue(session.invalid_rules)
        with self.assertRaises(ReviewError):
            session.export_text()
        with self.assertRaises(ReviewError):
            await self.panel.validate_rules_current()
        self.panel.clear_rules()
        session.save()
        self.assertFalse(session.invalid_rules)
        self.assertEqual(json.loads(session.export_text())["decisions"], [])

    async def test_rule_only_source_download_pairs_with_review_and_revalidates_after_reload(self):
        with self.client:
            await self.panel.apply_rules()
        session = self.review.controls.session
        session.save()
        self.review.controls.refresh()
        row = dict(next(row for row in self.review.rule_grid.options["rowData"] if row["action"] == "replace"), apply=False)
        self.review.toggle_rule(SimpleNamespace(args={"data": row}))
        session.save()
        with patch.object(self.ui.download, "content") as download:
            self.review.download_rule_source()
        source = load_suggestions_preview(download.call_args.args[0].encode())
        review = load_review(session.export_text().encode(), source)
        self.assertEqual(len(review.rules), 4)
        # Uploaded files get new temporary paths after reconnect: explicit Apply
        # may rebind rule-only input only after validating preserved annotations.
        source.metadata["nicegui_generation_binding"] = "previous-upload"
        self.review.state = source
        self.review.controls.session = review
        self.panel.target.set_value("release")
        with self.client:
            await self.panel.apply_rules()
        self.assertEqual(sum(not item["apply"] for item in self.review.controls.session.effective_rules), 1)
        self.assertFalse(any(item["policy_overridden"] for item in self.review.controls.session.effective_rules))
        self.assertIsNotNone(self.review.controls.session.active_rule_binding)
        self.assertNotEqual(self.review.state.metadata["nicegui_generation_binding"], "previous-upload")

    async def test_generated_source_binding_prevents_unrelated_rule_only_restore(self):
        with self.client:
            await self.panel.apply_rules()
        session = self.review.controls.session
        session.save()
        artifact = session.export_text().encode()
        other = copy.deepcopy(self.review.state)
        other.metadata["nicegui_generation_binding"] = "another-project"
        with self.assertRaisesRegex(ReviewError, "project/scope"):
            load_review(artifact, other)

    async def test_loading_rule_definitions_is_atomic_and_never_applies(self):
        content = rules_json_text(DEFAULT_CONCEPT_RULES[:1]).encode()
        event = SimpleNamespace(file=SimpleNamespace(size=lambda: len(content), read=AsyncMock(return_value=content)))
        await self.panel.load_rules(event)
        self.assertEqual(len(self.panel.records), 1)
        self.assertIsNone(self.review.state.source_name)
        event.file.read = AsyncMock(return_value=b"invalid private data")
        await self.panel.load_rules(event)
        self.assertEqual(len(self.panel.records), 1)
        self.assertNotIn("private data", self.panel.status.text)

    async def test_newest_rule_upload_wins_even_when_older_upload_finishes_first(self):
        entered_a, entered_b, release_a, release_b = (asyncio.Event() for _ in range(4))
        async def read_a():
            entered_a.set()
            await release_a.wait()
            return rules_json_text(DEFAULT_CONCEPT_RULES).encode()
        async def read_b():
            entered_b.set()
            await release_b.wait()
            return rules_json_text(DEFAULT_CONCEPT_RULES[:1]).encode()
        first = SimpleNamespace(file=SimpleNamespace(size=lambda: 100, read=read_a))
        second = SimpleNamespace(file=SimpleNamespace(size=lambda: 100, read=read_b))
        task_a = asyncio.create_task(self.panel.load_rules(first))
        await entered_a.wait()
        task_b = asyncio.create_task(self.panel.load_rules(second))
        await entered_b.wait()
        release_a.set()
        await task_a
        release_b.set()
        await task_b
        self.assertEqual(len(self.panel.records), 1)
        self.assertIsNone(self.review.state.source_name)

    async def test_late_rule_worker_cannot_overwrite_a_new_manual_edit(self):
        await self.checked_generation()
        with self.client:
            await self.panel.open_review()
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed(function, *args, **kwargs):
            if function is run_rules:
                entered.set()
                await release.wait()
            return function(*args, **kwargs)
        with patch("nicegui.run.io_bound", side_effect=delayed):
            task = asyncio.create_task(self.panel.apply_rules())
            await entered.wait()
            self.review.controls.session.stage(self.review.state.findings[0].row_id)
            release.set()
            await task
        self.assertIsNone(self.review.controls.session.draft_rules)
        self.assertTrue(self.review.controls.session.drafts)

    async def test_external_source_change_blocks_generation_download(self):
        await self.checked_generation()
        from snomed_post_processing.gui.nicegui.suggestion_ui import stamps
        with patch("snomed_post_processing.gui.nicegui.suggestion_ui.stamps", return_value=()):
            with patch.object(self.ui.download, "content") as download:
                await self.panel.download("json")
        download.assert_not_called()
        self.assertFalse(self.panel.results.visible)

    async def test_cache_creation_never_runs_generation(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "SNOGIT_20260401.dat"
            source.write_text("990000201\tx\tSynthetic term\n", encoding="utf-8")
            self.panel.snogit_source.mode.set_value("Server path")
            self.panel.snogit_source.path.set_value(str(source))
            await self.panel.inspect_snogit()
            self.assertEqual(self.panel.members.value, [source.name])
            await self.panel.build_cache()
            self.assertIsNotNone(self.panel.created_cache, self.panel.status.text)
            self.assertIsNone(self.panel.completed)
            self.assertIsNone(self.review.state.source_name)
            with patch.object(self.ui.download, "file") as download:
                await self.panel.download_cache()
            download.assert_called_once()
            await self.policy.run_check()
            self.panel.bm25.set_value(True)
            await self.panel.generate()
            self.assertIsNotNone(self.panel.completed, self.panel.status.text)
            settings = json.loads(self.panel.completed[0].json)["metadata"]["settings"]
            self.assertEqual(settings["snogit_members"], [source.name])
