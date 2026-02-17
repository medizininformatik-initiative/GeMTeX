import datetime
import json
import logging
import pathlib
import dataclasses
import sys
import zipfile
import gc
from io import TextIOWrapper
from typing import Union

import cassis
import numpy as np
import yaspin


if __name__.find(".uima_processing") != -1:
    from ..utils import ListDumpType
else:
    sys.path.append(".")
    from utils import ListDumpType


@dataclasses.dataclass
class DocumentAnnotations:
    snomed_codes: np.ndarray
    offsets: np.ndarray
    text: np.ndarray
    length: int


@dataclasses.dataclass
class TemporaryContainer:
    max_length: int
    documents: dict[str, DocumentAnnotations]


@dataclasses.dataclass
class TemporaryCorpus:
    annotators: dict[str, TemporaryContainer]


def _load_document(path: Union[str, pathlib.Path]) -> cassis.Cas:
    if isinstance(path, str):
        path = pathlib.Path(path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File '{path}' does not exist.")

    return cassis.load_cas_from_json(path.open("r", encoding="utf-8"))


def get_annotations_from_document(
    document: Union[cassis.Cas, str, pathlib.Path],
    annotation_types: list[str] = None,
    id_prefix: str = "http://snomed.info/id/",
) -> DocumentAnnotations:
    if not annotation_types:
        annotation_types = ["gemtex.Concept"]
    id_prefix = id_prefix + "/" if not id_prefix.endswith("/") else id_prefix
    # annotations = DocumentAnnotations([], [], [], 0)

    if not isinstance(document, cassis.Cas):
        document = _load_document(document)
    codes, offsets, text = [], [], []
    for type_ in annotation_types:
        for annotation in document.select(type_):
            try:
                codes.append(annotation.get("id").removeprefix(id_prefix))
                offsets.append(
                    (
                        annotation.begin,
                        annotation.end,
                    )
                )
                text.append(annotation.get_covered_text())
            except Exception as e:
                pass
    return DocumentAnnotations(
        # snomed_codes=np.asarray(codes, dtype=np.dtypes.StringDType),
        snomed_codes=np.asarray(codes, dtype="bytes"),
        offsets=np.asarray(offsets, dtype="i,i"),
        text=np.asarray(text, dtype=np.dtypes.StringDType),
        length=len(codes),
    )


def process_inception_zip(
    file_path: Union[str, pathlib.Path],
    annotation_types: list[str] = None,
    id_prefix: str = "http://snomed.info/id/",
):
    if not annotation_types:
        annotation_types = ["gemtex.Concept"]

    # ---- Prepare containers ----
    annotations = TemporaryCorpus(annotators={})
    try:
        with zipfile.ZipFile(file_path, "r") as zip_file:
            file_name = file_path.name
            # ---- Read project metadata ----
            try:
                project_meta = json.loads(
                    zip_file.read("exportedproject.json").decode("utf-8")
                )
            except KeyError:
                logging.warning(f"No exportedproject.json found in {file_name}")
                return None

            project_documents = project_meta.get("source_documents", [])
            if not project_documents:
                logging.warning(f"No source documents found in project {file_name}")
                return None

            logging.info(f"Started processing project {file_name}")

            # ---- Process each document ----
            for doc in project_documents:
                doc_name = doc["name"]
                state = doc.get("state", "")
                # annotations[doc_name] = {}

                # Determine path (curation or annotation)
                folder_prefix = (
                    f"curation/{doc_name}/"
                    if state == "CURATION_FINISHED"
                    else f"annotation/{doc_name}/"
                )

                # Collect CAS JSON files
                matching_files = [
                    info.filename
                    for info in zip_file.infolist()
                    if info.filename.startswith(folder_prefix)
                    and info.filename.endswith(".json")
                    and not info.is_dir()
                ]

                # Use INITIAL_CAS.json only if it is the *only* file
                if len(matching_files) > 1:
                    matching_files = [
                        p for p in matching_files if not p.endswith("INITIAL_CAS.json")
                    ]

                if not matching_files:
                    logging.warning(
                        f"No CAS found for {doc_name} in {file_name} ({folder_prefix})"
                    )
                    continue

                # ---- Load each CAS, compute stats, discard CAS ----
                for cas_path in matching_files:
                    annotator_name = str(pathlib.Path(cas_path).stem)

                    try:
                        with zip_file.open(cas_path) as cas_file:
                            cas = cassis.load_cas_from_json(cas_file)
                        doc_anno = get_annotations_from_document(
                            cas, annotation_types, id_prefix
                        )
                        if annotator_name not in annotations.annotators:
                            annotations.annotators[annotator_name] = TemporaryContainer(
                                max_length=0, documents={}
                            )
                        annotations.annotators[annotator_name].documents[doc_name] = (
                            doc_anno
                        )
                        annotations.annotators[annotator_name].max_length = (
                            doc_anno.length
                            if doc_anno.length
                            > annotations.annotators[annotator_name].max_length
                            else annotations.annotators[annotator_name].max_length
                        )
                        # Drop CAS immediately
                        del cas

                    except Exception as e:
                        logging.warning(
                            f"Failed to load {cas_path} from {file_name}: {e}"
                        )

        # Encourage cleanup
        gc.collect()

    except Exception as e:
        logging.error(f"Error processing {file_name}: {e}")
        return None

    return annotations


def analyze_documents(
    project: TemporaryCorpus,
    filter_array: np.ndarray,
    mapping_array: np.ndarray,
    filter_type: ListDumpType,
    out_path: pathlib.Path,
    as_whitelist: bool,
):
    erroneous_doc_count = 0
    # filter_array = filter_array.astype(np.dtypes.StringDType)
    log_doc = out_path.open("w", encoding="utf-8")
    with yaspin.yaspin() as spinner:
        for annotator_name, documents in project.annotators.items():
            new_annotator = True
            doc_error_count = 0
            concept_error_count = 0
            for i, (doc_name, annotations) in enumerate(documents.documents.items()):
                spinner.text = f"Processing ({annotator_name} [{i:>3}/{len(documents.documents)}]: '{doc_name}') ..."
                if as_whitelist:
                    erroneous_codes_array = ~np.isin(annotations.snomed_codes, filter_array)
                else:
                    erroneous_codes_array = np.isin(annotations.snomed_codes, filter_array)

                if not (no_errors := np.all(~erroneous_codes_array)):
                    doc_error_count += 1
                    concept_error_count += np.count_nonzero(erroneous_codes_array)
                    if not as_whitelist:
                        #ToDo: Here mapping of erroneous codes to FSN should be done
                        pass
                    log_critical_docs(
                        annotator_name,
                        doc_name,
                        annotations,
                        erroneous_codes_array,
                        log_doc,
                        new_annotator,
                        as_whitelist,
                    )
                    new_annotator = False
            concept_error_text = f" With {concept_error_count} concept(s) not on '{filter_type.name.lower()}'."
            spinner.write(
                f"{annotator_name}: Done. Found {doc_error_count} critical document(s).{concept_error_text if doc_error_count > 0 else ''}"
            )
            erroneous_doc_count += doc_error_count
    log_doc.close()
    return erroneous_doc_count


def log_critical_docs(
    annotator_name: str,
    document_name: str,
    document_dump: DocumentAnnotations,
    bool_index_array: np.ndarray,
    output_file: TextIOWrapper,
    is_new_annotator: bool,
    is_whitelist: bool

):
    stacked = np.stack(
        [
            document_dump.snomed_codes[bool_index_array],
            document_dump.text[bool_index_array],
            document_dump.offsets[bool_index_array],
        ],
        axis=-1,
        dtype=object,
    )
    lines = []
    if is_new_annotator:
        lines.append(f"## {annotator_name}\n")
    lines.append(f"#### {document_name}\n")
    lines.append(f"| Snomed CT Code | Covered Text | Offset in Document |\n")
    lines.append(f"| -------------: | -----------: | -----------------: |\n")
    for line in stacked:
        lines.append(f"| {line[0].decode('utf-8')} | {line[1]} | {line[2]} |\n")
    output_file.writelines(lines)
    output_file.write("\n\n")
