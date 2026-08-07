"""Markdown report rendering for UIMA policy analysis results."""

from __future__ import annotations

import re
from collections import Counter
from io import TextIOWrapper
from typing import Optional

import randomname

from ..snomed import Information
from .models import CriticalFinding, IgnoreOverlap


def _populate_dump_dictionary(
    dictionary: dict, code: str, offset: tuple[int, int], fsn: Optional[str] = None
):
    if code not in dictionary:
        dictionary[code] = {
            "offset": [offset],
        }
        if fsn is not None:
            dictionary[code]["fsn"] = fsn
    else:
        dictionary[code]["offset"].append(offset)


def _format_overlap_layers(overlaps: list[IgnoreOverlap]) -> str:
    if not overlaps:
        return ""
    return ", ".join(sorted({overlap.layer for overlap in overlaps}))


def _markdown_cell(value) -> str:
    return (
        str(value)
        .replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("|", "\\|")
    )


def _finding_tag(finding: CriticalFinding) -> str:
    if not finding.fsn:
        return ""
    match = re.search(r"\(([^()]*)\)\s*$", finding.fsn)
    return match.group(1) if match else ""


def _format_finding_offset(finding: CriticalFinding) -> str:
    return f"({finding.offset[0]}, {finding.offset[1]})"


def render_finding_sections(
    findings: list[CriticalFinding],
    output_file: TextIOWrapper,
    output_file_masked: TextIOWrapper,
    dump_dictionary: Optional[dict] = None,
):
    annotators = sorted({finding.annotator for finding in findings})
    annotator_names_masked = {
        name: f"annotator-{randomname.get_name(adj=('age', 'character', 'emotions', 'appearance'))}"
        for name in annotators
    }
    documents_masked: dict[str, str] = {}

    def masked_doc(name: str) -> str:
        if name not in documents_masked:
            documents_masked[name] = f"document-{randomname.get_name(adj=('linguistics', 'construction', 'materials', 'geometry', 'algorithms', 'size', 'complexity', 'colors'))}"
        return documents_masked[name]

    def write_policy_section(section_findings: list[CriticalFinding], list_type: str):
        if not section_findings:
            return
        for fi, masked in ((output_file, False), (output_file_masked, True)):
            fi.write(f"# {list_type.capitalize()}\n")
            fi.write(f"[Zum Inhalt](#{Information.log_dump_pretext_caption.lower()})  \n")
            fi.write("Zu den Annotator*innen: ")
            links = []
            for annotator in annotators:
                display = annotator_names_masked[annotator] if masked else annotator
                links.append(f"[{display}](#{display.lower()})")
            fi.write(", ".join(links) + "\n")

            current_annotator = None
            current_document = None
            for finding in section_findings:
                annotator = annotator_names_masked[finding.annotator] if masked else finding.annotator
                document = masked_doc(finding.document) if masked else finding.document
                if annotator != current_annotator:
                    fi.write(f"## {annotator}\n([Zum Sektionsanfang](#{list_type}))\n")
                    current_annotator = annotator
                    current_document = None
                if document != current_document:
                    fi.write(f"#### {document}\n")
                    if list_type == "whitelist":
                        fi.write("| Snomed CT Code | Covered Text | Offset in Document |\n")
                        fi.write("| -------------: | -----------: | -----------------: |\n")
                    else:
                        fi.write("| Snomed CT Code | Covered Text | Offset in Document | FSN |\n")
                        fi.write("| -------------: | -----------: | -----------------: | --: |\n")
                    current_document = document
                code = finding.code or "nan"
                if list_type == "whitelist":
                    fi.write(f"| {_markdown_cell(code)} | {_markdown_cell(finding.covered_text)} | {_format_finding_offset(finding)} |\n")
                else:
                    fi.write(f"| {_markdown_cell(code)} | {_markdown_cell(finding.covered_text)} | {_format_finding_offset(finding)} | {_markdown_cell(finding.fsn or '')} |\n")
            fi.write("\n\n")

    def write_ignored_section(ignored_findings: list[CriticalFinding]):
        if not ignored_findings:
            return
        for fi, masked in ((output_file, False), (output_file_masked, True)):
            fi.write("# Ignored faulty concepts\n")
            fi.write(f"[Zum Inhalt](#{Information.log_dump_pretext_caption.lower()})  \n\n")
            fi.write(
                "These concepts would have been reported as faulty, but were ignored because they overlap with configured ignore layer(s).\n\n"
            )
            for list_type in ("whitelist", "blacklist"):
                section_findings = [f for f in ignored_findings if f.list_type == list_type]
                if not section_findings:
                    continue
                fi.write(f"## {list_type.capitalize()}\n")
                current_annotator = None
                current_document = None
                for finding in section_findings:
                    annotator = annotator_names_masked[finding.annotator] if masked else finding.annotator
                    document = masked_doc(finding.document) if masked else finding.document
                    if annotator != current_annotator:
                        fi.write(f"### {annotator}\n")
                        current_annotator = annotator
                        current_document = None
                    if document != current_document:
                        fi.write(f"#### {document}\n")
                        columns = [
                            "Target Layer",
                            "Snomed CT Code",
                            "Covered Text",
                            "Offset in Document",
                            "Reason",
                            "Overlapping Ignore Layer(s)",
                        ]
                        if list_type == "blacklist":
                            columns.append("FSN")
                        fi.write("| " + " | ".join(columns) + " |\n")
                        fi.write("| " + " | ".join(["--:"] * len(columns)) + " |\n")
                        current_document = document
                    overlap_layers = _format_overlap_layers(list(finding.ignore_overlaps))
                    row = f"| {_markdown_cell(finding.layer or '')} | {_markdown_cell(finding.code or 'nan')} | {_markdown_cell(finding.covered_text)} | {_format_finding_offset(finding)} | {_markdown_cell(finding.reason)} | {_markdown_cell(overlap_layers)}"
                    if list_type == "blacklist":
                        row += f" | {_markdown_cell(finding.fsn or '')}"
                    fi.write(row + " |\n")
            fi.write("\n\n")

    actionable = [finding for finding in findings if not finding.ignored]
    ignored = [finding for finding in findings if finding.ignored]
    write_policy_section([f for f in actionable if f.list_type == "whitelist"], "whitelist")
    write_policy_section([f for f in actionable if f.list_type == "blacklist"], "blacklist")
    write_ignored_section(ignored)

    if dump_dictionary is not None:
        for finding in actionable:
            if finding.code is None:
                continue
            if finding.list_type == "blacklist":
                _populate_dump_dictionary(dump_dictionary, finding.code, finding.offset, finding.fsn or "")
            else:
                _populate_dump_dictionary(dump_dictionary, finding.code, finding.offset)


