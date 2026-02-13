import json
import logging
import pathlib
import dataclasses
import zipfile
import gc
from typing import Union

import cassis
import numpy as np


@dataclasses.dataclass
class DocumentAnnotations:
    snomed_codes: np.ndarray
    offsets: np.ndarray
    text: np.ndarray
    length: int


def _load_document(path: Union[str, pathlib.Path]) -> cassis.Cas:
    if isinstance(path, str):
        path = pathlib.Path(path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File '{path}' does not exist.")

    return cassis.load_cas_from_json(path.open("r", encoding="utf-8"))

def get_annotations_from_document(document: Union[cassis.Cas, str, pathlib.Path], annotation_types: list[ str] = None, id_prefix: str = "http://snomed.info/id/") -> DocumentAnnotations:
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
                offsets.append((annotation.begin, annotation.end,))
                text.append(annotation.get_covered_text())
            except Exception as e:
                pass
    return DocumentAnnotations(
        snomed_codes=np.asarray(codes, dtype=np.dtypes.StringDType),
        offsets=np.asarray(offsets, dtype="i,i"),
        text=np.asarray(text, dtype=np.dtypes.StringDType),
        length=len(codes)
    )

def process_inception_zip(file_path: Union[str, pathlib.Path], annotation_types: list[ str] = None, id_prefix: str = "http://snomed.info/id/"):
    if not annotation_types:
        annotation_types = ["gemtex.Concept"]
    # ---- Prepare containers ----
    annotations = {}
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
                annotations[doc_name] = {}

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
                    matching_files = [p for p in matching_files if not p.endswith("INITIAL_CAS.json")]

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
                        annotations[doc_name][annotator_name] = get_annotations_from_document(cas, annotation_types, id_prefix)

                        # Drop CAS immediately
                        del cas

                    except Exception as e:
                        logging.warning(f"Failed to load {cas_path} from {file_name}: {e}")

        # Encourage cleanup
        gc.collect()

    except Exception as e:
        logging.error(f"Error processing {file_name}: {e}")
        return None

    return annotations

def analyze_documents(project: dict[str, dict[str, DocumentAnnotations ]], filter_array: np.ndarray = None):
    # project = {doc_name: {annotator_name: DocumentAnnotations}}
    for doc_name, annotators in project.items():
        for annotator_name, annotations in annotators.items():
            print(f"{doc_name} - {annotator_name}")

    # np.stack((doc1_arr, np.pad(doc2_arr, (0, 1), mode='constant', constant_values=138875005)))
    # .tolist() --> gets the python values like tuple, str etc.
    # np.isin(document_array, filter_array) returns --> returns document_array shaped bool array
