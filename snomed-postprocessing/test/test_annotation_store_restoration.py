"""Synthetic-only CAS preservation, deduplication and offline deployment checks."""
from collections import Counter
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import zipfile
import zlib

import cassis
import h5py
import numpy as np
import pytest
from click.testing import CliRunner

from snomed_post_processing.annotation_source import AnnotationStoreError
from snomed_post_processing.annotation_store.cas_views import iter_cas_views
from snomed_post_processing.annotation_store.restoration import cas_restoration_status, restore_annotation_store_cas
from snomed_post_processing.cli.app import build_annotation_store_cli, restore_annotation_store_cas_cli
from snomed_post_processing.pipelines.annotation_store import run_build_annotation_store
from snomed_post_processing.pipelines.inception_apply_upload import apply_decisions_and_upload_to_inception
from snomed_post_processing.pipelines.policy_check import check_policy, PolicySettings
from snomed_post_processing.pipelines.sanitization_run import run_sanitization
from snomed_post_processing.sanitization.decisions_json import read_sanitization_decisions_json, write_sanitization_decisions_json

FIXTURE = Path(__file__).parent / 'projects' / 'synthetic-annotator-scope'


@pytest.fixture
def inputs(tmp_path):
    hdf5 = tmp_path / 'policy.hdf5'
    shutil.copyfile(FIXTURE / 'policy.hdf5', hdf5)
    # The toy policy omits builder-only semantic-tag datasets. Augment a temporary copy.
    with h5py.File(hdf5, 'a') as file:
        concepts = file['concepts']
        tags = [fsn.rsplit('(', 1)[-1].rstrip(')') for fsn in concepts['fsn'].asstr()[:]]
        unique = sorted(set(tags))
        concepts.create_dataset('semantic_tags', data=unique, dtype=h5py.string_dtype())
        concepts.create_dataset('semantic_tag_id', data=np.asarray([unique.index(tag) for tag in tags], dtype='int64'))
    return hdf5


def build(tmp_path, hdf5, *, store_cas=True, projects=None, name='store.sqlite', append=False):
    output = tmp_path / name
    summary = run_build_annotation_store(
        input_paths=projects or [FIXTURE / 'project.zip'], snomed_hdf5=hdf5, output=output,
        annotation_type=('webanno.custom.Concept',), id_prefix='http://snomed.info/id/',
        replace=False, append=append, store_document_text=False, site=None, batch_index=None,
        batch_total=None, fail_fast=True, report=None, log_level='ERROR', log_summary=False,
        store_cas=store_cas)
    return output, summary


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def altered_project(tmp_path, name, changes, *, remove=()):
    output = tmp_path / name
    with zipfile.ZipFile(FIXTURE / 'project.zip') as original, zipfile.ZipFile(output, 'w') as archive:
        for member in original.namelist():
            if member not in remove and member not in changes:
                archive.writestr(member, original.read(member))
        for member, data in changes.items():
            archive.writestr(member, data)
    return output


def test_opt_in_preserves_raw_cas_and_references_one_typesystem(tmp_path, inputs):
    path, summary = build(tmp_path, inputs)
    assert summary.preserved_cas_views == 6
    assert summary.preserved_type_systems == 1
    assert summary.annotation_occurrences == 14
    with closing(sqlite3.connect(path)) as connection, zipfile.ZipFile(FIXTURE / 'project.zip') as original:
        rows = connection.execute('SELECT v.cas_path,r.payload_hash,r.typesystem_hash FROM annotation_views v JOIN cas_restore_views r ON r.view_id=v.id').fetchall()
        digest = hashlib.sha256(original.read('TypeSystem.xml')).hexdigest()
        assert {row[2] for row in rows} == {digest}
        assert connection.execute('SELECT count(*) FROM cas_restore_blobs WHERE hash=?', (digest,)).fetchone()[0] == 1
        assert connection.execute('SELECT count(*) FROM document_texts').fetchone()[0] == 3
        for member, payload_hash, _ in rows:
            payload = zlib.decompress(connection.execute('SELECT data FROM cas_restore_blobs WHERE hash=?', (payload_hash,)).fetchone()[0])
            assert payload == original.read(member)


