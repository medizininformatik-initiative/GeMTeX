import logging
import pathlib
from typing import Union, Optional

import click

from ..snowstorm import build_endpoint, get_branches
from ..snomed import DumpMode, FilterMode
from ..hdf5_handling.metadata import inspect_hdf5_metadata, format_hdf5_metadata_summary
from .logging import set_log_level
from .options import (
    click_log_level,
    build_snogit_cache_options,
    click_server_options,
    create_concept_id_dump_options,
    log_documents_options,
    suggest_sanitization_options,
)
from ..sanitization import build_snogit_sidecar
from ..pipelines import (
    apply_decisions_and_upload_to_inception,
    build_inception_shell_project,
    build_inception_upload_artifacts,
    deploy_inception_sanitized_project,
    run_build_annotation_store,
    run_check_annotation_store_document,
    run_create_concept_id_dump,
    run_log_documents,
    run_sanitization_check,
)
from ..sanitization.decisions_json import read_sanitization_decisions_json


@click.command()
@log_documents_options
def log_documents(
    process_path: str,
    lists_path: Optional[str],
    ip: str,
    port: Union[int, str],
    use_secure_protocol: bool,
    inception_username: Optional[str],
    inception_password: Optional[str],
    inception_project: Optional[str],
    log_level: str,
    keep_export: bool,
    omit_dump: bool,
    forbid_prompt: bool,
    annotation_type: tuple[str, ...],
    ignore_overlap_type: tuple[str, ...],
    ignore_overlap_mode: str,
):
    """
    Analyzes an INCEpTION project zip file (if PROCESS_PATH points to a local zip file) or a particular project in an INCEpTION instance
    if ip, port, username & password, as well as the project-name are given (then PROCESS_PATH points to the folder where the project should be temporarily exported to).
    Then, it logs all documents that contain erroneous concepts according to the given filter lists in a hdf5 file ("lists-path").
    """
    run_log_documents(
        process_path=process_path,
        lists_path=lists_path,
        ip=ip,
        port=port,
        use_secure_protocol=use_secure_protocol,
        inception_username=inception_username,
        inception_password=inception_password,
        inception_project=inception_project,
        log_level=log_level,
        keep_export=keep_export,
        omit_dump=omit_dump,
        forbid_prompt=forbid_prompt,
        annotation_type=annotation_type,
        ignore_overlap_type=ignore_overlap_type,
        ignore_overlap_mode=ignore_overlap_mode,
    )

@click.command()
@create_concept_id_dump_options
def create_concept_id_dump(
    root_code: str,
    rf2_zip: Optional[pathlib.Path],
    output: Optional[pathlib.Path],
    language: str,
    include_ancestors: bool,
    policy_date: Optional[str],
    rf2_view: str,
    write_legacy_policy_groups: bool,
    use_secure_protocol: bool,
    port: Optional[int],
    ip: Optional[str],
    branch: Union[int, str],
    dump_mode: DumpMode,
    filter_list: Union[str, click.File],
    filter_mode: FilterMode,
    not_recursive: bool,
    force_overwrite: bool,
    force_overwrite_concepts: bool,
    memoize_ancestors: bool,
    log_level: str,
):
    """Create a SNOMED CT concept ID dump and store it in an HDF5 file."""
    run_create_concept_id_dump(
        root_code=root_code,
        rf2_zip=rf2_zip,
        output=output,
        language=language,
        include_ancestors=include_ancestors,
        policy_date=policy_date,
        rf2_view=rf2_view,
        write_legacy_policy_groups=write_legacy_policy_groups,
        use_secure_protocol=use_secure_protocol,
        port=port,
        ip=ip,
        branch=branch,
        dump_mode=dump_mode,
        filter_list=filter_list,
        filter_mode=filter_mode,
        not_recursive=not_recursive,
        force_overwrite=force_overwrite,
        force_overwrite_concepts=force_overwrite_concepts,
        memoize_ancestors=memoize_ancestors,
        log_level=log_level,
    )

