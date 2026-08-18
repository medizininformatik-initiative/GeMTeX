"""Reusable Click option decorators."""

from __future__ import annotations

import pathlib

import click

from ..sanitization import (
    DEFAULT_ALLOWED_ASSOCIATION_TYPES,
    SUPPORTED_ASSOCIATION_TYPES,
    format_association_type_descriptions,
)
from ..snomed import DumpMode, FilterMode
from .types import ClickEnumChoice, ClickUnion


def click_server_options(fnc):
    fnc = click.option(
        "--use-secure_protocol", is_flag=True, help="Whether to use 'https'."
    )(fnc)
    fnc = click.option(
        "--port",
        default=8080,
        help="Port on which the Snowstorm/INCEpTION instance runs.",
    )(fnc)
    fnc = click.option(
        "--ip",
        default="localhost",
        help="The IP address of the Snowstorm/INCEpTION instance.",
    )(fnc)
    return fnc


def click_inception_client_options(fnc):
    fnc = click.option(
        "--inception-project",
        default=None,
        help="The name of the INCEpTION project (URL slug).",
    )(fnc)
    fnc = click.option(
        "--inception-password",
        default=None,
        help="The username for the INCEpTION client (needs to have REMOTE role).",
    )(fnc)
    fnc = click.option(
        "--inception-username",
        default=None,
        help="The username for the INCEpTION client (needs to have REMOTE role).",
    )(fnc)
    return fnc


def click_log_level(fnc):
    fnc = click.option(
        "--log-level",
        default="INFO",
        type=click.Choice(
            ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False
        ),
        help="The log level.",
    )(fnc)
    return fnc


def common_click_args(fnc):
    fnc = click.argument("root_code", default="138875005")(fnc)
    return fnc


def log_documents_options(fnc):
    """Apply options for the log-critical-documents command."""
    fnc = click.option(
        "--ignore-overlap-mode",
        default="overlap",
        show_default=True,
        type=click.Choice(["overlap", "covered-by", "contains", "exact"], case_sensitive=False),
        help="How target annotations must match ignore-overlap annotations to be ignored.",
    )(fnc)
    fnc = click.option(
        "--ignore-overlap-type",
        multiple=True,
        default=("webanno.custom.No_Human",),
        show_default=True,
        help="Annotation layer/type whose overlapping spans suppress faulty-code findings on target annotations. Can be provided multiple times.",
    )(fnc)
    fnc = click.option(
        "--annotation-type",
        multiple=True,
        default=("gemtex.Concept", "webanno.custom.Concept"),
        show_default=True,
        help="Target annotation layer/type to check for SNOMED CT codes. Can be provided multiple times.",
    )(fnc)
    fnc = click.option(
        "--forbid-prompt",
        is_flag=True,
        help="Forbids prompting the user to select the annotators to log manually (instead of all). Use this flag for e.g. 'docker', when you don't want to mess with providing prompt answers.",
    )(fnc)
    fnc = click.option(
        "--omit-dump",
        is_flag=True,
        help="Omits the creation of a dump of all concepts in the project and their respective offsets (if not omitted, it is saved alongside the log file).",
    )(fnc)
    fnc = click.option(
        "--keep-export",
        is_flag=True,
        help="Keeps the temporary exported INCEpTION project (when using client) after processing.",
    )(fnc)
    fnc = click_log_level(fnc)
    fnc = click_inception_client_options(fnc)
    fnc = click_server_options(fnc)
    fnc = click.option(
        "--lists-path",
        default=None,
        help="The path to the lists file in 'hdf5' format. (default: default lists are used)",
    )(fnc)
    fnc = click.argument("process_path", type=click.STRING)(fnc)
    return fnc