def test_restored_cas_and_policy_equal_original_and_store_unchanged(tmp_path, inputs):
    path, _ = build(tmp_path, inputs)
    before = checksum(path)
    output = tmp_path / 'restored.zip'
    result = restore_annotation_store_cas(path, output, store_scope='1:annotation')
    assert result.view_count == 6
    assert result.id_feature == 'id'
    assert result.id_prefix == 'http://snomed.info/id/'
    original = {(v.document_name, v.annotator): v for v in iter_cas_views(FIXTURE / 'project.zip')}
    restored = {(v.document_name, v.annotator): v for v in iter_cas_views(output)}
    assert original.keys() == restored.keys()
    with zipfile.ZipFile(FIXTURE / 'project.zip') as source, zipfile.ZipFile(output) as target:
        for key, old in original.items():
            new = restored[key]
            assert source.read(old.cas_path) == target.read(new.cas_path)
            assert json.loads(old.cas.to_json()) == json.loads(new.cas.to_json())
            assert Counter(a.type.name for a in old.cas.select_all()) == Counter(a.type.name for a in new.cas.select_all())
            for a, b in zip(old.cas.select('webanno.custom.Concept'), new.cas.select('webanno.custom.Concept')):
                assert (a.id, a.literal, a.note, a.begin, a.end) == (b.id, b.literal, b.note, b.begin, b.end)
    settings = PolicySettings(annotation_types=('webanno.custom.Concept',))
    assert check_policy(output, inputs, settings).findings == check_policy(FIXTURE / 'project.zip', inputs, settings).findings
    assert checksum(path) == before
    assert not Path(str(path) + '-wal').exists()
    assert not Path(str(path) + '-shm').exists()
    with pytest.raises(FileExistsError):
        restore_annotation_store_cas(path, output)


def test_different_typesystems_are_retained_and_duplicate_cas_reused(tmp_path, inputs):
    with zipfile.ZipFile(FIXTURE / 'project.zip') as source:
        ts = cassis.load_typesystem(io.BytesIO(source.read('TypeSystem.xml')))
    ts.create_type('synthetic.ExtraLayer', supertypeName='uima.tcas.Annotation')
    modified = altered_project(tmp_path, 'different.zip', {'annotation/automatic.txt/TypeSystem.xml': ts.to_xml()})
    path, summary = build(tmp_path, inputs, projects=[modified])
    assert summary.preserved_type_systems == 2
    restore_annotation_store_cas(path, tmp_path / 'different-restored.zip')
    _, repeated = build(tmp_path, inputs, projects=[modified], append=True)
    assert repeated.preserved_cas_views == 6
    assert repeated.annotation_occurrences == summary.annotation_occurrences
    second = tmp_path / 'second.zip'
    shutil.copyfile(modified, second)
    _, appended = build(tmp_path, inputs, projects=[second], append=True)
    assert appended.preserved_cas_views == 12
    assert appended.preserved_type_systems == 2
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute('SELECT count(DISTINCT payload_hash) FROM cas_restore_views').fetchone()[0] == 6
    with pytest.raises(AnnotationStoreError, match='export'):
        restore_annotation_store_cas(path, tmp_path / 'ambiguous.zip')
    restore_annotation_store_cas(path, tmp_path / 'single.zip', store_scope='1:annotation')


def test_scope_filters_restoration_and_source_metadata(tmp_path, inputs):
    path, _ = build(tmp_path, inputs)
    output = tmp_path / 'alice.zip'
    result = restore_annotation_store_cas(path, output, annotators=(' ALICE ',))
    assert result.view_count == 3
    assert {v.annotator for v in iter_cas_views(output)} == {'alice'}
    with zipfile.ZipFile(output) as archive:
        metadata = json.loads(archive.read('exportedproject.json'))
        assert {item['user'] for item in metadata['annotation_documents']} == {'alice'}
        assert not any('bob.' in name for name in archive.namelist())
    with pytest.raises(AnnotationStoreError, match='No CAS views'):
        restore_annotation_store_cas(path, tmp_path / 'empty.zip', annotators=('unknown',))


def test_existing_analysis_stores_are_not_upgraded(tmp_path, inputs):
    path, _ = build(tmp_path, inputs, store_cas=False)
    before = checksum(path)
    assert 'no preserved CAS' in cas_restoration_status(path)
    with pytest.raises(AnnotationStoreError, match='no preserved CAS'):
        restore_annotation_store_cas(path, tmp_path / 'missing.zip')
    with pytest.raises(ValueError, match='not upgraded'):
        build(tmp_path, inputs, append=True)
    assert checksum(path) == before
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name LIKE 'cas_restore_%'").fetchall() == []
    assert not (tmp_path / 'missing.zip').exists()