@click.command(name="build-snogit-cache")
@build_snogit_cache_options
def build_snogit_cache_cli(
    hdf5_path: pathlib.Path,
    snogit_zip: pathlib.Path,
    output: pathlib.Path,
    snogit_member: tuple[str, ...],
    log_level: str,
):
    """Build a reusable processed SNOGIT cache HDF5."""
    set_log_level(log_level)
    result = build_snogit_sidecar(
        hdf5_path=hdf5_path,
        snogit_zip_path=snogit_zip,
        output_path=output,
        members=snogit_member or None,
    )
    click.echo(f"Processed SNOGIT cache written to: {result.output_path.resolve()}")
    click.echo("Selected member(s): " + ", ".join(result.selected_members))
    click.echo(f"Rows read: {result.rows_read:,}")
    click.echo(f"Rows kept: {result.rows_kept:,}")
    click.echo(f"Rows written: {result.rows_written:,}")
    click.echo(f"Rows skipped unknown concept: {result.rows_skipped_unknown_concept:,}")
    click.echo(f"Rows skipped policy-ineligible: {result.rows_skipped_policy:,}")
    click.echo(f"Rows skipped empty term: {result.rows_skipped_empty_term:,}")
    click.echo(f"Duplicate rows skipped: {result.duplicate_rows:,}")


@click.command(name="suggest-sanitization")
@suggest_sanitization_options
def suggest_sanitization_cli(
    lists_path: pathlib.Path,
    critical_findings: pathlib.Path,
    output: pathlib.Path,
    association_type: tuple[str, ...],
    semantic_bm25_fallback: bool,
    blacklist_suggestions: bool,
    bm25_min_score: float,
    bm25_min_lexical_score: float,
    bm25_max_candidates: int,
    use_snogit_cache: Optional[pathlib.Path],
    activate_historical_ancestor_fallback: bool,
    ancestor_max_distance: int,
    ancestor_max_relative_distance: float,
    target_view: str,
    enforce_embedded_blacklist: bool,
    custom_blacklist: Optional[pathlib.Path],
    log_level: str,
):
    """Create sanitization suggestions from a CriticalFindings JSON artifact."""
    run_sanitization_check(
        lists_path=lists_path,
        critical_findings=critical_findings,
        output=output,
        association_type=association_type,
        semantic_bm25_fallback=semantic_bm25_fallback,
        blacklist_suggestions=blacklist_suggestions,
        bm25_min_score=bm25_min_score,
        bm25_min_lexical_score=bm25_min_lexical_score,
        bm25_max_candidates=bm25_max_candidates,
        use_snogit_cache=use_snogit_cache,
        activate_historical_ancestor_fallback=activate_historical_ancestor_fallback,
        ancestor_max_distance=None if ancestor_max_distance < 0 else ancestor_max_distance,
        ancestor_max_relative_distance=(
            None if ancestor_max_relative_distance < 0 else ancestor_max_relative_distance
        ),
        target_view=target_view.lower(),
        enforce_embedded_blacklist=enforce_embedded_blacklist,
        custom_blacklist=custom_blacklist,
        log_level=log_level,
    )

@click.command(name="build-inception-shell-project")
@click.option(
    "--source-project",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
    help="Original INCEpTION full project ZIP to derive the shell from.",
)
@click.option(
    "--output-project-shell",
    required=True,
    type=click.Path(dir_okay=False, path_type=pathlib.Path),
    help="Output path for the generated shell project ZIP.",
)
@click.option("--project-name", default=None, help="Name for the sanitized shell project.")
@click.option("--project-slug", default=None, help="Slug for the sanitized shell project.")
@click.option("--project-description", default=None, help="Description for the sanitized shell project.")
@click.option(
    "--manual-review-layer",
    default="webanno.custom.ManualReview",
    show_default=True,
    help="Custom span layer added for manual-review markers.",
)
@click.option(
    "--sanitized-project-suffix",
    default="sanitized",
    show_default=True,
    help="Suffix appended to project metadata when explicit values are not supplied.",
)
@click.option(
    "--keep-source-documents",
    is_flag=True,
    help="Keep source document metadata/files in the shell ZIP. By default the shell contains schema only.",
)
@click.option("--force", is_flag=True, help="Overwrite an existing output shell ZIP.")
def build_inception_shell_project_cli(
    source_project: pathlib.Path,
    output_project_shell: pathlib.Path,
    project_name: Optional[str],
    project_slug: Optional[str],
    project_description: Optional[str],
    manual_review_layer: str,
    sanitized_project_suffix: str,
    keep_source_documents: bool,
    force: bool,
):
    """Build a bare-bones INCEpTION project ZIP carrying schema/layers."""
    result = build_inception_shell_project(
        source_project=source_project,
        output_project=output_project_shell,
        project_name=project_name,
        project_slug=project_slug,
        project_description=project_description,
        sanitized_project_suffix=sanitized_project_suffix,
        manual_review_layer=manual_review_layer,
        clear_source_documents=not keep_source_documents,
        include_source_files=keep_source_documents,
        force=force,
    )
    click.echo(f"Shell project written to: {result.output_project.resolve()}")
    click.echo(f"Project name: {result.project_name}")
    click.echo(f"Project slug: {result.project_slug}")
    click.echo(f"Layers: {result.layer_count}")
    click.echo(f"Source documents: {result.source_document_count}")
    click.echo(f"Annotation documents: {result.annotation_document_count}")
    click.echo(f"Omitted ZIP members: {result.omitted_member_count}")


