"""Page-local manual review commands using the existing backend JSON format.

Navigation is not staging, staging is not saving, and exporting never applies CAS
changes. Imported rule/delete/manual-edit decisions are preserved and protected.
No HDF5/project is opened and no paths from metadata are followed.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
from dataclasses import dataclass, field

from .state import PreviewState

MAX_DECISIONS_BYTES = 50 * 1024 * 1024
NO_REPLACEMENT = "— no replacement selected —"


class ReviewError(ValueError):
    """Safe user-facing error which must not include uploaded contents."""


def _identity(item):
    return (item.get("document"), item.get("annotator"), item.get("layer"),
            tuple(item.get("offset", ())), item.get("source_code") or "")


def _finding_identity(row):
    return row.document, row.annotator, row.layer, tuple(row.offset or ()), row.code


def _fingerprint(state):
    from snomed_post_processing.sanitization.json_io import sanitization_suggestion_to_dict
    encoded = json.dumps([sanitization_suggestion_to_dict(item) for item in state.source_suggestions],
                         sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ReviewChoice:
    action: str
    candidate_id: str | None = None


@dataclass
class ReviewSession:
    source: PreviewState
    saved: dict = field(default_factory=dict)
    rules: list = field(default_factory=list)
    drafts: dict = field(default_factory=dict)
    reviewed_documents: set = field(default_factory=set)
    draft_reviewed: dict = field(default_factory=dict)
    imported_metadata: dict = field(default_factory=dict)
    revision: int = 0
    locally_edited: set = field(default_factory=set)

    @property
    def dirty(self):
        return bool(self.drafts or self.draft_reviewed)

    def _require_source(self):
        if self.source.is_demo:
            raise ReviewError("Load suggestions JSON before staging, importing or exporting decisions.")

    def _row(self, row_id):
        self._require_source()
        row = next((item for item in self.source.findings if item.row_id == row_id), None)
        if row is None:
            raise ReviewError("Select a finding from the current suggestions snapshot.")
        return row

    def protected(self, row):
        item = self.saved.get(row.suggestion_index, {})
        return (any(_identity(rule) == _finding_identity(row) for rule in self.rules)
                or item.get("concept_rule") or (row.suggestion_index not in self.locally_edited and (
                    item.get("manual_edit") or item.get("delete_annotation")
                    or item.get("action") in ("manual_edit", "delete", "delete_annotation", "clear_id"))))

    def stage(self, row_id, candidate_id=None, *, action=None):
        row = self._row(row_id)
        if self.protected(row):
            raise ReviewError("This imported rule, deletion or manual-edit decision is protected. Edit it in Streamlit.")
        action = action or ("replace" if candidate_id is not None else "none")
        if action not in ("replace", "none", "delete", "manual_edit") or (action != "replace" and candidate_id is not None):
            raise ReviewError("Select one review action for this finding.")
        if action == "replace":
            candidate = next((item for item in row.candidates if item.row_id == candidate_id and item.selectable), None)
            if candidate is None:
                raise ReviewError("Select a selectable candidate from this finding; context targets cannot be staged.")
        self.drafts[row_id] = ReviewChoice(action, candidate_id)
        self.revision += 1

    def proposed_candidate(self, row_id):
        row = self._row(row_id)
        matches = [candidate for candidate in row.candidates
                   if candidate.selectable and row.proposed_code and candidate.code == row.proposed_code]
        return matches[0] if len(matches) == 1 else None

    def accept_suggestion(self, row_id):
        candidate = self.proposed_candidate(row_id)
        if candidate is None:
            raise ReviewError("No unique selectable saved proposal. Choose a candidate in Selected finding and use Apply.")
        self.stage(row_id, candidate.row_id)

    def mark_document(self, row_id, reviewed):
        row = self._row(row_id)
        self.draft_reviewed[row.document] = bool(reviewed)
        self.revision += 1

    def discard(self):
        self.drafts.clear()
        self.draft_reviewed.clear()
        self.revision += 1

    def _decision(self, row, candidate_id=None, *, human=False, action=None):
        candidate = next((item for item in row.candidates if item.row_id == candidate_id and item.selectable), None)
        action = action or ("replace" if candidate else "none")
        decision = dict(suggestion_index=row.suggestion_index, document=row.document, annotator=row.annotator,
                    layer=row.layer, offset=list(row.offset or ()), source_code=row.code, covered_text=row.text,
                    action=action, apply=bool(candidate), delete_annotation=action == "delete",
                    manual_edit=action == "manual_edit", reviewed_by_human=human, valid_choice=bool(candidate),
                    resolved=bool(candidate) or action == "delete",
                    replacement_code=candidate.code if candidate else None,
                    replacement_fsn=candidate.fsn if candidate else None,
                    replacement_choice=f"{candidate.code} — {candidate.fsn}".strip() if candidate else NO_REPLACEMENT,
                    suggestion_status=row.status, review_note=row.reason)
        if candidate is not None:
            from snomed_post_processing.sanitization.json_io import candidate_to_dict
            ordinal = row.candidates.index(candidate)
            decision["manual_candidate_ordinal"] = ordinal
            decision["manual_candidate"] = candidate_to_dict(self.source.source_suggestions[row.suggestion_index].candidates[ordinal])
        return decision

    def save(self):
        self._require_source()
        # Validate the entire batch before publishing; never partially save.
        changes = {}
        for row_id, choice in self.drafts.items():
            row = self._row(row_id)
            if self.protected(row):
                raise ReviewError("A protected imported decision cannot be overwritten.")
            if choice.action == "replace" and not any(c.row_id == choice.candidate_id and c.selectable for c in row.candidates):
                raise ReviewError("A pending candidate no longer matches this finding.")
            changes[row.suggestion_index] = self._decision(row, choice.candidate_id, human=True, action=choice.action)
        # Like Streamlit's document save, human confirmation conservatively protects
        # unchanged/Keep rows in that document from later automatic conditions.
        for row in self.source.findings:
            if self.draft_reviewed.get(row.document) and not self.protected(row):
                item = copy.deepcopy(changes.get(row.suggestion_index, self.saved.get(row.suggestion_index, self._decision(row))))
                item["reviewed_by_human"] = True
                item.pop("automatic_condition", None)
                changes[row.suggestion_index] = item
        self.saved.update(changes)
        self.locally_edited.update(changes)
        automatic = set(self.imported_metadata.get("automatic_reviewed_documents", []))
        self.imported_metadata["automatic_reviewed_documents"] = sorted(automatic - set(self.draft_reviewed))
        for document, reviewed in self.draft_reviewed.items():
            if reviewed:
                self.reviewed_documents.add(document)
            else:
                self.reviewed_documents.discard(document)
        self.discard()

    def status(self, row):
        if row.row_id in self.drafts:
            choice = self.drafts[row.row_id]
            candidate = next((c for c in row.candidates if c.row_id == choice.candidate_id), None)
            return (f"Pending replacement: {candidate.code}" if candidate else
                    {"delete": "Pending deletion", "manual_edit": "Pending manual review", "none": "Pending Keep"}[choice.action])
        if self.protected(row):
            return "Protected imported decision"
        item = self.saved.get(row.suggestion_index, {})
        if item.get("delete_annotation"):
            return "Saved deletion"
        if item.get("manual_edit"):
            return "Saved manual review"
        if item.get("apply"):
            return f"Saved replacement: {item.get('replacement_code')}"
        return "Saved Keep" if item.get("reviewed_by_human") else "Unreviewed"

    def export_text(self):
        self._require_source()
        if self.dirty:
            raise ReviewError("Save choices or discard pending changes before exporting reviewed decisions.")
        from snomed_post_processing.sanitization.decisions_json import sanitization_decisions_json_text
        decisions = [copy.deepcopy(self.saved.get(row.suggestion_index, self._decision(row)))
                     for row in self.source.findings
                     if not any(_identity(rule) == _finding_identity(row) for rule in self.rules)]
        decisions.extend(copy.deepcopy(self.rules))
        # Suggestions metadata may contain full-document finding_contexts for
        # excluded annotators. Like Streamlit, carry write-back settings across,
        # not the entire suggestions metadata/clinical context into a review file.
        names = ("id_prefix", "id_feature", "manual_review_layer", "suggestions_json_path", "suggestions_report_path")
        metadata = {key: copy.deepcopy(self.source.metadata[key]) for key in names if key in self.source.metadata}
        metadata.update(copy.deepcopy(self.imported_metadata))
        if "finding_contexts" in metadata:
            from snomed_post_processing.uima_processing.scope import annotator_in_scope
            contexts = metadata["finding_contexts"]
            metadata["finding_contexts"] = [item for item in contexts if isinstance(item, dict)
                                           and annotator_in_scope(item.get("annotator", ""), self.source.source_annotators)] if isinstance(contexts, list) else []
        metadata.update(annotators=list(self.source.source_annotators),
                        document_count=len({item["document"] for item in decisions}),
                        reviewed_documents=sorted(self.reviewed_documents),
                        nicegui_suggestions_sha256=_fingerprint(self.source))
        # A manual save/flag change must not claim the document is still automatically reviewed.
        automatic = set(self.imported_metadata.get("automatic_reviewed_documents", [])) & self.reviewed_documents
        human_documents = {item["document"] for item in decisions if item.get("reviewed_by_human")}
        metadata["automatic_reviewed_documents"] = sorted(automatic - human_documents)
        for name, default in (("id_prefix", "http://snomed.info/id/"), ("id_feature", "id"),
                              ("manual_review_layer", "webanno.custom.ManualReview")):
            metadata.setdefault(name, default)
        return sanitization_decisions_json_text(decisions, metadata=metadata)


def load_review(content: bytes, state: PreviewState) -> ReviewSession:
    """Parse and validate off to the side. Caller publishes atomically after race checks."""
    session = ReviewSession(state)
    session._require_source()
    if len(content) > MAX_DECISIONS_BYTES:
        raise ReviewError("Reviewed decisions JSON exceeds the 50 MiB upload limit.")
    from snomed_post_processing.sanitization.decisions_json import read_sanitization_decisions_json
    from snomed_post_processing.uima_processing.scope import normalize_annotators, scope_covers, annotator_in_scope
    try:
        decisions, metadata = read_sanitization_decisions_json(io.StringIO(content.decode("utf-8-sig")))
        scope = metadata.get("annotators", [])
        if not isinstance(scope, list) or any(not isinstance(name, str) for name in scope):
            raise ValueError()
        if not scope_covers(normalize_annotators(scope), state.source_annotators):
            raise ReviewError("Reviewed decisions have a narrower annotator scope than these suggestions.")
        fingerprint = metadata.get("nicegui_suggestions_sha256")
        if fingerprint is not None and fingerprint != _fingerprint(state):
            raise ReviewError("Reviewed decisions do not match these suggestions. Load their matching suggestions JSON.")
        rows = {row.suggestion_index: row for row in state.findings}
        seen_rules = set()
        for raw in decisions:
            if not isinstance(raw, dict):
                raise ValueError()
            if not annotator_in_scope(raw.get("annotator", ""), state.source_annotators):
                continue
            item = copy.deepcopy(raw)
            if item.get("concept_rule"):
                identity = _identity(item)
                if not all(isinstance(item.get(key), str) for key in ("document", "annotator", "layer", "source_code")):
                    raise ValueError()
                if (len(identity[3]) != 2 or any(type(value) is not int for value in identity[3])
                        or item.get("action") not in ("replace", "clear_id") or identity in seen_rules):
                    raise ValueError()
                seen_rules.add(identity)
                session.rules.append(item)
                continue
            index = item.get("suggestion_index")
            if type(index) is not int or index not in rows or index in session.saved:
                raise ValueError()
            row = rows[index]
            if _identity(item) != _finding_identity(row) or ("covered_text" in item and item["covered_text"] != row.text):
                raise ReviewError("Reviewed decisions do not match these suggestions. Load their matching suggestions JSON.")
            if item.get("action", "none") not in ("none", "replace", "delete", "delete_annotation", "manual_edit", "clear_id"):
                raise ValueError()
            for flag in ("apply", "valid_choice", "resolved", "reviewed_by_human", "manual_edit", "delete_annotation"):
                if flag in item and type(item[flag]) is not bool:
                    raise ValueError()
            protected = item.get("manual_edit") or item.get("delete_annotation") or item.get("action") in ("delete", "delete_annotation", "manual_edit", "clear_id")
            if item.get("apply") and not protected:
                if not item.get("valid_choice") or not any(c.selectable and c.code == item.get("replacement_code") for c in row.candidates):
                    raise ReviewError("An imported replacement is not a selectable candidate in these suggestions.")
            if "manual_candidate" in item or "manual_candidate_ordinal" in item:
                from snomed_post_processing.sanitization.json_io import candidate_to_dict
                ordinal = item.get("manual_candidate_ordinal")
                candidates = state.source_suggestions[index].candidates
                if (type(ordinal) is not int or not 0 <= ordinal < len(candidates)
                        or not item.get("apply") or item.get("replacement_code") != candidates[ordinal].code
                        or json.dumps(item.get("manual_candidate"), sort_keys=True)
                        != json.dumps(candidate_to_dict(candidates[ordinal]), sort_keys=True)):
                    raise ValueError()
            session.saved[index] = item
        if any(_identity(item) in seen_rules and (item.get("apply") or item.get("manual_edit") or item.get("delete_annotation")
                                                or item.get("reviewed_by_human")) for item in session.saved.values()):
            raise ReviewError("Imported rule and manual decisions conflict. Resolve them in Streamlit before importing.")
        for key in ("reviewed_documents", "automatic_reviewed_documents"):
            if key in metadata and (not isinstance(metadata[key], list) or any(not isinstance(doc, str) for doc in metadata[key])):
                raise ValueError()
        documents = {row.document for row in state.findings} | {item["document"] for item in session.rules}
        session.reviewed_documents = set(metadata.get("reviewed_documents", [])) & documents
        session.imported_metadata = copy.deepcopy(metadata)
    except ReviewError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        raise ReviewError("Invalid or mismatched reviewed decisions JSON. Load matching suggestions first; current review unchanged.") from None
    return session