def test_cas_store_append_requires_explicit_opt_in_and_rejects_changed_source(tmp_path, inputs):
    project = tmp_path / 'source.zip'
    shutil.copyfile(FIXTURE / 'project.zip', project)
    path, _ = build(tmp_path, inputs, projects=[project])
    before = checksum(path)
    with pytest.raises(ValueError, match='requires --store-cas'):
        build(tmp_path, inputs, store_cas=False, append=True, projects=[project])
    with zipfile.ZipFile(project) as archive:
        metadata = json.loads(archive.read('exportedproject.json'))
    metadata['name'] = 'changed export'
    changed = altered_project(tmp_path, 'changed.zip', {'exportedproject.json': json.dumps(metadata)})
    shutil.copyfile(changed, project)
    with pytest.raises(ValueError, match='configuration changed'):
        build(tmp_path, inputs, append=True, projects=[project])
    assert checksum(path) == before


def test_missing_project_configuration_can_use_explicit_template(tmp_path, inputs):
    project = tmp_path / 'flat.zip'
    with zipfile.ZipFile(FIXTURE / 'project.zip') as source, zipfile.ZipFile(project, 'w') as archive:
        archive.writestr('TypeSystem.xml', source.read('TypeSystem.xml'))
        archive.writestr('rules.txt.json/alice.json', source.read('annotation/rules.txt/alice.json'))
    path, _ = build(tmp_path, inputs, projects=[project])
    with pytest.raises(AnnotationStoreError, match='project configuration'):
        restore_annotation_store_cas(path, tmp_path / 'missing-config.zip')
    assert not (tmp_path / 'missing-config.zip').exists()
    result = restore_annotation_store_cas(path, tmp_path / 'template.zip', project_template=FIXTURE / 'project.zip')
    assert result.view_count == 1
    assert {(view.document_name, view.annotator) for view in iter_cas_views(result.output_project)} == {('rules.txt', 'alice')}


def test_builder_replace_and_report_never_overwrite_input_aliases(tmp_path, inputs):
    runner = CliRunner()
    project = tmp_path / 'source.zip'
    shutil.copyfile(FIXTURE / 'project.zip', project)
    original = checksum(project)
    common = ['--input', str(project), '--snomed-hdf5', str(inputs), '--fail-fast']
    result = runner.invoke(build_annotation_store_cli, [*common, '--output', str(project), '--replace'])
    assert result.exit_code != 0
    assert 'must not overwrite input files' in result.output
    assert checksum(project) == original
    report_result = runner.invoke(build_annotation_store_cli, [*common, '--output', str(tmp_path / 'new.sqlite'),
                                                                '--report', str(project)])
    assert report_result.exit_code != 0
    assert checksum(project) == original
    assert not (tmp_path / 'new.sqlite').exists()
    alias = tmp_path / 'source-alias.sqlite'
    try:
        os.link(project, alias)
    except OSError:
        pytest.skip('Hard links unavailable on this filesystem')
    result = runner.invoke(build_annotation_store_cli, [*common, '--output', str(alias), '--replace'])
    assert result.exit_code != 0
    assert checksum(project) == original
    assert alias.samefile(project)


def test_writeback_and_deployment_outputs_cannot_alias_sources_or_root_scope(tmp_path, inputs):
    path, _ = build(tmp_path, inputs)
    decisions, metadata = read_sanitization_decisions_json(FIXTURE / 'staged-decisions.json')
    metadata.update(annotators=[], store_scope='1:annotation')
    decisions_path = tmp_path / 'decisions.json'
    write_sanitization_decisions_json(decisions, decisions_path, metadata=metadata)
    store_before, decisions_before = checksum(path), checksum(decisions_path)
    alias = tmp_path / 'store-output.zip'
    try:
        os.link(path, alias)
    except OSError:
        pytest.skip('Hard links unavailable on this filesystem')
    with pytest.raises(Exception, match='must not overwrite input files'):
        run_sanitization(path, decisions, alias, store_scope='1:annotation')
    assert checksum(path) == store_before and alias.samefile(path)
    output_dir = tmp_path / 'deployment'
    with pytest.raises(Exception, match='must not overwrite input files'):
        apply_decisions_and_upload_to_inception(source_project=path, decisions_path=decisions_path,
            output_dir=output_dir, shell_project=alias, store_scope='1:annotation', force=True)
    assert not output_dir.exists()
    with pytest.raises(Exception, match='must not contain input files'):
        apply_decisions_and_upload_to_inception(source_project=path, decisions_path=decisions_path,
            output_dir=output_dir, upload_artifacts_dir=tmp_path, store_scope='1:annotation', force=True)
    assert not output_dir.exists()
    with pytest.raises(Exception, match='must not overwrite input files'):
        apply_decisions_and_upload_to_inception(source_project=path, decisions_path=decisions_path,
            output_dir=output_dir, pipeline_report=decisions_path, store_scope='1:annotation', force=True)
    assert checksum(path) == store_before
    assert checksum(decisions_path) == decisions_before