@click.command(name="build-inception-upload-artifacts")
@click.option(
    "--source-project",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
    help="INCEpTION project ZIP containing JSONCAS/XMI annotation content to sanitize.",
)
@click.option(
    "--decisions",
    "decisions_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
    help="Reviewed sanitization decisions JSON.",
)
@click.option(
    "--output-dir",
    required=True,
    type=click.Path(file_okay=False, path_type=pathlib.Path),
    help="Directory where flattened sanitized CAS files and report are written.",
)
@click.option(
    "--manual-review-layer",
    default="webanno.custom.ManualReview",
    show_default=True,
    help="Manual-review marker layer name.",
)
@click.option(
    "--id-prefix",
    default="http://snomed.info/id/",
    show_default=True,
    help="SNOMED URI prefix used in CAS annotation IDs.",
)
@click.option("--force", is_flag=True, help="Allow writing into a non-empty output directory.")
@click.option(
    "--no-repair-for-remote-upload",
    is_flag=True,
    help="Write raw sanitized CAS artifacts without INCEpTION remote-upload compatibility repair.",
)
def build_inception_upload_artifacts_cli(
    source_project: pathlib.Path,
    decisions_path: pathlib.Path,
    output_dir: pathlib.Path,
    manual_review_layer: str,
    id_prefix: str,
    force: bool,
    no_repair_for_remote_upload: bool,
):
    """Build offline flattened sanitized CAS upload artifacts."""
    decisions, _ = read_sanitization_decisions_json(decisions_path)
    result = build_inception_upload_artifacts(
        source_project=source_project,
        decisions=decisions,
        output_dir=output_dir,
        id_prefix=id_prefix,
        manual_review_layer=manual_review_layer,
        force=force,
        repair_for_remote_upload=not no_repair_for_remote_upload,
    )
    click.echo(f"Artifacts written to: {result.output_dir.resolve()}")
    click.echo(f"Report written to: {result.report_path.resolve()}")
    click.echo(f"Artifacts: {result.artifact_count}")
    click.echo(f"Unmatched decisions: {len(result.unmatched_decisions)}")
    click.echo(f"Skipped decisions: {len(result.skipped_decisions)}")
    repaired_count = sum(1 for artifact in result.artifacts if artifact.remote_upload_repaired)
    issue_count = sum(artifact.remote_upload_issue_count for artifact in result.artifacts)
    click.echo(f"Remote-upload repaired artifacts: {repaired_count}")
    click.echo(f"Remaining remote-upload compatibility issues: {issue_count}")


