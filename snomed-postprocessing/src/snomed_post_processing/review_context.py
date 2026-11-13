"""Framework-neutral document extraction and display context for annotation review.

Accepts explicitly supplied ZIP bytes/maps/metadata only. No caching, session state,
metadata-path access, database access or network operations are performed here.
"""
from __future__ import annotations

import io
import logging
import pathlib
import zipfile
from dataclasses import dataclass, field
from typing import Any, Iterable

from .uima_processing.io import (
    _annotator_name_from_cas_path,
    _load_cas_from_zip_member,
    _load_typesystem_from_zip,
    _read_project,
    _yield_matching_files,
)
from .uima_processing.scope import annotator_in_scope, normalize_annotators

logger = logging.getLogger(__name__)
ContextKey = tuple[str, str, str, tuple[int, int]]


@dataclass
class ReviewContext:
    """Resolve ZIP document text, then saved finding snippets, then placeholders.

    Construct from already-loaded maps, or use ``from_metadata``/``from_project_zip``.
    Findings supply document, annotator, code, offset and covered_text attributes.
    Instances belong to their caller; frontends own any caching and worker dispatch.
    """

    document_texts: dict[str, str] = field(default_factory=dict)
    finding_contexts: dict[ContextKey, str] = field(default_factory=dict)

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any], *, document_texts: dict[str, str] | None = None) -> ReviewContext:
        lookup = {}
        for item in metadata.get("finding_contexts", ()) or ():
            try:
                offset = tuple(int(value) for value in item.get("offset", ()))
                if len(offset) != 2:
                    continue
                key = (str(item.get("document", "") or ""), str(item.get("annotator", "") or ""),
                       str(item.get("code", "") or ""), offset)
                context = str(item.get("context", "") or "")
            except Exception:
                continue
            if context:
                lookup[key] = context
        return cls(document_texts if document_texts is not None else {}, lookup)

    @classmethod
    def from_project_zip(cls, data: bytes, file_name: str | None = None, *, annotators=(),
                         metadata: dict[str, Any] | None = None) -> ReviewContext:
        """Extract scoped JSONCAS/XMI sofa text; invalid archives raise to the caller."""
        texts = _extract_project_document_texts(data, file_name, annotators=annotators)
        return cls.from_metadata(metadata or {}, document_texts=texts)

    def document_text(self, document: str) -> str:
        for alias in (document, _strip_known_suffix(document)):
            if alias in self.document_texts:
                return self.document_texts[alias]
        return ""

    @staticmethod
    def finding_key(finding: Any) -> ContextKey:
        offset = tuple(int(value) for value in (getattr(finding, "offset", None) or ()))
        if len(offset) != 2:
            offset = (-1, -1)
        return (str(getattr(finding, "document", "") or ""),
                str(getattr(finding, "annotator", "") or ""),
                str(getattr(finding, "code", "") or ""), offset)

    def label(self, finding: Any) -> str:
        """Display two words on either side, with the covered text in brackets."""
        text = self.document_text(str(getattr(finding, "document", "")))
        offset = getattr(finding, "offset", None)
        if text and offset and len(offset) == 2:
            return _offset_context(text, int(offset[0]), int(offset[1]))
        context = self.finding_contexts.get(self.finding_key(finding))
        if context:
            return context
        if compact_text(getattr(finding, "covered_text", ""), max_length=80):
            return "No full document context loaded."
        return "No document text context available."

    def missing_documents(self, findings: Iterable[Any]) -> list[str]:
        """Names lacking both project text and saved context; never returns clinical text."""
        return sorted({str(getattr(finding, "document", "")) for finding in findings
                       if not self.document_text(str(getattr(finding, "document", "")))
                       and not self.finding_contexts.get(self.finding_key(finding))})


