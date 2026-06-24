#!/usr/bin/env python3
"""Export INCEpTION annotations into one ZIP per document/annotator pair.

This CLI connects to an INCEpTION instance via pycaprio, exports a selected
project as XMI, and writes compact ZIP files containing only TypeSystem.xml and
one annotation XMI from annotation/.
"""

import argparse
import csv
import getpass
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, NamedTuple, Optional, Sequence, Tuple, Union, List, Set, Dict


class ProjectInfo(NamedTuple):
    project_id: int
    project_name: str


class AnnotationEntry(NamedTuple):
    zip_path: str
    document_name: str
    annotator_name: str


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export an INCEpTION project into per-document/annotator XMI ZIPs."
    )
    parser.add_argument("--host", required=True, help="INCEpTION base URL")
    parser.add_argument("--username", required=True, help="INCEpTION API username")
    parser.add_argument(
        "--password",
        help="INCEpTION API password. If omitted, INCEPTION_PASSWORD is used or an interactive prompt is shown.",
    )
    parser.add_argument("--project", help="Project id or exact/case-insensitive project name")
    parser.add_argument("--list-projects", action="store_true", help="List projects and exit")
    parser.add_argument(
        "--select-project",
        action="store_true",
        help="Prompt for a project when --project is omitted",
    )
    parser.add_argument("--output-dir", type=Path, help="Directory for generated ZIP files")
    parser.add_argument("--anonymize", action="store_true", help="Use anonymous annotator names in outputs")
    parser.add_argument("--mapping-file", type=Path, help="CSV mapping file for anonymization")
    parser.add_argument(
        "--keep-project-export",
        action="store_true",
        help="Keep the full project export ZIP in --output-dir for debugging",
    )
    parser.add_argument(
        "--verify-ssl",
        default="true",
        help="SSL verification: true, false, or path to a CA bundle (default: true)",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")
    parser.add_argument(
        "--include-annotator",
        action="append",
        default=[],
        help="Annotator to include. Repeatable. Mutually exclusive with --exclude-annotator.",
    )
    parser.add_argument(
        "--exclude-annotator",
        action="append",
        default=[],
        help="Annotator to exclude. Repeatable. Mutually exclusive with --include-annotator.",
    )
    parser.add_argument(
        "--list-annotators",
        action="store_true",
        help="Export/read selected project enough to list annotators, then exit",
    )
    parser.add_argument(
        "--select-annotators",
        action="store_true",
        help="Prompt for annotators after project export",
    )

    args = parser.parse_args(argv)
    if args.include_annotator and args.exclude_annotator:
        parser.error("--include-annotator and --exclude-annotator are mutually exclusive")
    if not args.list_projects and not args.project and not args.select_project:
        parser.error("provide --project, --select-project, or --list-projects")
    if not args.list_projects and not args.output_dir:
        parser.error("--output-dir is required unless --list-projects is used")
    return args


def parse_verify_ssl(value: str) -> Union[bool, str]:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return value


def make_client(host: str, username: str, password: str, verify_ssl: Union[bool, str]):
    try:
        from pycaprio import Pycaprio
    except ImportError as exc:
        raise RuntimeError("pycaprio is required: install it before using this CLI") from exc

    client = Pycaprio(host, (username, password))
    if verify_ssl is False:
        try:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except ImportError:
            pass
        client.api.client.session.verify = False
    elif isinstance(verify_ssl, str):
        client.api.client.session.verify = verify_ssl
    return client


def list_projects(client) -> List[ProjectInfo]:
    projects = []
    for project in client.api.projects():
        projects.append(ProjectInfo(int(project.project_id), str(project.project_name)))
    return sorted(projects, key=lambda p: (p.project_name.lower(), p.project_id))


def print_projects(projects: Sequence[ProjectInfo]) -> None:
    for project in projects:
        print(f"{project.project_id}\t{project.project_name}")


def _pyinquirer_prompt(questions):
    try:
        from PyInquirer import prompt
    except ImportError as exc:
        raise RuntimeError(
            "PyInquirer is required for interactive selection. Install dependencies with `uv sync`."
        ) from exc
    return prompt(questions)


def prompt_for_project(projects: Sequence[ProjectInfo]) -> ProjectInfo:
    if not projects:
        raise ValueError("No projects available")
    answer_name = "project_id"
    answer = _pyinquirer_prompt(
        [
            {
                "type": "list",
                "name": answer_name,
                "message": "Please choose the INCEpTION project to export:",
                "choices": [
                    {
                        "name": f"{project.project_name} ({project.project_id})",
                        "value": project.project_id,
                    }
                    for project in projects
                ],
            }
        ]
    )
    selected_id = answer.get(answer_name)
    for project in projects:
        if project.project_id == selected_id:
            return project
    raise ValueError("No project selected")


def resolve_project(projects: Sequence[ProjectInfo], project_arg: str) -> ProjectInfo:
    if project_arg.isdigit():
        project_id = int(project_arg)
        matches = [p for p in projects if p.project_id == project_id]
        if matches:
            return matches[0]
        raise ValueError(f"Project id not found: {project_arg}")

    exact_matches = [p for p in projects if p.project_name == project_arg]
    if len(exact_matches) == 1:
        return exact_matches[0]
    ci_matches = [p for p in projects if p.project_name.lower() == project_arg.lower()]
    if len(ci_matches) == 1:
        return ci_matches[0]
    if len(ci_matches) > 1:
        raise ValueError(f"Ambiguous project name: {project_arg}; use numeric project id")
    raise ValueError(f"Project not found: {project_arg}")


def export_project_xmi(client, project_id: int) -> bytes:
    try:
        data = client.api.export_project(project_id, "xmi")
    except Exception as exc:  # pycaprio/API exceptions vary by version
        raise RuntimeError(f"Failed to export project {project_id} as xmi") from exc
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if hasattr(data, "read"):
        return data.read()
    raise TypeError(f"Unexpected export payload type: {type(data)!r}")


def safe_filename(value: str) -> str:
    value = value.strip()
    value = re.sub(r'[<>:"/\\|?*]+', "_", value)
    value = re.sub(r"\s+", "_", value)
    value = value.strip("._ ")
    return value or "unnamed"


def find_typesystem(zip_file: zipfile.ZipFile) -> str:
    candidates = [
        info.filename
        for info in zip_file.infolist()
        if not info.is_dir() and info.filename.replace("\\", "/").endswith("TypeSystem.xml")
    ]
    exact = [c for c in candidates if c.replace("\\", "/") == "TypeSystem.xml"]
    if exact:
        return exact[0]
    if candidates:
        return candidates[0]
    raise ValueError("Export does not contain TypeSystem.xml")


def iter_annotation_xmis(zip_file: zipfile.ZipFile) -> Iterable[AnnotationEntry]:
    for info in zip_file.infolist():
        path = info.filename.replace("\\", "/")
        if info.is_dir() or not path.startswith("annotation/") or not path.endswith(".xmi"):
            continue
        if path.endswith("/INITIAL_CAS.xmi"):
            continue
        parts = path.split("/")
        if len(parts) < 3:
            continue
        document_name = "/".join(parts[1:-1])
        annotator_name = Path(parts[-1]).stem
        if not document_name or not annotator_name:
            continue
        yield AnnotationEntry(info.filename, document_name, annotator_name)


def discover_annotators(project_zip_path: Path) -> Set[str]:
    with zipfile.ZipFile(project_zip_path, "r") as source_zip:
        return {entry.annotator_name for entry in iter_annotation_xmis(source_zip)}


def prompt_for_annotators(annotators: Set[str]) -> Optional[List[str]]:
    ordered = sorted(annotators, key=str.lower)
    if not ordered:
        raise ValueError("No annotators available")
    if len(ordered) == 1:
        return ordered

    return_all_name = "return_all"
    return_all = _pyinquirer_prompt(
        [
            {
                "type": "confirm",
                "name": return_all_name,
                "message": "There are multiple annotators in the project. Export all of them?",
                "default": True,
            }
        ]
    )
    if return_all.get(return_all_name):
        return None

    selection_name = "annotators"
    selected = _pyinquirer_prompt(
        [
            {
                "type": "checkbox",
                "name": selection_name,
                "message": "Please choose the annotators to export:",
                "choices": [{"name": name} for name in ordered],
                "validate": lambda value: True if value else "Choose at least one annotator.",
            }
        ]
    )
    chosen = selected.get(selection_name) or []
    if not chosen:
        raise ValueError("No annotators selected")
    return chosen


def build_annotator_filter(
    available: Set[str],
    include: Optional[Sequence[str]] = None,
    exclude: Optional[Sequence[str]] = None,
    selected: Optional[Sequence[str]] = None,
) -> Optional[Set[str]]:
    include = [x for x in (include or []) if x]
    exclude = [x for x in (exclude or []) if x]
    if include and exclude:
        raise ValueError("Include and exclude annotator filters are mutually exclusive")
    if selected is not None:
        include = [x for x in selected if x]
        exclude = []

    available_by_lower = {a.lower(): a for a in available}
    available_lowers = set(available_by_lower)

    if include:
        requested = {a.lower() for a in include}
        unknown = requested - available_lowers
        if unknown:
            raise ValueError(f"Unknown annotator(s): {', '.join(sorted(unknown))}")
        if not requested:
            raise ValueError("Empty annotator selection")
        return requested

    if exclude:
        requested = {a.lower() for a in exclude}
        unknown = requested - available_lowers
        if unknown:
            raise ValueError(f"Unknown annotator(s): {', '.join(sorted(unknown))}")
        remaining = available_lowers - requested
        if not remaining:
            raise ValueError("Annotator selection would be empty")
        return remaining

    return None


def load_mapping(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    mapping = {}  # type: Dict[str, str]
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["real_annotator", "anonymous_annotator"]:
            raise ValueError(f"Invalid mapping header in {path}")
        for row in reader:
            real = row.get("real_annotator", "")
            anon = row.get("anonymous_annotator", "")
            if real and anon:
                mapping[real] = anon
    return mapping


def write_mapping(path: Path, mapping: Dict[str, str], overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Mapping file exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["real_annotator", "anonymous_annotator"])
        writer.writeheader()
        for real, anon in sorted(mapping.items(), key=lambda item: item[1]):
            writer.writerow({"real_annotator": real, "anonymous_annotator": anon})
    tmp_path.replace(path)


def get_anon_name(real_name: str, mapping: Dict[str, str]) -> str:
    if real_name in mapping:
        return mapping[real_name]
    used = set(mapping.values())
    idx = 1
    while True:
        candidate = f"annotator{idx:03d}"
        if candidate not in used:
            mapping[real_name] = candidate
            return candidate
        idx += 1


def sanitize_xmi_bytes(xmi_bytes: bytes, real_annotator: str, anonymous_annotator: str) -> bytes:
    real_bytes = real_annotator.encode("utf-8")
    anon_bytes = anonymous_annotator.encode("utf-8")
    sanitized = xmi_bytes.replace(real_bytes, anon_bytes)
    if real_bytes in sanitized:
        raise ValueError("Anonymization validation failed for an annotation XMI")
    return sanitized


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    # Stable, non-identifying metadata.
    info.date_time = (1980, 1, 1, 0, 0, 0)
    return info


def write_individual_zip(
    source_zip: zipfile.ZipFile,
    typesystem_path: str,
    entry: AnnotationEntry,
    output_dir: Path,
    anonymize: bool,
    mapping: Dict[str, str],
    overwrite: bool,
) -> Path:
    output_annotator = get_anon_name(entry.annotator_name, mapping) if anonymize else entry.annotator_name
    zip_name = f"{safe_filename(entry.document_name)}-{safe_filename(output_annotator)}.zip"
    output_zip_path = output_dir / zip_name

    if output_zip_path.exists() and not overwrite:
        raise FileExistsError(f"Output exists: {output_zip_path}")

    typesystem_bytes = source_zip.read(typesystem_path)
    xmi_bytes = source_zip.read(entry.zip_path)
    xmi_entry_name = f"{safe_filename(output_annotator)}.xmi"
    if anonymize:
        xmi_bytes = sanitize_xmi_bytes(xmi_bytes, entry.annotator_name, output_annotator)
        real_bytes = entry.annotator_name.encode("utf-8")
        if real_bytes in xmi_entry_name.encode("utf-8") or real_bytes in zip_name.encode("utf-8"):
            raise ValueError("Anonymization validation failed for output names")

    with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as out_zip:
        out_zip.writestr(_zip_info("TypeSystem.xml"), typesystem_bytes)
        out_zip.writestr(_zip_info(xmi_entry_name), xmi_bytes)
    return output_zip_path


def process_project_export(
    project_zip_path: Path,
    output_dir: Path,
    anonymize: bool = False,
    mapping_file: Optional[Path] = None,
    overwrite: bool = False,
    annotator_filter: Optional[Set[str]] = None,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    if anonymize:
        mapping_file = mapping_file or output_dir / "annotator-mapping.csv"
        mapping = load_mapping(mapping_file)
    else:
        mapping = {}

    written = []  # type: List[Path]
    seen_outputs = set()  # type: Set[Path]
    with zipfile.ZipFile(project_zip_path, "r") as source_zip:
        typesystem_path = find_typesystem(source_zip)
        entries = list(iter_annotation_xmis(source_zip))
        if not entries:
            raise ValueError("No annotation XMI files found in export")

        for entry in entries:
            if annotator_filter is not None and entry.annotator_name.lower() not in annotator_filter:
                continue
            output_annotator = get_anon_name(entry.annotator_name, mapping) if anonymize else entry.annotator_name
            candidate = output_dir / f"{safe_filename(entry.document_name)}-{safe_filename(output_annotator)}.zip"
            if candidate in seen_outputs:
                raise FileExistsError(f"Output name collision: {candidate}")
            seen_outputs.add(candidate)
            written.append(
                write_individual_zip(
                    source_zip,
                    typesystem_path,
                    entry,
                    output_dir,
                    anonymize,
                    mapping,
                    overwrite,
                )
            )

    if not written:
        raise ValueError("Annotator selection matched no annotation XMI files")

    if anonymize and mapping_file is not None:
        write_mapping(mapping_file, mapping, overwrite=True)
    return len(written)


def write_project_export(data: bytes, project_label: str, output_dir: Optional[Path], keep: bool) -> Tuple[Optional[tempfile.TemporaryDirectory], Path]:
    if keep:
        if output_dir is None:
            raise ValueError("--output-dir is required with --keep-project-export")
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{safe_filename(project_label)}-full-export.zip"
        path.write_bytes(data)
        return None, path
    tmpdir = tempfile.TemporaryDirectory()
    path = Path(tmpdir.name) / f"{safe_filename(project_label)}.zip"
    path.write_bytes(data)
    return tmpdir, path


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    password = args.password or os.environ.get("INCEPTION_PASSWORD")
    if password is None:
        password = getpass.getpass("INCEpTION password: ")

    try:
        client = make_client(args.host, args.username, password, parse_verify_ssl(args.verify_ssl))
        projects = list_projects(client)

        if args.list_projects:
            print_projects(projects)
            return 0

        project = resolve_project(projects, args.project) if args.project else prompt_for_project(projects)
        print(f"Exporting project {project.project_name} ({project.project_id}) as xmi...")
        export_bytes = export_project_xmi(client, project.project_id)
        tmpdir, project_zip_path = write_project_export(
            export_bytes, project.project_name, args.output_dir, args.keep_project_export
        )
        try:
            annotators = discover_annotators(project_zip_path)
            if not annotators:
                raise ValueError("No annotators found under annotation/")

            if args.list_annotators:
                for annotator in sorted(annotators, key=str.lower):
                    print(annotator)
                return 0

            selected = prompt_for_annotators(annotators) if args.select_annotators else None
            annotator_filter = build_annotator_filter(
                annotators,
                include=args.include_annotator,
                exclude=args.exclude_annotator,
                selected=selected,
            )
            count = process_project_export(
                project_zip_path,
                args.output_dir,
                anonymize=args.anonymize,
                mapping_file=args.mapping_file or (args.output_dir / "annotator-mapping.csv" if args.anonymize else None),
                overwrite=args.overwrite,
                annotator_filter=annotator_filter,
            )
            print(f"Wrote {count} ZIP file(s) to {args.output_dir}")
            if args.anonymize:
                print(f"Anonymization mapping written to {args.mapping_file or args.output_dir / 'annotator-mapping.csv'}")
            if args.keep_project_export:
                print(f"Kept full project export at {project_zip_path}")
            return 0
        finally:
            if tmpdir is not None:
                tmpdir.cleanup()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
