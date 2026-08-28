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
    build_inception_shell_project,
    run_create_concept_id_dump,
    run_log_documents,
    run_sanitization_check,
)


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
     * build-inception-shell-project
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
        "\n * build-inception-shell-project"
        "\n * list-branches"
        "\n\nEach command has a '--help' option that provides further information, e.g. 'log-critical-documents --help'"
    )



if __name__ == "__main__":
    help_me(["--help"])
