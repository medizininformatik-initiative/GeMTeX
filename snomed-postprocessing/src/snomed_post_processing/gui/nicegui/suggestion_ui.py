"""Explicit rules and suggestion generation, sharing tab 1 inputs and backend engines."""
import copy
from dataclasses import asdict
import io
import uuid

from snomed_post_processing.pipelines.suggestion_generation import DEFAULT_ASSOCIATIONS, SuggestionSettings
from snomed_post_processing.sanitization import ASSOCIATION_TYPE_DESCRIPTIONS, SUPPORTED_ASSOCIATION_TYPES
from snomed_post_processing.sanitization.concept_rules import (
    ConceptRule, DEFAULT_CONCEPT_RULES, preserve_rule_edits, read_rules_json, rules_json_text, validate_rules,
)
from .file_sources import FileSource
from .review import ReviewError
from .suggestion_jobs import (
    SuggestionJob, create_cache, inspect_members, restore_suggestions, run_generation, run_rules, stamps, validate_preserved_rules,
)
from .suggestions import MAX_SUGGESTIONS_BYTES, SuggestionsPreviewError, load_suggestions_preview


def rule_records(rules):
    return [{"row_id": uuid.uuid4().hex, **asdict(rule)} for rule in rules]


def rules_from_records(rows):
    rules = []
    for row in rows:
        values = {name: "" if row.get(name) is None else str(row[name]).strip()
                  for name in ("rule_id", "name", "source_code", "action", "target_code")}
        values.update(enabled=row.get("enabled", True), override_policy=row.get("override_policy", True))
        rules.append(ConceptRule(**values))
    return validate_rules(rules)


