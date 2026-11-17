"""Read-only schema-v2 annotation-store adapter for the existing corpus engine."""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3

import numpy as np

from .uima_processing.extraction import spans_match
from .uima_processing.models import DocumentAnnotations, IgnoreOverlap, TemporaryContainer, TemporaryCorpus
from .uima_processing.scope import normalize_annotators


class AnnotationStoreError(ValueError):
    """A fixed, user-safe annotation-store validation message."""


def is_annotation_store(path):
    try:
        with Path(path).open("rb") as stream:
            return stream.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


@contextmanager
def _connect(path):
    path = Path(path).resolve()
    wal = Path(str(path) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise AnnotationStoreError("Use a closed, checkpointed SQLite snapshot, not a live WAL database.")
    before = path.stat()
    connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        if connection.execute("PRAGMA user_version").fetchone()[0] != 2:
            raise AnnotationStoreError("Only annotation-store schema v2 is supported; no migration is performed.")
        yield connection
    except sqlite3.DatabaseError as error:
        raise AnnotationStoreError("Invalid annotation-store schema or data.") from error
    finally:
        connection.close()
    after = path.stat()
    if wal.exists() and wal.stat().st_size:
        raise AnnotationStoreError("Use a closed, checkpointed SQLite snapshot, not a live WAL database.")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise AnnotationStoreError("Annotation store changed while reading. Use an unchanged snapshot.")


def store_scopes(path):
    """Metadata-only export/view choices; combined scopes remain ambiguity-checked."""
    with _connect(path) as connection:
        rows = connection.execute("""SELECT DISTINCT v.export_id, v.view_kind, e.filename
            FROM annotation_views v JOIN exports e ON e.id=v.export_id
            ORDER BY v.export_id, v.view_kind""").fetchall()
    kinds = sorted({row["view_kind"] for row in rows})
    options = {f"*:{kind}": f"All exports · {kind}" for kind in kinds}
    if len(kinds) > 1:
        options = {"*:*": "All exports · all views (unambiguous identities required)", **options}
    if len({row["export_id"] for row in rows}) > 1:
        options.update({f"{row['export_id']}:{row['view_kind']}":
                        f"Export {row['export_id']} · {row['filename']} · {row['view_kind']}" for row in rows})
    return options


def default_store_scope(options):
    combined = [key for key in options if key.startswith("*:") and key != "*:*"]
    return combined[0] if len(combined) == 1 else None


def _views(connection, scope, annotators, *, validate_identity=True):
    rows = connection.execute("""SELECT v.*, d.document_name FROM annotation_views v
        LEFT JOIN documents d ON d.id=v.document_id ORDER BY v.id""").fetchall()
    kinds = {row["view_kind"] for row in rows}
    if scope is None:
        if len(kinds) != 1:
            raise AnnotationStoreError("Select an annotation-store export/view scope first.")
        scope = f"*:{next(iter(kinds))}"
    export, separator, kind = scope.partition(":")
    if not separator or (export != "*" and not export.isdecimal()):
        raise AnnotationStoreError("Invalid annotation-store scope.")
    rows = [row for row in rows if kind in ("*", row["view_kind"]) and (export == "*" or row["export_id"] == int(export))]
    if not rows:
        raise AnnotationStoreError("Selected annotation-store scope has no views.")
    names = normalize_annotators(annotators or ())
    rows = [row for row in rows if not names or row["annotator"].strip().lower() in names]
    seen = set()
    for row in rows:
        if row["document_name"] is None:
            raise AnnotationStoreError("An annotation view has no document identity.")
        key = row["document_name"], row["annotator"].strip().lower()
        if key in seen and validate_identity:
            raise AnnotationStoreError("Multiple views share a document/annotator identity. Select a single export instead of all exports.")
        seen.add(key)
    return rows


def store_annotators(path, scope=None):
    with _connect(path) as connection:
        return {row["annotator"] for row in _views(connection, scope, (), validate_identity=False)}


@dataclass
class StoreData:
    corpus: TemporaryCorpus
    document_texts: dict[str, str]


def read_annotation_store(path, *, store_scope=None, annotator_filter=None,
                          annotation_types=None, ignore_overlap_types=None, ignore_overlap_mode="overlap"):
    layers = tuple(annotation_types or ("gemtex.Concept",))
    ignore_layers = tuple(ignore_overlap_types or ())
    spans_match((0, 1), (0, 1), ignore_overlap_mode)  # Validate even if there are no annotations.
    corpus, texts = TemporaryCorpus({}), {}
    with _connect(path) as connection:
        views = _views(connection, store_scope, annotator_filter)
        available = set()
        for view in views:
            document, annotator = view["document_name"], view["annotator"]
            text_row = connection.execute("SELECT text FROM document_texts WHERE id=? AND document_hash_id=?",
                                          (view["document_text_id"], view["document_hash_id"])).fetchone()
            text = text_row[0] if text_row is not None else None
            if text is not None:
                if not isinstance(text, str):
                    raise AnnotationStoreError("Invalid stored document text.")
                if document in texts and texts[document] != text:
                    raise AnnotationStoreError("Selected views contain conflicting text for the same document name.")
                texts[document] = text
            rows = connection.execute("""SELECT a.* FROM annotation_occurrence_links l
                LEFT JOIN annotations a ON a.id=l.annotation_id WHERE l.view_id=? ORDER BY l.id""", (view["id"],)).fetchall()
            available.update(row["layer"] for row in rows)
            for row in rows:
                if row["id"] is None:
                    raise AnnotationStoreError("An annotation occurrence has no annotation payload.")
                if row["document_hash_id"] != view["document_hash_id"] or row["begin_offset"] < 0 or row["end_offset"] < row["begin_offset"]:
                    raise AnnotationStoreError("Invalid annotation occurrence identity or offsets.")
                if text is not None and (row["end_offset"] > len(text) or
                                             (row["covered_text"] is not None and text[row["begin_offset"]:row["end_offset"]] != row["covered_text"])):
                    raise AnnotationStoreError("Stored annotation offsets/covered text disagree with document text.")
            ignores = [IgnoreOverlap(row["layer"], (row["begin_offset"], row["end_offset"]), row["covered_text"] or "")
                       for row in rows if row["layer"] in ignore_layers]
            targets = [row for row in rows if row["layer"] in layers]
            overlaps = [[ignore for ignore in ignores if spans_match((row["begin_offset"], row["end_offset"]), ignore.offset, ignore_overlap_mode)]
                        for row in targets]
            codes = [str(row["sctid"]).strip() if row["sctid"] is not None else "nan" for row in targets]
            annotations = DocumentAnnotations(
                np.asarray(codes, dtype="bytes"),
                np.asarray([(row["begin_offset"], row["end_offset"]) for row in targets], dtype="i,i"),
                np.asarray([row["covered_text"] or "" for row in targets], dtype=np.dtypes.StringDType),
                np.asarray([row["layer"] for row in targets], dtype=np.dtypes.StringDType), len(targets),
                np.asarray([bool(items) for items in overlaps], dtype=bool), overlaps)
            container = corpus.annotators.setdefault(annotator, TemporaryContainer(0, {}))
            container.documents[document] = annotations
            container.max_length = max(container.max_length, len(document))
        if any(layer not in available for layer in ignore_layers):
            raise AnnotationStoreError("A requested ignore-overlap layer is unavailable in the selected annotation-store scope.")
    return StoreData(corpus, texts)
