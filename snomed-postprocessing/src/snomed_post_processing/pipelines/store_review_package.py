"""Portable, offline INCEpTION packages from reviewed SQLite-backed CAS."""
import io
import json
from pathlib import Path
import tempfile
import zipfile

from ..sanitization.decisions_json import read_sanitization_decisions_json, write_sanitization_decisions_json
from ..uima_processing.scope import annotator_in_scope, normalize_annotators, scope_covers
from .inception_apply_upload import apply_decisions_and_upload_to_inception


def build_store_review_package(store, decisions_text, *, store_scope, annotators=(), project_template=None):
    """Return a scoped shell/artifact ZIP. Never contacts INCEpTION."""
    decisions, source_metadata = read_sanitization_decisions_json(io.StringIO(decisions_text))
    scope = normalize_annotators(annotators)
    if not scope_covers(source_metadata.get('annotators', ()), scope):
        raise ValueError('Reviewed decisions cover a narrower annotator scope. Select matching inputs.')
    if source_metadata.get('store_scope') != store_scope:
        raise ValueError('SQLite scope differs from the reviewed decisions. Load matching suggestions first.')
    if source_metadata.get('annotation_source_file') not in (None, Path(store).name):
        raise ValueError('Reviewed decisions name another annotation store. Load matching suggestions first.')
    decisions = [item for item in decisions if annotator_in_scope(item.get('annotator', ''), scope)]
    keys = ('id_prefix', 'id_feature', 'manual_review_layer', 'store_scope', 'annotation_source_file', 'nicegui_generation_binding')
    metadata = {key: source_metadata[key] for key in keys if key in source_metadata}
    metadata['annotators'] = list(scope)
    with tempfile.TemporaryDirectory(prefix='snomed_store_review_') as directory:
        root = Path(directory)
        reviewed = root / 'reviewed-decisions.json'
        write_sanitization_decisions_json(decisions, reviewed, metadata=metadata)
        result = apply_decisions_and_upload_to_inception(
            source_project=Path(store), decisions_path=reviewed, output_dir=root / 'deployment',
            store_scope=store_scope, project_template=project_template, annotator_filter=scope,
            manual_review_layer=metadata.get('manual_review_layer', 'webanno.custom.ManualReview'))
        if result.deployment_result.errors:
            raise ValueError('Offline INCEpTION preparation failed; no package was produced.')
        report_path = result.artifacts_result.report_path
        report = json.loads(report_path.read_text(encoding='utf-8'))
        report.update(source_project=Path(store).name, output_dir='artifacts')
        for upload in report['uploads']:
            upload['output_path'] = Path(upload['output_path']).name
        content = io.BytesIO()
        with zipfile.ZipFile(content, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(result.shell_project, 'shell-project.zip')
            archive.write(reviewed, 'reviewed-decisions.json')
            for path in result.upload_artifacts_dir.iterdir():
                if path != report_path and path.is_file():
                    archive.write(path, f'artifacts/{path.name}')
            archive.writestr(f'artifacts/{report_path.name}', json.dumps(report, ensure_ascii=False, indent=2))
            archive.writestr('README.txt',
                'Prepared offline from preserved CAS and saved review decisions. No remote writes occurred.\n'
                'Extract this ZIP, then deploy explicitly:\n'
                'uv run deploy-inception-sanitized-project --shell-project shell-project.zip '
                '--upload-artifacts-dir artifacts --inception-url URL --username USER '
                '--password-env INCEPTION_PASSWORD --annotation-user USER --apply\n'
                'Omit --apply and connection settings for another offline validation.\n'
                'The package contains clinical text and annotations; protect it accordingly.\n')
        return content.getvalue()