@click.command(name="apply-decisions-to-inception")
@click.option(
    "--source-project",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
    help="Original INCEpTION full project ZIP. The file is not modified.",
)
@click.option(
    "--decisions",
    "decisions_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
    help="Reviewed sanitization decisions JSON.",
)
@click.option(
    "--output-dir",
    required=True,
    type=click.Path(file_okay=False, path_type=pathlib.Path),
    help="Directory for shell ZIP, repaired upload artifacts, and reports.",
)
@click.option("--project-name", default=None, help="Name for the sanitized INCEpTION project.")
@click.option("--project-slug", default=None, help="Slug for the sanitized INCEpTION project.")
@click.option("--project-description", default=None, help="Description for the sanitized project.")
@click.option(
    "--manual-review-layer",
    default="webanno.custom.ManualReview",
    show_default=True,
    help="Manual-review marker layer name.",
)
@click.option(
    "--id-prefix",
    default="http://snomed.info/id/",
    show_default=True,
    help="SNOMED URI prefix used in CAS annotation IDs.",
)
@click.option("--inception-url", default=None, help="INCEpTION base URL, e.g. http://localhost:8080.")
@click.option("--username", default=None, help="INCEpTION username for connection check/apply.")
@click.option("--password", default=None, help="INCEpTION password. Prefer --password-env to avoid shell history.")
@click.option("--password-env", default=None, help="Environment variable containing the INCEpTION password.")
@click.option("--annotation-user", default=None, help="User receiving flattened uploaded annotations. Defaults to --username.")
@click.option("--check-connection", is_flag=True, help="Authenticate and list projects in dry-run mode.")
@click.option("--no-verify-tls", is_flag=True, help="Disable TLS certificate verification.")
@click.option("--no-repair-for-remote-upload", is_flag=True, help="Do not persist remote-upload sentence/CAS repairs.")
@click.option("--force", is_flag=True, help="Allow writing into a non-empty output directory / overwrite shell ZIP.")
@click.option("--apply", "apply_changes", is_flag=True, help="Actually import/upload to INCEpTION. Omit for dry-run.")
def apply_decisions_to_inception_cli(
    source_project: pathlib.Path,
    decisions_path: pathlib.Path,
    output_dir: pathlib.Path,
    project_name: Optional[str],
    project_slug: Optional[str],
    project_description: Optional[str],
    manual_review_layer: str,
    id_prefix: str,
    inception_url: Optional[str],
    username: Optional[str],
    password: Optional[str],
    password_env: Optional[str],
    annotation_user: Optional[str],
    check_connection: bool,
    no_verify_tls: bool,
    no_repair_for_remote_upload: bool,
    force: bool,
    apply_changes: bool,
):
    """Run the full reviewed-decisions -> INCEpTION deployment workflow."""
    result = apply_decisions_and_upload_to_inception(
        source_project=source_project,
        decisions_path=decisions_path,
        output_dir=output_dir,
        project_name=project_name,
        project_slug=project_slug,
        project_description=project_description,
        manual_review_layer=manual_review_layer,
        id_prefix=id_prefix,
        repair_for_remote_upload=not no_repair_for_remote_upload,
        inception_url=inception_url,
        username=username,
        password=password,
        password_env=password_env,
        annotation_user=annotation_user,
        apply=apply_changes,
        check_connection=check_connection,
        verify_tls=not no_verify_tls,
        force=force,
    )
    click.echo(f"Pipeline report written to: {result.pipeline_report_path.resolve()}")
    click.echo(f"Shell project: {result.shell_project.resolve()}")
    click.echo(f"Upload artifacts: {result.upload_artifacts_dir.resolve()}")
    click.echo(f"Deployment report: {result.deployment_result.deployment_report_path.resolve()}")
    click.echo(f"Decisions: {result.decision_count}")
    click.echo(f"Artifacts: {result.artifacts_result.artifact_count}")
    click.echo(f"Remote-upload compatibility issues: {sum(a.remote_upload_issue_count for a in result.artifacts_result.artifacts)}")
    click.echo(f"Dry run: {result.dry_run}")
    click.echo(f"Applied: {result.applied}")
    click.echo(f"Planned uploads: {result.deployment_result.planned_upload_count}")
    click.echo(f"Errors: {len(result.deployment_result.errors)}")
    if result.deployment_result.errors:
        raise click.ClickException("Pipeline failed; see reports for details.")