def _extract_project_document_texts(project_zip_bytes: bytes, file_name: str | None, *, annotators=()) -> dict[str, str]:
    annotators = normalize_annotators(annotators)
    lookup: dict[str, str] = {}
    documents_seen = documents_loaded = cas_failures = empty_texts = 0
    with zipfile.ZipFile(io.BytesIO(project_zip_bytes)) as zip_file:
        project_documents = _read_project(zip_file, file_name or "uploaded project")
        for document_name, cas_paths in _yield_matching_files(
            project_documents, zip_file, file_name=file_name, allowed_extensions=[".json", ".xmi"],
        ):
            cas_paths = [path for path in cas_paths if annotator_in_scope(
                _annotator_name_from_cas_path(path, fallback_flat_layout=project_documents is None), annotators)]
            if not cas_paths:
                continue
            documents_seen += 1
            for cas_path in cas_paths:
                stage = "typesystem loading"
                try:
                    typesystem = _load_typesystem_from_zip(zip_file, cas_path)
                    stage = "CAS loading"
                    cas = _load_cas_from_zip_member(zip_file, cas_path, typesystem=typesystem)
                    stage = "sofa text extraction"
                    text = _cas_document_text(cas)
                except Exception:
                    cas_failures += 1
                    logger.exception("Context extraction failed during %s: document=%r, CAS member=%r",
                                     stage, document_name, cas_path)
                    continue
                if text:
                    _store_document_text_aliases(lookup, document_name, cas_path, text)
                    documents_loaded += 1
                    break
                empty_texts += 1
                logger.warning("CAS has no document text: document=%r, CAS member=%r", document_name, cas_path)
            else:
                logger.warning("No usable context found for document=%r", document_name)
    logger.warning(
        "Review context extraction summary: documents discovered=%d, loaded=%d, "
        "failed CAS attempts=%d, empty-text CAS=%d, lookup aliases=%d",
        documents_seen, documents_loaded, cas_failures, empty_texts, len(lookup),
    )
    if not documents_seen:
        logger.warning("No matching JSON/XMI documents found in the selected project ZIP; check its archive layout.")
    return lookup


def _cas_document_text(cas: Any) -> str:
    text = getattr(cas, "sofa_string", None)
    if text:
        return str(text)
    try:
        text = getattr(cas.get_sofa(), "sofaString", None)
        if text:
            return str(text)
    except Exception:
        logger.exception("Could not read sofa text from CAS via get_sofa().")
    return ""


def _store_document_text_aliases(lookup: dict[str, str], document_name: str, cas_path: str, text: str) -> None:
    path = pathlib.PurePosixPath(cas_path)
    aliases = {document_name, path.name, path.parent.name, _strip_known_suffix(document_name),
               _strip_known_suffix(path.name), _strip_known_suffix(path.parent.name)}
    for alias in aliases:
        if alias:
            lookup.setdefault(alias, text)


def _strip_known_suffix(name: str) -> str:
    for suffix in (".xmi", ".json", ".zip", ".ser"):
        if name.lower().endswith(suffix):
            return name[:-len(suffix)]
    return name


def _offset_context(text: str, begin: int, end: int, *, word_window: int = 2, char_window: int = 25) -> str:
    if begin < 0 or end < begin or begin > len(text):
        return _character_context(text, begin, end, char_window=char_window)
    end = min(end, len(text))
    left_words = text[:begin].split()
    right_words = text[end:].split()
    target = compact_text(text[begin:end], max_length=80)
    if left_words or right_words:
        left = " ".join(left_words[-word_window:])
        right = " ".join(right_words[:word_window])
        return f"… {left} [{target}] {right} …".replace("  ", " ").strip()
    return _character_context(text, begin, end, char_window=char_window)


def _character_context(text: str, begin: int, end: int, *, char_window: int) -> str:
    begin = max(0, min(begin, len(text)))
    end = max(begin, min(end, len(text)))
    left = compact_text(text[max(0, begin - char_window):begin], max_length=char_window)
    target = compact_text(text[begin:end], max_length=80)
    right = compact_text(text[end:min(len(text), end + char_window)], max_length=char_window)
    return f"… {left} [{target}] {right} …".replace("  ", " ").strip()


def compact_text(value: Any, *, max_length: int) -> str:
    """Whitespace-compacted/truncated display text; leaves the source untouched."""
    text = " ".join(str(value or "").split())
    return text if len(text) <= max_length else f"{text[:max_length - 1].rstrip()}…"