def create_concept_id_dump_options(fnc):
    """Apply options for the create-concepts-dump command."""
    fnc = click_log_level(fnc)
    fnc = click.option(
        "--memoize-ancestors",
        is_flag=True,
        help="Use memoization when computing the compact ancestor/distance HDF5 extension. Disabled by default.",
    )(fnc)
    fnc = click.option(
        "--force-overwrite-concepts",
        is_flag=True,
        help="If this flag is set, an existing /concepts HDF5 extension will be rebuilt. Independent from --force-overwrite.",
    )(fnc)
    fnc = click.option(
        "--force-overwrite",
        is_flag=True,
        help="If this flag is set, the selected whitelist/blacklist HDF5 group will be overwritten.",
    )(fnc)
    fnc = click.option(
        "--not-recursive",
        is_flag=True,
        help="If this flag is set, the codes will not be resolved recursively and only the first level children will be returned.",
    )(fnc)
    fnc = click.option(
        "--filter-mode",
        default=FilterMode.POSITIVE,
        type=ClickEnumChoice(FilterMode),
        help="'positive': only concepts with specified codes/tags will be returned; 'negative': vice versa concepts with specified codes/tags will not be returned",
    )(fnc)
    fnc = click.option(
        "--filter-list",
        "-fl",
        default=None,
        type=ClickUnion((click.STRING, "str"), (click.File, "file")),
        multiple=True,
        help="When \"dump-mode == 'semantic'\", either multiple arguments of codes (or semantic tags) or a file that contains a code (semantic tag) per line.",
    )(fnc)
    fnc = click.option(
        "--dump-mode",
        default=DumpMode.VERSION,
        type=ClickEnumChoice(DumpMode),
        help="Whether to whitelist ('version') or blacklist ('semantic') a code dump.",
    )(fnc)
    fnc = click.option(
        "--branch",
        default=0,
        type=ClickUnion((click.INT, "int"), (click.STRING, "str")),
        help="The branch (i.e. Release Version) of SNOMED on the server. Defaults to the first one found.",
    )(fnc)
    fnc = click.option(
        "--ip",
        default=None,
        help="Snowstorm IP/host. Required together with --port when --zip is not used.",
    )(fnc)
    fnc = click.option(
        "--port",
        default=None,
        type=click.INT,
        help="Snowstorm port. Required together with --ip when --zip is not used.",
    )(fnc)
    fnc = click.option(
        "--use-secure_protocol", is_flag=True, help="Whether to use 'https' for Snowstorm mode."
    )(fnc)
    fnc = click.option(
        "--write-legacy-policy-groups",
        is_flag=True,
        help="In RF2 ZIP mode, additionally write legacy /whitelist or /blacklist groups for older code.",
    )(fnc)
    fnc = click.option(
        "--rf2-view",
        default="snapshot",
        show_default=True,
        type=click.Choice(["snapshot", "full"], case_sensitive=False),
        help="RF2 release view to ingest from the ZIP.",
    )(fnc)
    fnc = click.option(
        "--policy-date",
        default=None,
        help="Policy date as YYYYMMDD for RF2 ZIP mode. Snapshot mode requires this to equal the Snapshot release date; Full mode reconstructs state at or before this date.",
    )(fnc)
    fnc = click.option(
        "--include-ancestors",
        is_flag=True,
        help="In RF2 ZIP mode, compute compact ancestor arrays under /concepts. Historical associations are included by default.",
    )(fnc)
    fnc = click.option(
        "--language",
        default="en",
        show_default=True,
        help="RF2 description language used in ZIP mode, e.g. 'en'.",
    )(fnc)
    fnc = click.option(
        "--output",
        default=None,
        type=click.Path(dir_okay=False, path_type=pathlib.Path),
        help="Output HDF5 path for RF2 ZIP mode. Defaults to data/gemtex_snomedct_codes_<release-date>.hdf5 when the date can be inferred.",
    )(fnc)
    fnc = click.option(
        "--zip",
        "rf2_zip",
        default=None,
        type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
        help="Path to a SNOMED CT RF2 release ZIP. If provided, HDF5 is generated from the release ZIP instead of Snowstorm.",
    )(fnc)
    fnc = common_click_args(fnc)
    return fnc


def suggest_sanitization_options(fnc):
    """Apply options for the suggest-sanitization command."""
    fnc = click_log_level(fnc)
    fnc = click.option(
        "--ancestor-max-relative-distance",
        default=0.35,
        show_default=True,
        type=float,
        help=(
            "Maximum relative is-a distance for ancestor fallback suggestions "
            "(distance divided by source depth-to-root). Use a negative value to disable."
        ),
    )(fnc)
    fnc = click.option(
        "--ancestor-max-distance",
        default=3,
        show_default=True,
        type=int,
        help=(
            "Maximum absolute is-a distance for active/historical ancestor fallback "
            "suggestions. Use a negative value to disable."
        ),
    )(fnc)
    fnc = click.option(
        "--activate-historical-ancestor-fallback",
        is_flag=True,
        help=(
            "After historical associations fail for whitelist findings, try nearest active "
            "policy-acceptable ancestors first from active ancestor arrays, then through "
            "stored inactive is-a fallback edges."
        ),
    )(fnc)
    fnc = click.option(
        "--bm25-max-candidates",
        default=5,
        show_default=True,
        type=int,
        help="Maximum BM25 fallback candidates retained internally per finding.",
    )(fnc)
    fnc = click.option(
        "--bm25-min-lexical-score",
        default=0.15,
        show_default=True,
        type=float,
        help="Minimum query-token overlap ratio required for semantic BM25 fallback suggestions.",
    )(fnc)
    fnc = click.option(
        "--bm25-min-score",
        default=1.5,
        show_default=True,
        type=float,
        help="Minimum BM25 score required for semantic BM25 fallback suggestions.",
    )(fnc)
    fnc = click.option(
        "--blacklist-suggestions",
        is_flag=True,
        help="Allow suggestion-only BM25 replacement suggestions for blacklist findings. Requires --semantic-bm25-fallback.",
    )(fnc)
    fnc = click.option(
        "--semantic-bm25-fallback",
        is_flag=True,
        help="Use semantic BM25 for unresolved whitelist findings as fallback.",
    )(fnc)
    fnc = click.option(
        "--association-type",
        multiple=True,
        default=DEFAULT_ALLOWED_ASSOCIATION_TYPES,
        show_default=True,
        type=click.Choice(SUPPORTED_ASSOCIATION_TYPES, case_sensitive=False),
        help="Historical association type allowed for sanitization suggestions. Can be provided multiple times. Meanings: "
        + format_association_type_descriptions().replace("\n", " "),
    )(fnc)
    fnc = click.option(
        "--output",
        required=True,
        type=click.Path(dir_okay=False, path_type=pathlib.Path),
        help="Output Markdown path for sanitization suggestions.",
    )(fnc)
    fnc = click.option(
        "--critical-findings",
        required=True,
        type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
        help="Path to the CriticalFindings JSON produced by log-critical-documents.",
    )(fnc)
    fnc = click.option(
        "--lists-path",
        required=True,
        type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
        help="Path to the sanitization-ready HDF5 policy file.",
    )(fnc)
    return fnc