def test_direct_inception_apis_reject_source_aliases_before_writing(tmp_path):
    from snomed_post_processing.pipelines.inception_deployment import deploy_inception_sanitized_project
    from snomed_post_processing.pipelines.inception_shell_project import build_inception_shell_project
    from snomed_post_processing.pipelines.inception_upload_artifacts import build_inception_upload_artifacts
    project = tmp_path / 'project.zip'
    shutil.copyfile(FIXTURE / 'project.zip', project)
    before = checksum(project)
    alias = tmp_path / 'shell.zip'
    try:
        os.link(project, alias)
    except OSError:
        pytest.skip('Hard links unavailable on this filesystem')
    with pytest.raises(Exception, match='must not overwrite input files'):
        build_inception_shell_project(project, alias, force=True)
    with pytest.raises(Exception, match='must not contain input files'):
        build_inception_upload_artifacts(project, [], tmp_path, force=True)
    assert checksum(project) == before and alias.samefile(project)

    artifact_dir = tmp_path / 'artifacts'
    artifact_dir.mkdir()
    report = artifact_dir / 'inception-upload-artifacts-report.json'
    report.write_text(json.dumps({'mode': 'flattened-documents', 'uploads': []}), encoding='utf-8')
    with pytest.raises(Exception, match='must not overwrite input files'):
        deploy_inception_sanitized_project(shell_project=project, upload_artifacts_dir=artifact_dir,
                                           deployment_report=alias)
    assert checksum(project) == before and alias.samefile(project)


def test_restoration_output_alias_never_overwrites_store_or_template(tmp_path, inputs):
    path, _ = build(tmp_path, inputs)
    before = checksum(path)
    alias = tmp_path / 'restored.zip'
    try:
        os.link(path, alias)
    except OSError:
        pytest.skip('Hard links unavailable on this filesystem')
    with pytest.raises(AnnotationStoreError, match='must not overwrite input files'):
        restore_annotation_store_cas(path, alias)
    assert checksum(path) == before and alias.samefile(path)
    template = tmp_path / 'template.zip'
    shutil.copyfile(FIXTURE / 'project.zip', template)
    template_alias = tmp_path / 'template-output.zip'
    os.link(template, template_alias)
    template_before = checksum(template_alias)
    with pytest.raises(AnnotationStoreError, match='must not overwrite input files'):
        restore_annotation_store_cas(path, template_alias, project_template=template)
    assert checksum(template_alias) == template_before


def test_corruption_and_unsafe_names_fail_before_output(tmp_path, inputs):
    path, _ = build(tmp_path, inputs)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("UPDATE cas_restore_blobs SET data=? WHERE hash=(SELECT payload_hash FROM cas_restore_views LIMIT 1)", (zlib.compress(b'not the original CAS'),))
    with pytest.raises(AnnotationStoreError, match='hash'):
        restore_annotation_store_cas(path, tmp_path / 'bad.zip')
    assert not (tmp_path / 'bad.zip').exists()
    other, _ = build(tmp_path, inputs, name='unsafe.sqlite')
    with closing(sqlite3.connect(other)) as connection, connection:
        connection.execute("UPDATE documents SET document_name='../escape' WHERE id=(SELECT min(id) FROM documents)")
    with pytest.raises(AnnotationStoreError, match='safe ZIP'):
        restore_annotation_store_cas(other, tmp_path / 'unsafe.zip')
    assert not (tmp_path / 'unsafe.zip').exists()


