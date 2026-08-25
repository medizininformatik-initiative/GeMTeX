"""INCEpTION project ZIP retrieval and interactive selection helpers."""

from __future__ import annotations

import logging
import pathlib
from typing import Optional, Union

import yaspin
from PyInquirer import prompt
from pycaprio import Pycaprio


def get_project_zip(
    process_path: str,
    host: str,
    user_name: Optional[str] = None,
    password: Optional[str] = None,
    project_name: Optional[str] = None,
    verify_ssl: Union[bool, str] = True,
) -> Union[pathlib.Path, list[str]]:
    inception_client = None
    project_zip = None
    projects = None
    use_local_zip = False

    if user_name is not None and password is not None:
        logging.info(
            f"Trying to find project '{project_name}' in INCEpTION instance at '{host}'."
        )
        try:
            inception_client = Pycaprio(host, (user_name, password))
            if not verify_ssl:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                inception_client.api.client.session.verify = False
            elif isinstance(verify_ssl, str):
                inception_client.api.client.session.verify = verify_ssl

            projects = {
                p.project_name: p.project_id for p in inception_client.api.projects()
            }
        except Exception as e:
            logging.error(
                f"Something went wrong while trying to connect to INCEpTION instance: '{e}'."
            )
            raise RuntimeError(f"Could not connect to INCEpTION instance: {e}")
    else:
        logging.info(
            f"Inception client credentials were not complete/given and/or no project name. Assuming zipped project under '{process_path}'."
        )
        use_local_zip = True

    if not use_local_zip:
        if project_name is None:
            if projects is not None:
                return list(projects.keys())
            else:
                raise ValueError(
                    "No project name given and no API connection established."
                )
        else:
            logging.info(f"Project name given: '{project_name}'.")

    if inception_client is None:
        project_zip = pathlib.Path(process_path).resolve()
        if (
            not project_zip.exists()
            or not project_zip.is_file()
            or not project_zip.suffix == ".zip"
        ):
            logging.error(f"Could not find project zip file '{process_path}'.")
            raise FileNotFoundError(
                f"Could not find project zip file '{process_path}'."
            )
    else:
        project = [
            p
            for p in projects
            if p.lower() == project_name.lower()
            or str(projects.get(p)) == project_name.lower()
        ]
        if len(project) == 0:
            logging.error(
                f"Could not find project '{project_name}' in INCEpTION instance at '{host}'. Did you forgot to use the 'URL slug' for the project?"
            )
            logging.error(
                f"Available projects: {', '.join([p.lower() for p in projects])}"
            )
            raise ValueError(f"Project '{project_name}' not found.")
        else:
            logging.info(f"Found project '{project_name}' in INCEpTION instance.")
            with yaspin.yaspin(text="Exporting project..."):
                project = project[0]
                project_id = projects.get(project)
                project_export = inception_client.api.export_project(
                    project_id, "jsoncas"
                )
                folder = pathlib.Path(process_path).resolve()
                if folder.is_file():
                    folder = folder.parent
                if not folder.exists():
                    folder.mkdir(parents=True)
                file_path = folder / pathlib.Path(project).with_suffix(".zip")
                logging.info(f"Exporting project '{project}' to '{file_path}'")
                with open(file_path, "wb") as f:
                    f.write(project_export)
            project_zip = file_path
    return project_zip


def prompt_for_names(annotator_names: set[str]):
    if len(annotator_names) <= 1:
        return None

    return_all_name = "return_all"
    return_all = prompt(
        [
            {
                "type": "confirm",
                "name": return_all_name,
                "message": "There are multiple annotators in the project. Do you want to log all of them?",
                "default": False,
            }
        ]
    )
    if return_all.get(return_all_name):
        return None

    annotator_choice_name = "menu_entry"
    annotator_names_chosen = prompt(
        [
            {
                "type": "checkbox",
                "name": annotator_choice_name,
                "message": "Please choose the annotators you want to log:",
                "choices": [{"name": _name} for _name in sorted(annotator_names)],
            }
        ]
    )
    return annotator_names_chosen.get(annotator_choice_name)