@click.command(name="deploy-inception-sanitized-project")
@click.option(
    "--shell-project",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
    help="Sanitized INCEpTION shell project ZIP to import when --apply is used.",
)
@click.option(
    "--upload-artifacts-dir",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=pathlib.Path),
    help="Directory created by build-inception-upload-artifacts.",
)
@click.option(
    "--deployment-report",
    default=None,
    type=click.Path(dir_okay=False, path_type=pathlib.Path),
    help="Output JSON deployment report. Defaults inside --upload-artifacts-dir.",
)
@click.option("--inception-url", default=None, help="INCEpTION base URL, e.g. http://localhost:8080.")
@click.option("--username", default=None, help="INCEpTION username for connection check/apply.")
@click.option("--password", default=None, help="INCEpTION password. Prefer --password-env to avoid shell history.")
@click.option("--password-env", default=None, help="Environment variable containing the INCEpTION password.")
@click.option(
    "--annotation-user",
    default=None,
    help="User receiving flattened uploaded annotations. Defaults to --username.",
)
@click.option(
    "--check-connection",
    is_flag=True,
    help="In dry-run mode, authenticate and list projects but do not write anything.",
)
@click.option("--no-verify-tls", is_flag=True, help="Disable TLS certificate verification.")
@click.option(
    "--apply",
    "apply_changes",
    is_flag=True,
    help="Actually import the shell project and upload artifacts. Omit for dry-run.",
)
def deploy_inception_sanitized_project_cli(
    shell_project: pathlib.Path,
    upload_artifacts_dir: pathlib.Path,
    deployment_report: Optional[pathlib.Path],
    inception_url: Optional[str],
    username: Optional[str],
    password: Optional[str],
    password_env: Optional[str],
    annotation_user: Optional[str],
    check_connection: bool,
    no_verify_tls: bool,
    apply_changes: bool,
):
    """Deploy or dry-run a sanitized INCEpTION shell + flattened artifact set."""
    result = deploy_inception_sanitized_project(
        shell_project=shell_project,
        upload_artifacts_dir=upload_artifacts_dir,
        deployment_report=deployment_report,
        inception_url=inception_url,
        username=username,
        password=password,
        password_env=password_env,
        annotation_user=annotation_user,
        apply=apply_changes,
        check_connection=check_connection,
        verify_tls=not no_verify_tls,
    )
    click.echo(f"Deployment report written to: {result.deployment_report_path.resolve()}")
    click.echo(f"Dry run: {result.dry_run}")
    click.echo(f"Applied: {result.applied}")
    click.echo(f"Planned uploads: {result.planned_upload_count}")
    click.echo(f"Warnings: {len(result.warnings)}")
    click.echo(f"Errors: {len(result.errors)}")
    if result.imported_project_id is not None:
        click.echo(f"Imported project id: {result.imported_project_id}")
    if result.errors:
        raise click.ClickException("Deployment validation/apply failed; see report for details.")