@pytest.mark.parametrize('users,changed,artifact_count', [((), 6, 6), (('alice',), 3, 3)])
def test_sqlite_local_writeback_and_offline_deployment(tmp_path, inputs, users, changed, artifact_count):
    path, _ = build(tmp_path, inputs)
    before = checksum(path)
    decisions, metadata = read_sanitization_decisions_json(FIXTURE / 'staged-decisions.json')
    metadata.update(annotators=list(users), store_scope='1:annotation')
    decisions_path = tmp_path / 'decisions.json'
    write_sanitization_decisions_json(decisions, decisions_path, metadata=metadata)
    local = run_sanitization(path, decisions, tmp_path / 'sanitized.zip', annotator_filter=set(users) or None,
                             id_feature='sctid', id_prefix='', store_scope='1:annotation')
    assert local.changed_annotation_count == changed
    assert not local.unmatched_decisions
    assert {view.annotator for view in iter_cas_views(local.output_project)} == {'alice', 'bob'}
    result = apply_decisions_and_upload_to_inception(source_project=path, decisions_path=decisions_path,
        output_dir=tmp_path / 'deployment', id_feature='sctid', id_prefix='')
    assert result.dry_run and not result.applied
    assert not result.deployment_result.errors
    assert result.artifacts_result.artifact_count == artifact_count
    assert sum(item.changed_annotation_count for item in result.artifacts_result.artifacts) == changed
    assert not result.artifacts_result.unmatched_decisions
    assert checksum(path) == before


def test_nested_cas_and_non_bmp_offsets_are_preserved(tmp_path, inputs):
    changes, remove = {}, []
    for view in iter_cas_views(FIXTURE / 'project.zip'):
        if view.document_name != 'rules.txt':
            continue
        cas = view.cas
        cas.sofa_string = '😀 ' + cas.sofa_string
        for annotation in cas.select_all():
            annotation.begin += 2
            annotation.end += 2
        payload = cas.to_xmi().encode('utf-8')
        nested = io.BytesIO()
        with zipfile.ZipFile(nested, 'w') as archive:
            archive.writestr('TypeSystem.xml', cas.typesystem.to_xml())
            archive.writestr('document.xmi', payload)
        member = f'annotation/rules.txt/{view.annotator}.zip'
        changes[member] = nested.getvalue()
        remove.append(view.cas_path)
    project = altered_project(tmp_path, 'nested.zip', changes, remove=remove)
    path, summary = build(tmp_path, inputs, projects=[project])
    assert summary.annotation_occurrences == 14
    result = restore_annotation_store_cas(path, tmp_path / 'restored-nested.zip')
    original = {(v.document_name, v.annotator): v for v in iter_cas_views(project)}
    for restored in iter_cas_views(result.output_project):
        old = original[(restored.document_name, restored.annotator)]
        assert old.cas.sofa_string == restored.cas.sofa_string
        assert [(a.begin, a.end, a.get_covered_text()) for a in old.cas.select_all()] == [
            (a.begin, a.end, a.get_covered_text()) for a in restored.cas.select_all()]


def test_portable_review_package_remains_deployable_after_temporary_files_are_gone(tmp_path, inputs):
    from unittest.mock import patch
    from snomed_post_processing.pipelines.store_review_package import build_store_review_package
    from snomed_post_processing.pipelines.inception_deployment import deploy_inception_sanitized_project
    from snomed_post_processing.sanitization.decisions_json import sanitization_decisions_json_text
    path, _ = build(tmp_path, inputs)
    decisions, metadata = read_sanitization_decisions_json(FIXTURE / 'staged-decisions.json')
    metadata.update(annotators=[], store_scope='1:annotation', annotation_source_file=path.name)
    text = sanitization_decisions_json_text(decisions, metadata=metadata)
    before = checksum(path)
    with patch('snomed_post_processing.pipelines.inception_deployment._pycaprio_client') as network:
        content = build_store_review_package(path, text, store_scope='1:annotation', annotators=('alice',))
        network.assert_not_called()
    directory = tmp_path / 'unpacked'
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        archive.extractall(directory)
    result = deploy_inception_sanitized_project(shell_project=directory / 'shell-project.zip', upload_artifacts_dir=directory / 'artifacts')
    assert not result.errors
    assert result.planned_upload_count == 3
    exported, scope = read_sanitization_decisions_json(directory / 'reviewed-decisions.json')
    assert scope['annotators'] == ['alice']
    assert {item['annotator'] for item in exported} == {'alice'}
    assert checksum(path) == before
    with pytest.raises(ValueError, match='SQLite scope differs'):
        build_store_review_package(path, text, store_scope='2:annotation')
    metadata['annotators'] = ['alice']
    narrow = sanitization_decisions_json_text(decisions, metadata=metadata)
    with pytest.raises(ValueError, match='narrower annotator scope'):
        build_store_review_package(path, narrow, store_scope='1:annotation')


