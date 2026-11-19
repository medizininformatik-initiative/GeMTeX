"""Opt-in, content-addressed CAS preservation and offline project restoration.

CAS bytes are retained without reserialization. External type systems and project
configuration use the same SHA-256-addressed compressed blob store.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile
import zlib

import cassis


CAS_STORAGE_SQL = """
create table if not exists cas_restore_blobs(
  hash text primary key,
  data blob not null
);
create table if not exists cas_restore_projects(
  export_id integer primary key references exports(id),
  configuration_hash text references cas_restore_blobs(hash),
  properties_hash text references cas_restore_blobs(hash),
  id_prefix text not null
);
create table if not exists cas_restore_views(
  view_id integer primary key references annotation_views(id),
  payload_hash text not null references cas_restore_blobs(hash),
  typesystem_hash text not null references cas_restore_blobs(hash),
  format text not null check(format in ('json', 'xmi'))
);
"""


def has_cas_storage(connection):
    expected = {'cas_restore_blobs', 'cas_restore_projects', 'cas_restore_views'}
    names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'cas_restore_%'")}
    if names and not expected.issubset(names):
        from ..annotation_source import AnnotationStoreError
        raise AnnotationStoreError("Incomplete CAS preservation schema. Build a new store.")
    return expected.issubset(names)


def _put_blob(connection, data):
    digest = hashlib.sha256(data).hexdigest()
    if connection.execute("SELECT 1 FROM cas_restore_blobs WHERE hash=?", (digest,)).fetchone() is None:
        connection.execute("INSERT INTO cas_restore_blobs(hash,data) VALUES(?,?)", (digest, zlib.compress(data)))
    return digest


def _get_blob(connection, digest):
    from ..annotation_source import AnnotationStoreError
    row = connection.execute("SELECT data FROM cas_restore_blobs WHERE hash=?", (digest,)).fetchone()
    try:
        data = zlib.decompress(row[0]) if row is not None else None
    except (zlib.error, TypeError) as error:
        raise AnnotationStoreError("Invalid preserved CAS blob.") from error
    if data is None or hashlib.sha256(data).hexdigest() != digest:
        raise AnnotationStoreError("Preserved CAS blob is missing or its hash does not match.")
    return data


def preserve_project(connection, export_id, archive, id_prefix):
    names = set(archive.namelist())
    hashes = [(_put_blob(connection, archive.read(name)) if name in names else None)
              for name in ("exportedproject.json", "project.properties")]
    values = (*hashes, id_prefix)
    previous = connection.execute("SELECT configuration_hash,properties_hash,id_prefix FROM cas_restore_projects WHERE export_id=?", (export_id,)).fetchone()
    if previous is not None and tuple(previous) != values:
        raise ValueError("Preserved export configuration changed. Build a new store instead of appending.")
    connection.execute("INSERT OR IGNORE INTO cas_restore_projects VALUES(?,?,?,?)", (export_id, *values))


def _typesystem_bytes(archive, cas_path=None):
    names = archive.namelist()
    local = str(PurePosixPath(cas_path).parent / 'TypeSystem.xml') if cas_path else 'TypeSystem.xml'
    candidates = [local, *(name for name in names if PurePosixPath(name).name == 'TypeSystem.xml' and not name.startswith('__MACOSX/'))]
    return next((archive.read(name) for name in candidates if name in names), None)


def _cas_payload(archive, cas_path):
    """Select exactly the JSON/XMI member used by the existing nested-ZIP reader."""
    from ..uima_processing.io import _is_ignored_zip_member, _is_supported_cas_path
    if not cas_path.lower().endswith('.zip'):
        return archive.read(cas_path), PurePosixPath(cas_path).suffix.lower()[1:], None
    with zipfile.ZipFile(io.BytesIO(archive.read(cas_path))) as nested:
        members = [info.filename for info in nested.infolist() if not _is_ignored_zip_member(info)
                   and _is_supported_cas_path(info.filename, ['.json', '.xmi'])]
        if len(members) > 1:
            members = [name for name in members if not PurePosixPath(name).name.startswith('INITIAL_CAS')] or members
        member = sorted(members)[0]
        typesystem = next((nested.read(info.filename) for info in nested.infolist()
                           if not info.is_dir() and PurePosixPath(info.filename).name == 'TypeSystem.xml'), None)
        return nested.read(member), PurePosixPath(member).suffix.lower()[1:], typesystem


def preserve_cas(connection, view_id, view, archive):
    payload, format_, nested_typesystem = _cas_payload(archive, view.cas_path)
    typesystem = nested_typesystem or _typesystem_bytes(archive, view.cas_path)
    if typesystem is None:
        # JSONCAS can carry its type system inline; retain its effective definition.
        typesystem = view.cas.typesystem.to_xml().encode('utf-8')
    if format_ == 'xmi':
        # The normal analysis reader is lenient. Preservation must be restorable
        # without silently dropping types absent from an incomplete type system.
        ts = cassis.load_typesystem(io.BytesIO(typesystem))
        cassis.load_cas_from_xmi(io.BytesIO(payload), typesystem=ts, lenient=False)
    values = (_put_blob(connection, payload), _put_blob(connection, typesystem), format_)
    previous = connection.execute("SELECT payload_hash,typesystem_hash,format FROM cas_restore_views WHERE view_id=?", (view_id,)).fetchone()
    if previous is not None and tuple(previous) != values:
        raise ValueError("Preserved CAS changed. Build a new store instead of appending.")
    connection.execute("INSERT OR IGNORE INTO cas_restore_views VALUES(?,?,?,?)", (view_id, *values))


def _restoration_rows(connection, store_scope, annotators):
    from ..annotation_source import AnnotationStoreError, _views
    if not has_cas_storage(connection):
        raise AnnotationStoreError("This store has no preserved CAS. Build a new store with --store-cas.")
    views = _views(connection, store_scope, annotators)
    if not views:
        raise AnnotationStoreError("No CAS views match the selected scope.")
    exports = {view['export_id'] for view in views}
    if len(exports) != 1:
        raise AnnotationStoreError("CAS restoration requires a single export. Select an export-specific SQLite scope.")
    project = connection.execute("SELECT * FROM cas_restore_projects WHERE export_id=?", (next(iter(exports)),)).fetchone()
    if project is None:
        raise AnnotationStoreError("The selected export has no preserved project data.")
    rows = []
    for view in views:
        stored = connection.execute("SELECT * FROM cas_restore_views WHERE view_id=?", (view['id'],)).fetchone()
        if stored is None:
            raise AnnotationStoreError("Some selected views have no preserved CAS. Build a new store with --store-cas.")
        rows.append((view, stored))
    return project, rows


def cas_restoration_status(path, *, store_scope=None, annotators=()):
    """Metadata-only readiness check; returns a fixed explanation or None."""
    from ..annotation_source import AnnotationStoreError, _connect
    try:
        with _connect(path) as connection:
            _restoration_rows(connection, store_scope, annotators)
    except AnnotationStoreError as error:
        return str(error)
    return None


@dataclass(frozen=True)
class CasRestorationResult:
    output_project: Path
    view_count: int
    id_prefix: str
    id_feature: str = 'id'


def _safe_component(value):
    from ..annotation_source import AnnotationStoreError
    if not value or value in ('.', '..') or any(char in value for char in '/\\:\x00'):
        raise AnnotationStoreError("A stored document or annotator name cannot be used as a safe ZIP component.")
    return value


def restore_annotation_store_cas(path, output_project, *, store_scope=None, annotators=(), project_template=None):
    """Restore one export's selected CAS to a new JSON/XMI workspace ZIP.

    This ZIP is input to the existing shell + artifact deployment workflow, not
    a Java-serialized full-project backup. No database updates or network access.
    """
    from ..annotation_source import AnnotationStoreError, _connect
    output = Path(output_project)
    from ..utils.output_paths import guard_output_paths
    try:
        guard_output_paths((path, project_template), (output,))
    except ValueError as error:
        raise AnnotationStoreError(str(error)) from error
    if output.exists():
        raise FileExistsError("Restoration output already exists; choose a new path.")
    with tempfile.TemporaryDirectory(prefix='snomed_cas_restore_') as directory:
        staged = Path(directory) / 'restored.zip'
        with _connect(path) as connection:
            project, rows = _restoration_rows(connection, store_scope, annotators)
            config_hash = project['configuration_hash']
            properties = _get_blob(connection, project['properties_hash']) if project['properties_hash'] else None
            if project_template is not None:
                with zipfile.ZipFile(project_template) as template:
                    configuration = template.read('exportedproject.json')
                    properties = template.read('project.properties') if 'project.properties' in template.namelist() else None
            elif config_hash:
                configuration = _get_blob(connection, config_hash)
            else:
                raise AnnotationStoreError("No INCEpTION project configuration was preserved. Supply a project-template ZIP when restoring this export.")
            try:
                metadata = json.loads(configuration)
                if not isinstance(metadata, dict):
                    raise ValueError()
            except (ValueError, UnicodeError) as error:
                raise AnnotationStoreError("Invalid preserved project configuration.") from error
            names = {view['document_name'] for view, _ in rows}
            identities = {(view['document_name'], view['annotator']) for view, _ in rows}
            sources = metadata.get('source_documents', [])
            if not isinstance(sources, list):
                raise AnnotationStoreError("Invalid source document metadata in the project configuration.")
            sources = [item for item in sources if item.get('name') in names]
            existing = {item['name'] for item in sources}
            sources.extend(dict(name=name, format='text', state='ANNOTATION_IN_PROGRESS') for name in sorted(names - existing))
            metadata['source_documents'] = sources
            metadata['annotation_documents'] = [item for item in metadata.get('annotation_documents', [])
                                                if (item.get('name'), item.get('user')) in identities]
            # Do not retain unselected document identities in curation metadata.
            for key in ('curation_documents', 'curated_documents'):
                if key in metadata:
                    metadata[key] = [item for item in metadata[key] if item.get('name') in names]
            written = set()
            type_systems = {stored['typesystem_hash'] for _, stored in rows}
            text_hashes = {}
            with zipfile.ZipFile(staged, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('exportedproject.json', json.dumps(metadata, ensure_ascii=False, indent=2))
                if properties is not None:
                    archive.writestr('project.properties', properties)
                if len(type_systems) == 1:
                    archive.writestr('TypeSystem.xml', _get_blob(connection, next(iter(type_systems))))
                for view, stored in rows:
                    document, annotator = _safe_component(view['document_name']), _safe_component(view['annotator'])
                    payload = _get_blob(connection, stored['payload_hash'])
                    typesystem = _get_blob(connection, stored['typesystem_hash'])
                    ts = cassis.load_typesystem(io.BytesIO(typesystem))
                    if stored['format'] == 'json':
                        cas = cassis.load_cas_from_json(io.BytesIO(payload), typesystem=ts)
                    elif stored['format'] == 'xmi':
                        cas = cassis.load_cas_from_xmi(io.BytesIO(payload), typesystem=ts, lenient=False)
                    else:
                        raise AnnotationStoreError("Invalid preserved CAS format.")
                    expected = connection.execute('SELECT text_hash FROM document_hashes WHERE id=?', (view['document_hash_id'],)).fetchone()
                    text = cas.sofa_string
                    actual = hashlib.sha256(text.encode('utf-8')).hexdigest() if isinstance(text, str) else None
                    if expected is None or actual != expected[0]:
                        raise AnnotationStoreError("Preserved CAS text does not match its stored document hash.")
                    if document in text_hashes and text_hashes[document] != actual:
                        raise AnnotationStoreError("Selected CAS contain conflicting text for one document name.")
                    if document not in text_hashes:
                        archive.writestr(f'source/{document}', text.encode('utf-8'))
                        text_hashes[document] = actual
                    kind = 'curation' if view['view_kind'] == 'curation' else 'annotation'
                    parent = f"{kind}/{document}/{stored['typesystem_hash']}"
                    ts_member = f'{parent}/TypeSystem.xml'
                    if len(type_systems) > 1 and ts_member not in written:
                        archive.writestr(ts_member, typesystem)
                        written.add(ts_member)
                    member = f"{parent}/{annotator}.{stored['format']}"
                    if member in written:
                        raise AnnotationStoreError("Selected CAS have conflicting restored member identities.")
                    archive.writestr(member, payload)
                    written.add(member)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as destination, staged.open('rb') as source:
            shutil.copyfileobj(source, destination)
    return CasRestorationResult(output, len(rows), project['id_prefix'])


@contextmanager
def prepared_cas_project(path, *, store_scope=None, annotators=(), project_template=None,
                         id_prefix='http://snomed.info/id/', id_feature='id'):
    """Adapt preserved SQLite to existing ZIP engines, cleaning up temporary CAS."""
    from ..annotation_source import is_annotation_store
    if not is_annotation_store(path):
        yield CasRestorationResult(Path(path), 0, id_prefix, id_feature)
        return
    with tempfile.TemporaryDirectory(prefix='snomed_restored_project_') as directory:
        yield restore_annotation_store_cas(path, Path(directory) / 'restored-project.zip',
                                           store_scope=store_scope, annotators=annotators,
                                           project_template=project_template)