def finding_counters(findings: list[CriticalFinding]) -> tuple[Counter, Counter]:
    whitelist_code_counter = Counter(
        finding.code for finding in findings if not finding.ignored and finding.list_type == "whitelist" and finding.code
    )
    blacklist_tag_counter = Counter(
        _finding_tag(finding) for finding in findings if not finding.ignored and finding.list_type == "blacklist"
    )
    return whitelist_code_counter, blacklist_tag_counter


def log_final_tag_count(
    whitelist_tag_counter: Counter,
    blacklist_tag_counter: Counter,
    output_file: TextIOWrapper,
    output_file_masked: TextIOWrapper,
):
    def no_count(list_type: str, out_: TextIOWrapper):
        is_whitelist = list_type == "whitelist"
        type_ = "SNOMED CT codes" if is_whitelist else "semantic tags"
        out_.write(
            f"_No {type_} found that are {'not ' if is_whitelist else ''}on the {list_type}_.\n"
        )

    for fi in [output_file, output_file_masked]:
        fi.write("# Final Count\n")
        fi.write("## Snomed CT Codes\n")
        fi.write(f"[Zum Inhalt](#{Information.log_dump_pretext_caption.lower()})  \n\n")
        if sum(whitelist_tag_counter.values()) > 0:
            fi.write("| Snomed CT Code | Count |\n")
            fi.write("| -------------: | ----: |\n")
            for code, count in whitelist_tag_counter.most_common():
                fi.write(f"| {code} | {count} |\n")
        else:
            no_count("whitelist", fi)
        fi.write("## Semantic Tags\n")
        fi.write(f"[Zum Inhalt](#{Information.log_dump_pretext_caption.lower()})  \n\n")
        if sum(blacklist_tag_counter.values()) > 0:
            fi.write("| Semantic Tag | Count |\n")
            fi.write("| -----------: | ----: |\n")
            for tag, count in blacklist_tag_counter.most_common():
                fi.write(f"| {tag} | {count} |\n")
        else:
            no_count("blacklist", fi)