class SuggestionControls:
    def __init__(self, ui, policy, get_review):
        self.ui, self.policy, self.get_review = ui, policy, get_review
        self.revision = self.rule_revision = self.rule_load_revision = 0
        self.ready = self.closed = self.busy = False
        self.completed = self.created_cache = self.member_stamp = None
        self.artifact_revision = 0
        self.created_caches = []
        self.rule_job = self.rule_stamps = None
        self.records = rule_records(DEFAULT_CONCEPT_RULES)
        ui.label("Uses the shared Inputs sidebar for HDF5, annotator scope and annotation settings. Saved findings require HDF5 but no project ZIP; ZIP is optional for context and required for policy checks/rules. Inputs never start processing.").classes("text-sm")
        with ui.expansion("Concept rules").classes("w-full"):
            ui.label("Match original IDs across all selected layers and annotators, including annotations without findings. ID-only changes; no chaining.").classes("text-sm")
            self.rule_editor = ui.aggrid({
                "columnDefs": [
                    {"field": "enabled", "cellDataType": "boolean", "width": 100},
                    *[{"field": key, "cellDataType": "text"} for key in ("rule_id", "name", "source_code")],
                    {"field": "action", "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": ["clear_id", "replace"]}},
                    {"field": "target_code", "cellDataType": "text"},
                    {"field": "override_policy", "headerName": "Override policy", "cellDataType": "boolean"},
                ], "defaultColDef": {"editable": True, "resizable": True, "sortable": True},
                "rowSelection": {"mode": "multiRow"}, "rowData": self.records, "stopEditingWhenCellsLoseFocus": True,
                ":getRowId": "params => params.data.row_id",
            }).classes("w-full h-64 overflow-auto overscroll-contain")
            self.rule_editor.on("cellValueChanged", lambda _: self.changed(rule_inputs=True), args=["data"])
            with ui.row():
                ui.button("Add rule", on_click=self.add_rule).props("flat dense")
                ui.button("Remove selected rules", on_click=self.remove_rules).props("flat dense")
                ui.button("Download concept rules JSON", on_click=self.download_rules).props("flat dense")
            self.rule_upload = ui.upload(label="Load concept rules JSON (definitions only)", on_upload=self.load_rules,
                                         auto_upload=True, multiple=False, max_file_size=MAX_SUGGESTIONS_BYTES) \
                .props("accept=.json").classes("max-w-full")
            ui.label("clear_id = Remove ID only; replace = Replace concept. Override policy bypasses list restrictions, never target existence/activity or manual decisions.").classes("text-sm")
            self.apply_button = ui.button("Apply rules to review", on_click=self.apply_rules)
            ui.button("Clear all pending rule decisions", on_click=self.clear_rules).props("flat dense")
            ui.label("Apply stages decisions in tab 3; Save choices commits them. Loading/editing definitions does not apply rules or change CAS.").classes("text-sm")
        with ui.expansion("Restore suggestions JSON", value=True).classes("w-full"):
            self.uploader = ui.upload(label="Load suggestions JSON", on_upload=self.load_suggestions,
                                      auto_upload=True, multiple=False, max_file_size=MAX_SUGGESTIONS_BYTES,
                                      on_rejected=lambda: self.restore_status.set_text("Upload rejected. Choose suggestions JSON up to 50 MiB; previous state retained.")) \
                .props("accept=.json").classes("max-w-full")
            self.restore_status = ui.label("Restores the suggestions table without analysis or HDF5/project access. Review stays unchanged until Load in review.").classes("text-sm")
        self.findings_source = ui.label().classes("text-sm")
        with ui.expansion("Replacement requirements", value=True).classes("w-full"):
            self.target = ui.select({"policy": "Policy rules", "release": "Active release"}, value="policy", on_change=self.requirements_changed)
            self.exclusion = ui.select({"none": "No exclusion list", "embedded": "Embedded exclusion list",
                                        "custom": "Custom exclusion list", "embedded+custom": "Embedded and custom exclusion lists"},
                                       value="none", label="Active-release exclusions", on_change=self.requirements_changed)
            self.custom = FileSource(ui, "Custom exclusion-list rules", (".txt", ".tsv", ".csv"), policy.data_dir,
                                     lambda: self.changed(rule_inputs=True))
            ui.label("Policy rules requires active inclusion-list concepts outside exclusions. Active release requires active concepts with optional exclusions. Neither changes Check policy; explicit rules may override list restrictions.").classes("text-sm")
        with ui.row().classes("w-full"):
            self.ancestor = ui.checkbox("Historical ancestor fallback", value=True, on_change=self.changed)
            self.bm25 = ui.checkbox("Semantic BM25 fallback", value=True, on_change=self.changed)
            self.blacklist_bm25 = ui.checkbox("Include exclusion-list findings in BM25 fallback", value=True, on_change=self.changed)
        with ui.expansion("Advanced suggestion settings", value=True).classes("w-full"):
            self.associations = ui.select({name: f"{name} — {ASSOCIATION_TYPE_DESCRIPTIONS.get(name, '')}" for name in SUPPORTED_ASSOCIATION_TYPES},
                                          multiple=True, value=list(DEFAULT_ASSOCIATIONS), label="Allowed historical association types",
                                          on_change=self.changed).classes("w-full")
            with ui.row():
                self.absolute = ui.checkbox("Use absolute ancestor distance limit", value=True, on_change=self.changed)
                self.distance = ui.number("Maximum absolute ancestor distance", value=3, min=1, max=20, step=1, on_change=self.changed)
                self.relative = ui.checkbox("Use relative ancestor distance limit", value=True, on_change=self.changed)
                self.ratio = ui.number("Maximum relative ancestor distance", value=0.35, min=0, max=1, step=0.05, on_change=self.changed)
            with ui.row():
                self.score = ui.number("Minimum BM25 score", value=1.5, min=0, step=0.1, on_change=self.changed)
                self.lexical = ui.number("Minimum lexical overlap ratio", value=0, min=0, max=1, step=0.05, on_change=self.changed)
                self.candidates = ui.number("Maximum retained candidates", value=5, min=1, max=50, step=1, on_change=self.changed)
                self.boost = ui.number("Matching semantic-tag boost (%)", value=10, min=0, max=100, on_change=self.changed)
            ui.label("FSN tags are excluded from lexical matching; 0% disables the separate tag boost. Cutoff ties and incomplete-retrieval flags are retained. BM25 scores are not clinical confidence.").classes("text-sm")
            self.snogit = ui.checkbox("Use SNOGIT/interface terms for BM25 candidates", value=True, on_change=self.changed)
            self.cache = FileSource(ui, "Processed SNOGIT cache HDF5", (".hdf5", ".h5"), policy.data_dir, self.changed)
            self.snogit_source = FileSource(ui, "SNOGIT ZIP or .dat source", (".zip", ".dat"), policy.data_dir, self.snogit_changed)
            with ui.row():
                self.inspect_button = ui.button("Inspect SNOGIT members", on_click=self.inspect_snogit)
                self.members = ui.select([], multiple=True, value=[], label="SNOGIT members (newest general file by default)", on_change=self.changed).classes("grow")
            with ui.row():
                self.cache_button = ui.button("Create processed SNOGIT cache", on_click=self.build_cache)
                self.cache_download = ui.button("Download created SNOGIT cache", on_click=self.download_cache)
            ui.label("Select/create a compatible cache or turn SNOGIT off. Cache creation never starts generation; generated caches are temporary until downloaded.").classes("text-sm")
        with ui.row():
            self.generate_button = ui.button("Generate sanitization suggestions", on_click=self.generate)
            self.spinner = ui.spinner()
        self.requirements = ui.label().classes("text-sm whitespace-pre-wrap").props("role=status aria-live=polite")
        self.status = ui.label().classes("text-sm whitespace-pre-wrap")
        with ui.column().classes("w-full") as self.results:
            self.summary = ui.label()
            self.overview = ui.aggrid({
                "columnDefs": [{"field": field} for field in ("document", "annotator", "code", "status", "proposed_code", "candidate_count")]
                              + [{"field": "text", "headerName": "Covered text", "flex": 2, "minWidth": 350}],
                "defaultColDef": {"sortable": True, "filter": "agTextColumnFilter", "resizable": True, "editable": False},
                "rowData": [], ":getRowId": "params => params.data.row_id",
            }).classes("w-full h-64 overflow-auto overscroll-contain")
            with ui.row():
                self.open_button = ui.button("Load in review (replaces review)", on_click=self.open_review)
                ui.button("Download suggestions JSON", on_click=lambda: self.download("json"))
                ui.button("Download suggestions Markdown", on_click=lambda: self.download("markdown"))
            ui.label("Loading replaces generic choices and flags; same-input rule choices are retained. Download existing reviewed decisions first if needed. No target is approved automatically.").classes("text-sm")
        self.cache.mode.set_value("Data directory")
        self.snogit_source.mode.set_value("Data directory")
        policy.listeners.append(self.shared_changed)
        policy.result_listeners.append(self.policy_result_changed)
        ui.context.client.on_delete(self.close)
        self.ready = True
        self.refresh()

    @property
    def version(self):
        return self.revision, self.policy.revision

    def connect_review(self):
        self.get_review().controls.before_export = self.validate_rules_current

    def changed(self, _=None, *, rule_inputs=False):
        if not self.ready or self.closed:
            return
        self.revision += 1
        if rule_inputs:
            self.rule_revision += 1
            review = self.get_review()
            if review is not None:
                session = review.controls.session
                was_invalid = session.invalid_rules
                if session.rule_binding is not None:
                    session.rules_stale = True
                if session.draft_rule_binding is not None:
                    session.draft_rules_stale = True
                if session.invalid_rules != was_invalid:
                    review.controls.refresh()
        self.status.set_text("Inputs changed. Run the desired action explicitly; previous successful generation retained.")
        self.refresh()

    def requirements_changed(self, _=None):
        self.changed(rule_inputs=True)

    def policy_result_changed(self):
        self.changed()

    def shared_changed(self):
        for source in (self.custom, self.cache, self.snogit_source):
            source.refresh_directory()
        self.changed(rule_inputs=True)

    def snogit_changed(self):
        self.member_stamp = None
        if self.ready:
            self.members.set_options([], value=[])
        self.changed()

    def generation_blockers(self):
        blockers = []
        if self.busy:
            blockers.append("Wait for the current generation, rule or cache task to finish.")
        if self.policy.lists.snapshot() is None:
            blockers.append("Select or finish uploading the SNOMED HDF5 in the shared Inputs sidebar.")
        if not self.policy.result_current:
            blockers.append("Run Check policy (project ZIP required), or restore CriticalFindings JSON in tab 1.")
        if self.policy.project.uploading:
            blockers.append("Wait for the project ZIP upload to finish before using it for context.")
        if self.bm25.value and self.snogit.value:
            if self.cache.uploading or (self.cache.snapshot() is None and self.created_cache is None):
                blockers.append("Select/create a processed SNOGIT cache, finish its upload, or turn off SNOGIT under Advanced suggestion settings.")
        if self.target.value == "release" and "custom" in self.exclusion.value and self.custom.snapshot() is None:
            blockers.append("Select or finish uploading custom exclusion-list rules under Replacement requirements.")
        try:
            self.settings()
        except (ValueError, TypeError, OverflowError):
            blockers.append("Correct advanced suggestion settings (thresholds and candidate/ancestor limits).")
        return blockers

    def refresh(self):
        custom = self.target.value == "release" and "custom" in self.exclusion.value
        self.exclusion.set_visibility(self.target.value == "release")
        self.custom.container.set_visibility(custom)
        if self.policy.result_current:
            origin = "Restored findings" if self.policy.imported_source is not None else "Current policy check"
            self.findings_source.set_text(f"Findings from tab 1: {origin} · {len(self.policy.result.findings)} findings.")
        else:
            self.findings_source.set_text("No current findings. Run or restore them in tab 1.")
        available = self.policy.lists.snapshot() is not None
        blockers = self.generation_blockers()
        self.generate_button.set_enabled(not blockers)
        self.requirements.set_text("Cannot generate yet:\n" + "\n".join(f"• {reason}" for reason in blockers)
                                   if blockers else "Inputs selected. Click Generate to start; file validity and findings scope are checked during generation.")
        self.apply_button.set_enabled(not self.busy and available and self.policy.project.snapshot() is not None)
        self.inspect_button.set_enabled(not self.busy and self.snogit_source.snapshot() is not None)
        self.cache_button.set_enabled(not self.busy and available and self.member_stamp is not None and bool(self.members.value))
        self.cache_download.set_enabled(not self.busy and self.created_cache is not None)
        self.spinner.set_visibility(self.busy)
        self.uploader.set_enabled(not self.busy)
        self.results.set_visibility(self.artifact_current and not self.busy)

    def settings(self, *, rules=False):
        base = dict(target_view=self.target.value, release_blacklist_mode=self.exclusion.value)
        if rules:
            return SuggestionSettings(**base)
        for widget in (self.candidates, self.distance) if self.absolute.value else (self.candidates,):
            if widget.value is None or int(widget.value) != widget.value:
                raise ValueError("Candidate count and absolute distance must be whole numbers.")
        settings = SuggestionSettings(**base, allowed_association_types=tuple(self.associations.value),
            historical_ancestor_fallback=self.ancestor.value, ancestor_max_distance=int(self.distance.value) if self.absolute.value else None,
            ancestor_max_relative_distance=float(self.ratio.value) if self.relative.value else None,
            semantic_bm25_fallback=self.bm25.value, blacklist_bm25_suggestions=self.blacklist_bm25.value,
            bm25_min_score=float(self.score.value), bm25_min_lexical_score=float(self.lexical.value),
            bm25_max_candidates=int(self.candidates.value), bm25_semantic_tag_boost_percent=float(self.boost.value), snogit_bm25=self.snogit.value)
        settings.validate()
        return settings

    def job(self, *, rules=False):
        settings = self.settings(rules=rules)
        if rules and not (self.policy.layers.value or "").strip():
            raise ValueError("Select at least one annotation layer.")
        lists = self.policy.lists.snapshot()
        if lists is None:
            raise ValueError("Select the SNOMED HDF5 in the shared Inputs sidebar.")
        custom = self.custom.snapshot() if settings.target_view == "release" and "custom" in settings.release_blacklist_mode else None
        if settings.target_view == "release" and "custom" in settings.release_blacklist_mode and custom is None:
            raise ValueError("Select custom exclusion-list rules.")
        findings_file = None if rules else self.policy.imported_source
        result = None if rules or findings_file is not None else self.policy.result
        if not rules and not self.policy.result_current:
            raise ValueError("Run Check policy or restore CriticalFindings JSON in tab 1.")
        cache = None if rules or not (settings.semantic_bm25_fallback and settings.snogit_bm25) else self.cache.snapshot() or self.created_cache
        return SuggestionJob(self.policy.project.snapshot(), lists, self.policy.settings(), settings, custom, cache,
                             findings_file, result, self.policy.completed_stamps,
                             self.policy.completed_stamps[0] if findings_file is not None else None)

    async def generate(self):
        from nicegui import run
        if self.busy or self.closed:
            return
        if self.generation_blockers():
            self.refresh()
            return
        try:
            job = self.job()
        except (ValueError, TypeError) as error:
            self.status.set_text(str(error))
            return
        version = self.version
        self.artifact_revision += 1
        token = self.artifact_revision
        self.busy = True
        self.status.set_text("Generating suggestions… No review or CAS changes.")
        self.refresh()
        try:
            # Native HDF5/BM25 work can hold the GIL even in a thread and starve
            # Socket.IO heartbeats. Keep the owning job here, send only data/paths.
            result, preview, snapshot = await run.cpu_bound(run_generation, job.for_process())
            if self.closed or version != self.version or token != self.artifact_revision:
                return
            self.completed = result, preview, job, snapshot, version
            self.render_artifact()
            self.status.set_text("Suggestions ready. Load them in review separately; no decisions approved.")
        except Exception:
            if not self.closed and version == self.version:
                self.status.set_text("Generation failed. Check CriticalFindings JSON (up to 50 MiB), scope/ID settings, replacement requirements, HDF5 and SNOGIT compatibility. Previous successful generation retained.")
        finally:
            self.busy = False
            if not self.closed:
                self.refresh()

    @property
    def artifact_current(self):
        return self.completed is not None and (self.completed[2] is None or self.completed[-1] == self.version)

    def render_artifact(self):
        result, preview = self.completed[:2]
        fields = ("row_id", "document", "annotator", "code", "status", "proposed_code", "candidate_count", "text")
        self.overview.options["rowData"] = [{name: getattr(row, name) for name in fields} for row in preview.findings]
        self.overview.update()
        statuses = {}
        for finding in preview.findings:
            statuses[finding.status] = statuses.get(finding.status, 0) + 1
        self.summary.set_text(f"Source: {preview.source_name} · {len(preview.findings)} suggestions · " +
                              " · ".join(f"{key}: {value}" for key, value in sorted(statuses.items())))

    async def load_suggestions(self, event):
        from nicegui import run
        if self.closed or self.busy:
            return
        self.artifact_revision += 1
        token = self.artifact_revision
        self.restore_status.set_text("Loading suggestions JSON; previous suggestions and review retained until successful restore.")
        try:
            if event.file.size() > MAX_SUGGESTIONS_BYTES:
                raise SuggestionsPreviewError("Suggestions JSON exceeds the 50 MiB limit.")
            content = await event.file.read()
            result, preview = await run.io_bound(restore_suggestions, content, event.file.name)
            if self.closed or token != self.artifact_revision:
                return
            self.completed = result, preview, None, (), None
            self.render_artifact()
            self.restore_status.set_text("Suggestions restored in tab 2. Review unchanged; use Load in review (replaces review) explicitly.")
            self.refresh()
        except Exception:
            if not self.closed and token == self.artifact_revision:
                self.restore_status.set_text("Could not restore suggestions JSON (limit 50 MiB). Previous suggestions/review retained.")
        finally:
            if not self.closed and token == self.artifact_revision:
                self.uploader.reset()

    async def current_result(self):
        from nicegui import run
        completed = self.completed
        if self.closed or self.busy or not self.artifact_current:
            raise ReviewError("Generation inputs changed. Generate current suggestions first.")
        if completed[2] is not None and await run.io_bound(stamps, completed[2].sources) != completed[3]:
            self.changed(rule_inputs=True)
            raise ReviewError("Generation source files changed. Generate suggestions again.")
        if self.closed or completed is not self.completed or not self.artifact_current:
            raise ReviewError("Inputs changed during preparation. Try again.")
        return completed

    async def download(self, kind):
        try:
            completed = await self.current_result()
            self.ui.download.content(getattr(completed[0], kind), "sanitization-suggestions." + ("json" if kind == "json" else "md"))
        except (ReviewError, OSError):
            self.status.set_text("Generation inputs changed or are unavailable. Generate again before downloading.")

    def review_token(self):
        review = self.get_review()
        return review.state, review.controls.session, review.load_revision, review.controls.session.revision

    async def open_review(self):
        token = self.review_token()
        try:
            completed = await self.current_result()
            if token != self.review_token():
                raise ReviewError("Review changed during preparation. Load generated suggestions again if you want to replace it.")
            self.get_review().publish_generated(copy.deepcopy(completed[1]))
            self.status.set_text("Suggestions loaded in tab 3. No choices approved; Save/export remain explicit.")
        except (ReviewError, OSError):
            self.status.set_text("Review or generation inputs changed. Review unchanged; retry with current results.")

    async def read_editor(self):
        revision = self.rule_revision
        rows = await self.rule_editor.get_client_data()
        if self.closed or revision != self.rule_revision:
            raise ReviewError("Rule definitions changed while reading the editor. Try again.")
        return rules_from_records(rows)

    async def add_rule(self):
        revision = self.rule_revision
        rows = await self.rule_editor.get_client_data()
        if self.closed or revision != self.rule_revision:
            return
        rows.extend(rule_records((ConceptRule(uuid.uuid4().hex, "", "", "clear_id"),)))
        self.records = rows
        self.rule_editor.options["rowData"] = rows
        self.rule_editor.update()
        self.changed(rule_inputs=True)

    async def remove_rules(self):
        revision = self.rule_revision
        rows = await self.rule_editor.get_client_data()
        selected = {row["row_id"] for row in await self.rule_editor.get_selected_rows()}
        if self.closed or revision != self.rule_revision:
            return
        self.records = [row for row in rows if row["row_id"] not in selected]
        self.rule_editor.options["rowData"] = self.records
        self.rule_editor.update()
        self.changed(rule_inputs=True)

    async def load_rules(self, event):
        from nicegui import run
        self.rule_load_revision += 1
        token, revision = self.rule_load_revision, self.rule_revision
        try:
            if event.file.size() > MAX_SUGGESTIONS_BYTES:
                raise ValueError()
            content = await event.file.read()
            rules = await run.io_bound(read_rules_json, io.StringIO(content.decode("utf-8-sig")))
            if self.closed or token != self.rule_load_revision or revision != self.rule_revision:
                return
            self.records = rule_records(rules)
            self.rule_editor.options["rowData"] = self.records
            self.rule_editor.update()
            self.changed(rule_inputs=True)
            self.status.set_text("Rule definitions loaded. Apply rules separately; existing review unchanged.")
        except Exception:
            if not self.closed and token == self.rule_load_revision and revision == self.rule_revision:
                self.status.set_text("Invalid concept-rules JSON. Definitions/review unchanged.")
        finally:
            if not self.closed and token == self.rule_load_revision:
                self.rule_upload.reset()

    async def download_rules(self):
        try:
            self.ui.download.content(rules_json_text(await self.read_editor()), "concept_rules.json")
        except (ValueError, TypeError, TimeoutError):
            self.status.set_text("Correct rule definitions or reopen the editor before downloading.")

    async def apply_rules(self):
        from nicegui import run
        from snomed_post_processing.sanitization.json_io import sanitization_suggestions_json_text
        if self.busy or self.closed:
            return
        try:
            rules = await self.read_editor()
            if self.closed or self.busy:
                return
            job = self.job(rules=True)
        except (ValueError, TypeError, TimeoutError):
            self.status.set_text("Correct rule definitions and select project/HDF5/annotation inputs first.")
            return
        version, rule_version, token = self.version, self.rule_revision, self.review_token()
        self.busy = True
        self.status.set_text("Scanning original annotations for explicit rules…")
        self.refresh()
        try:
            decisions, binding, snapshot = await run.io_bound(run_rules, job, rules)
            previous = self.get_review().controls.session
            if previous.effective_rules and previous.active_rule_binding not in (None, binding):
                raise ReviewError("Clear old rule decisions before applying rules to changed inputs.")
            decisions = copy.deepcopy(preserve_rule_edits(decisions, previous.effective_rules))
            await run.io_bound(validate_preserved_rules, job, decisions)
            if self.closed or version != self.version or rule_version != self.rule_revision or token != self.review_token():
                return
            if stamps(job.sources) != snapshot:
                raise ReviewError("Rule source files changed. Apply again.")
            review = self.get_review()
            if review.state.source_name is None or (not review.state.source_suggestions
                    and review.state.metadata.get("nicegui_generation_binding") != binding):
                metadata = dict(annotators=list(job.policy.annotators), id_prefix=job.policy.id_prefix,
                                id_feature=job.policy.id_feature, nicegui_generation_binding=binding, target_view=job.settings.target_view)
                review.publish_generated(load_suggestions_preview(sanitization_suggestions_json_text([], metadata=metadata).encode(), "rule-only-review.json"))
            elif review.state.metadata.get("nicegui_generation_binding") != binding:
                raise ReviewError("Load generated suggestions for the current project/scope before applying rules. Existing review unchanged.")
            review.controls.session.stage_rules(decisions, binding)
            self.rule_job, self.rule_stamps = job, snapshot
            review.controls.refresh()
            self.status.set_text(f"{len(decisions)} rule decisions staged in tab 3; Save choices commits them. Manual conflicts block Save/export until resolved.")
        except ReviewError as error:
            if not self.closed:
                self.status.set_text(str(error))
        except Exception:
            if not self.closed and version == self.version:
                self.status.set_text("Rule scan failed. Check definitions, active existing targets, policy override and shared inputs. Review unchanged.")
        finally:
            self.busy = False
            if not self.closed:
                self.refresh()

    def clear_rules(self):
        review = self.get_review()
        if review is not None:
            review.clear_rules()

    async def validate_rules_current(self):
        from nicegui import run
        session = self.get_review().controls.session
        if not session.effective_rules or session.active_rule_binding is None:
            return  # Imported rules retain their existing read-only semantics.
        if session.invalid_rules or self.rule_job is None:
            raise ReviewError("Rule inputs changed. Apply rules again or clear them before exporting.")
        try:
            current = await run.io_bound(stamps, self.rule_job.sources)
            if current != self.rule_stamps:
                raise ValueError()
        except (OSError, ValueError):
            session.rules_stale = session.draft_rules_stale = True
            self.get_review().controls.refresh()
            raise ReviewError("Rule source files changed. Apply rules again or clear them before exporting.") from None

    async def inspect_snogit(self):
        from nicegui import run
        source = self.snogit_source.snapshot()
        if source is None or self.busy or self.closed:
            return
        version = self.version
        self.busy = True
        self.refresh()
        try:
            members, stamp = await run.io_bound(inspect_members, source)
            if self.closed or version != self.version:
                return
            self.members.set_options([member.name for member in members], value=[member.name for member in members if member.recommended_default])
            self.member_stamp = (source.path, stamp)
            self.status.set_text("SNOGIT members loaded. Cache creation is a separate explicit action.")
        except Exception:
            if not self.closed:
                self.status.set_text("Could not inspect SNOGIT. Choose a supported SNOGIT ZIP or named .dat file.")
        finally:
            self.busy = False
            if not self.closed:
                self.refresh()

    async def build_cache(self):
        from nicegui import run
        source, lists = self.snogit_source.snapshot(), self.policy.lists.snapshot()
        if self.closed or self.busy or source is None or lists is None or not self.members.value:
            return
        version, members = self.version, tuple(self.members.value)
        self.busy = True
        self.status.set_text("Creating processed SNOGIT cache… Generation will not start automatically.")
        self.refresh()
        try:
            if self.member_stamp != (source.path, source.stamp()):
                raise ValueError("Inspect current members first.")
            cache = await run.io_bound(create_cache, lists, source, members)
            if self.closed or version != self.version:
                return
            self.created_cache = cache
            self.created_caches.append(cache)  # Keep already-issued file-download URLs valid for this page.
            self.changed()
            self.status.set_text("Processed cache ready. Download it to retain it after leaving this page. Generate suggestions separately.")
        except Exception:
            if not self.closed:
                self.status.set_text("Cache creation failed. Check source members and main HDF5. Existing cache unchanged.")
        finally:
            self.busy = False
            if not self.closed:
                self.refresh()

    async def download_cache(self):
        if not self.closed and not self.busy and self.created_cache is not None:
            self.ui.download.file(self.created_cache.path, filename="snogit-cache.hdf5")

    def close(self):
        self.closed = True
        self.revision += 1
        self.artifact_revision += 1
        for source in (self.custom, self.cache, self.snogit_source):
            source.close()
        self.completed = self.created_cache = self.rule_job = None
        self.created_caches.clear()
        if self.shared_changed in self.policy.listeners:
            self.policy.listeners.remove(self.shared_changed)
        if self.policy_result_changed in self.policy.result_listeners:
            self.policy.result_listeners.remove(self.policy_result_changed)