def test_offline_package_worker_supports_windows_spawn(tmp_path, inputs):
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing
    from snomed_post_processing.pipelines.store_review_package import build_store_review_package
    from snomed_post_processing.sanitization.decisions_json import sanitization_decisions_json_text
    path, _ = build(tmp_path, inputs)
    decisions, metadata = read_sanitization_decisions_json(FIXTURE / 'staged-decisions.json')
    metadata.update(annotators=[], store_scope='1:annotation', annotation_source_file=path.name)
    text = sanitization_decisions_json_text(decisions, metadata=metadata)
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn')) as executor:
        content = executor.submit(build_store_review_package, path, text,
                                  store_scope='1:annotation', annotators=('alice',)).result(timeout=15)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert 'shell-project.zip' in archive.namelist()
        report = json.loads(archive.read('artifacts/inception-upload-artifacts-report.json'))
        assert report['artifact_count'] == 3


def test_streamlit_enables_preserved_cas_but_blocks_scope_mismatch(tmp_path, inputs):
    from streamlit.testing.v1 import AppTest
    path, _ = build(tmp_path, inputs)
    for saved_scope, blocked in (('1:annotation', False), ('2:annotation', True)):
        app = AppTest.from_string(f'''
import pathlib
import streamlit as st
from snomed_post_processing.gui.streamlit.sanitization_run_tab import _render_sanitization_run_controls
st.session_state['zip_file'] = pathlib.Path({str(path)!r})
st.session_state['sanitization_suggestions_metadata'] = {{'store_scope': {saved_scope!r}}}
_render_sanitization_run_controls([], '{{}}', selected_count=1, has_invalid_selected_rows=False, store_scope='1:annotation')
''').run()
        assert not app.exception, str(app.exception)
        assert next(widget for widget in app.button if widget.label == 'Run sanitization').disabled == blocked


def test_nicegui_review_export_cannot_retarget_store_scope():
    from snomed_post_processing.gui.nicegui.review import ReviewSession
    from snomed_post_processing.gui.nicegui.suggestions import load_suggestions_preview
    data = json.loads((FIXTURE / 'suggestions.json').read_text(encoding='utf-8'))
    data['metadata'].update(store_scope='1:annotation', annotation_source_file='current.sqlite')
    state = load_suggestions_preview(json.dumps(data).encode(), 'suggestions.json')
    session = ReviewSession(state, imported_metadata={'store_scope': '2:annotation',
                                                       'annotation_source_file': 'other.sqlite'})
    _, metadata = read_sanitization_decisions_json(io.StringIO(session.export_text()))
    assert metadata['store_scope'] == '1:annotation'
    assert metadata['annotation_source_file'] == 'current.sqlite'


def test_offline_controller_rejects_stale_download_without_nicegui_dependency(tmp_path, inputs):
    import asyncio
    from types import ModuleType, SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock, patch
    from snomed_post_processing.gui.nicegui.file_sources import SourceFile
    from snomed_post_processing.gui.nicegui.store_restoration_ui import StoreRestorationControls
    from snomed_post_processing.gui.nicegui.review import ReviewSession
    from snomed_post_processing.gui.nicegui.suggestions import load_suggestions_preview
    from snomed_post_processing.pipelines.store_review_package import build_store_review_package
    path, _ = build(tmp_path, inputs)
    data = json.loads((FIXTURE / 'suggestions.json').read_text(encoding='utf-8'))
    data['metadata'].update(store_scope='1:annotation', annotation_source_file=path.name)
    state = load_suggestions_preview(json.dumps(data).encode(), 'suggestions.json')
    project = SourceFile(path)
    shared = SimpleNamespace(is_store=True, closed=False, revision=0, listeners=[], data_dir=SimpleNamespace(value='data'),
                             project=SimpleNamespace(snapshot=lambda: project), scope=SimpleNamespace(value='1:annotation'),
                             annotators=SimpleNamespace(value=['alice']))
    review = SimpleNamespace(state=state, controls=SimpleNamespace(session=ReviewSession(state), before_export=None))
    ui = MagicMock()
    control = StoreRestorationControls(ui, shared, review)
    module = ModuleType('nicegui')
    async def inline(function, *args, **kwargs):
        return function(*args, **kwargs)
    module.run = SimpleNamespace(io_bound=AsyncMock(side_effect=inline), cpu_bound=AsyncMock(side_effect=inline))
    with patch.dict('sys.modules', {'nicegui': module}):
        asyncio.run(control.prepare())
        ui.download.content.assert_called_once()
        ui.download.content.reset_mock()
        async def stale(function, *args, **kwargs):
            result = function(*args, **kwargs)
            if function is build_store_review_package:
                shared.revision += 1
            return result
        module.run.cpu_bound.side_effect = stale
        asyncio.run(control.prepare())
        ui.download.content.assert_not_called()
        assert 'changed while preparing' in control.status.set_text.call_args.args[0]