@click.command(name="build-annotation-store")
@click.option(
    "--input",
    "input_paths",
    required=True,
    multiple=True,
    type=click.Path(exists=True, path_type=pathlib.Path),
    help="INCEpTION export ZIP or directory containing export ZIPs. Can be repeated.",
)
@click.option(
    "--snomed-hdf5",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
    help="HDF5 concept metadata source.",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(dir_okay=False, path_type=pathlib.Path),
    help="Output SQLite annotation-store path.",
)
@click.option(
    "--annotation-type",
    multiple=True,
    default=("gemtex.Concept",),
    show_default=True,
    help="CAS annotation layer to extract. Can be repeated.",
)
@click.option(
    "--id-prefix",
    default="http://snomed.info/id/",
    show_default=True,
    help="SNOMED URI prefix stripped from annotation IDs.",
)
@click.option("--replace", is_flag=True, help="Replace an existing output DB.")
@click.option("--append", "append", is_flag=True, help="Append to an existing output DB or create it if missing.")
@click.option(
    "--store-document-text",
    is_flag=True,
    help="Store full CAS document text in the optional document_texts table.",
)
@click.option("--site", default=None, help="Override inferred site name for all input ZIPs.")
@click.option("--batch-index", default=None, type=int, help="Override inferred batch index for all input ZIPs. Use with --batch-total.")
@click.option("--batch-total", default=None, type=int, help="Override inferred total batch count for all input ZIPs. Use with --batch-index.")
@click.option("--fail-fast", is_flag=True, help="Stop on the first malformed/unsupported CAS error.")
@click.option(
    "--report",
    default=None,
    type=click.Path(dir_okay=False, path_type=pathlib.Path),
    help="Optional JSON import summary path.",
)
@click_log_level
def build_annotation_store_cli(
    input_paths: tuple[pathlib.Path, ...],
    snomed_hdf5: pathlib.Path,
    output: pathlib.Path,
    annotation_type: tuple[str, ...],
    id_prefix: str,
    replace: bool,
    append: bool,
    store_document_text: bool,
    site: Optional[str],
    batch_index: Optional[int],
    batch_total: Optional[int],
    fail_fast: bool,
    report: Optional[pathlib.Path],
    log_level: str,
):
    """Build a SQLite store of SNOMED annotations from INCEpTION export ZIPs."""
    try:
        summary = run_build_annotation_store(
            input_paths=input_paths,
            snomed_hdf5=snomed_hdf5,
            output=output,
            annotation_type=annotation_type,
            id_prefix=id_prefix,
            replace=replace,
            append=append,
            store_document_text=store_document_text,
            site=site,
            batch_index=batch_index,
            batch_total=batch_total,
            fail_fast=fail_fast,
            report=report,
            log_level=log_level,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Annotation store written to: {output.resolve()}")
    click.echo(f"Exports processed: {summary.exports_processed}")
    click.echo(f"Documents: {summary.documents}")
    click.echo(f"Annotation views: {summary.annotation_views}")
    click.echo(f"Annotations: {summary.annotations}")
    click.echo(f"Unknown SCTIDs: {len(summary.unknown_sctids)}")
    click.echo(f"Failed CAS members: {len(summary.failed_cas_members)}")
    for item in summary.missing_batches:
        click.echo(
            f"Missing batches for {item['site']}: "
            f"found {','.join(str(v) for v in item['found'])} of {item['total']}; "
            f"missing {','.join(str(v) for v in item['missing'])}"
        )


@click.command(name="check-annotation-store-document")
@click.option(
    "--store",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
    help="SQLite annotation store created by build-annotation-store.",
)
@click.option(
    "--document",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
    help="External plain-text document to hash and look up.",
)
@click.option("--encoding", default="utf-8", show_default=True, help="Document text encoding.")
@click.option(
    "--report",
    default=None,
    type=click.Path(dir_okay=False, path_type=pathlib.Path),
    help="Optional JSON check report path.",
)
@click_log_level
def check_annotation_store_document_cli(
    store: pathlib.Path,
    document: pathlib.Path,
    encoding: str,
    report: Optional[pathlib.Path],
    log_level: str,
):
    """Check whether a document's full-text hash exists in an annotation store."""
    try:
        result = run_check_annotation_store_document(
            store=store,
            document=document,
            encoding=encoding,
            report=report,
            log_level=log_level,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Document: {document}")
    click.echo(f"SHA-256: {result.text_hash}")
    click.echo(f"In annotation store: {'yes' if result.matched else 'no'}")
    if result.matches:
        click.echo("Matches:")
        for match in result.matches:
            batch = (
                f" batch {match.batch_index}-{match.batch_total}"
                if match.batch_index is not None and match.batch_total is not None
                else ""
            )
            click.echo(
                f"- {match.site}{batch}, {match.export_file}, {match.view_kind}, "
                f"{match.annotator}: {match.annotations} annotation(s)"
            )


@click.command()
@click.argument(
    "hdf5_path",
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
)
@click.option(
    "--markdown",
    is_flag=True,
    help="Render the metadata summary as Markdown.",
)
def summarize_hdf5(hdf5_path: pathlib.Path, markdown: bool):
    """Print a concise metadata summary for a SNOMED postprocessing HDF5 file."""
    summary = inspect_hdf5_metadata(hdf5_path)
    click.echo(format_hdf5_metadata_summary(summary, markdown=markdown))


@click.command()
@click_server_options
@click_log_level
def list_branches(
    ip: str, port: Union[int, str], use_secure_protocol: bool, log_level: str
):
    """Lists all available branches on the server."""
    set_log_level(log_level)
    endpoint_builder, host = build_endpoint(ip, port, use_secure_protocol)
    path_ids, _ = get_branches(endpoint_builder, host)
    pad = len(max([str(x) for x in path_ids.get("path").keys()], key=len))
    for _id, path in path_ids.get("path").items():
        print(f"{str(_id).ljust(pad, ' ')} : {path}")


@click.command()
def help_me():
    """Please use one of the following commands:

    \b
     * log-critical-documents
     * create-concepts-dump
     * summarize-hdf5
     * build-snogit-cache
     * suggest-sanitization
     * build-annotation-store
     * check-annotation-store-document
     * build-inception-shell-project
     * build-inception-upload-artifacts
     * apply-decisions-to-inception
     * deploy-inception-sanitized-project
     * list-branches

    Each command has a '--help' option that provides further information, e.g. 'log-critical-documents --help'
    """
    print(
        "Please use one of the following commands:"
        "\n\n * log-critical-documents"
        "\n * create-concepts-dump"
        "\n * summarize-hdf5"
        "\n * build-snogit-cache"
        "\n * suggest-sanitization"
        "\n * build-annotation-store"
        "\n * check-annotation-store-document"
        "\n * build-inception-shell-project"
        "\n * build-inception-upload-artifacts"
        "\n * apply-decisions-to-inception"
        "\n * deploy-inception-sanitized-project"
        "\n * list-branches"
        "\n\nEach command has a '--help' option that provides further information, e.g. 'log-critical-documents --help'"
    )



if __name__ == "__main__":
    help_me(["--help"])