def test_nicegui_offline_download_and_stale_review_protection(tmp_path, inputs):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch
    pytest.importorskip('nicegui')
    from nicegui import Client, ui
    from nicegui.page import page
    from snomed_post_processing.gui.nicegui.shared_inputs import SharedInputControls
    from snomed_post_processing.gui.nicegui.store_restoration_ui import StoreRestorationControls
    from snomed_post_processing.gui.nicegui.review import ReviewSession
    from snomed_post_processing.gui.nicegui.suggestions import load_suggestions_preview
    from snomed_post_processing.pipelines.store_review_package import build_store_review_package
    path, _ = build(tmp_path, inputs)
    data = json.loads((FIXTURE / 'suggestions.json').read_text(encoding='utf-8'))
    data['metadata'].update(store_scope='1:annotation', annotation_source_file=path.name)
    state = load_suggestions_preview(json.dumps(data).encode(), 'suggestions.json')

    async def scenario():
        client = Client(page('/store-restoration-test'))
        with client:
            shared = SharedInputControls(ui)
            shared.source_kind.set_value('Annotation store (SQLite)')
            shared.store.mode.set_value('Server path')
            shared.store.path.set_value(str(path))
            shared.scope.set_options({'1:annotation': 'Export 1'}, value='1:annotation')
            shared.annotators.set_options({'alice': 'Alice'}, value=['alice'])
            review = SimpleNamespace(state=state, controls=SimpleNamespace(session=ReviewSession(state), before_export=None))
            control = StoreRestorationControls(ui, shared, review)

        async def inline(function, *args, **kwargs):
            return function(*args, **kwargs)

        with client, patch('nicegui.run.io_bound', new=AsyncMock(side_effect=inline)), \
                patch('nicegui.run.cpu_bound', new=AsyncMock(side_effect=inline)), patch.object(ui.download, 'content') as download:
            await control.prepare()
            download.assert_called_once()
            assert download.call_args.args[1] == 'inception-review-package.zip'
            assert 'Prepared offline' in control.status.text

        async def changed(function, *args, **kwargs):
            result = function(*args, **kwargs)
            if function is build_store_review_package:
                shared.changed()
            return result

        with client, patch('nicegui.run.io_bound', new=AsyncMock(side_effect=changed)), \
                patch('nicegui.run.cpu_bound', new=AsyncMock(side_effect=changed)), patch.object(ui.download, 'content') as download:
            await control.prepare()
            download.assert_not_called()
            assert 'changed while preparing' in control.status.text
        control.close()
        shared.close()
        client.delete()

    asyncio.run(scenario())


def test_cli_build_and_restore(tmp_path, inputs):
    runner = CliRunner()
    path = tmp_path / 'cli.sqlite'
    result = runner.invoke(build_annotation_store_cli, ['--input', str(FIXTURE / 'project.zip'),
        '--snomed-hdf5', str(inputs), '--output', str(path), '--annotation-type', 'webanno.custom.Concept',
        '--store-cas', '--fail-fast'])
    assert result.exit_code == 0, (result.output, result.exception)
    assert 'Distinct preserved type systems: 1' in result.output
    restored = tmp_path / 'cli-restored.zip'
    result = runner.invoke(restore_annotation_store_cas_cli, ['--store', str(path), '--output', str(restored),
                                                           '--store-scope', '1:annotation', '--annotator', 'alice'])
    assert result.exit_code == 0, (result.output, result.exception)
    assert 'CAS views: 3' in result.output
    assert {view.annotator for view in iter_cas_views(restored)} == {'alice'}
