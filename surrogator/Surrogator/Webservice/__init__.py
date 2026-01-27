"""
This is Surrogator's Webservice.
This file is derived from
https://github.com/inception-project/inception-reporting-dashboard/blob/main/inception_reports/generate_reports_manager.py
"""

import copy
import logging as log
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import pkg_resources
import requests
import streamlit as st
import streamlit_ext as ste
import toml
from pycaprio import Pycaprio
from streamlit import session_state

from Surrogator.FileUtils import read_dir
from Surrogator.QualityControl import run_quality_control_of_project, write_quality_control_report
from Surrogator.Substitution.ProjectManagement import set_surrogates_in_inception_projects

st.set_page_config(
    page_title="GeMTeX Surrogator",
    layout="wide",
    initial_sidebar_state=st.session_state.setdefault("sidebar_state", "expanded"),
)

if st.session_state.get("flag"):
    st.session_state.sidebar_state = st.session_state.flag
    del st.session_state.flag
    time.sleep(0.01)
    st.rerun()


def startup():
    st.markdown(
        """

        <style>
        .block-container {
            padding-top: 0rem;
            padding-bottom: 5rem;
            padding-left: 5rem;
            padding-right: 5rem;
        }
        </style>

        <style>
        div[data-testid="stHorizontalBlock"] {
            margin-top: 1rem;
            border: thick double #999999;
            box-shadow: 0px 0px 10px #999999;
        }
        </style>

        <style>
        section.main > div {max-width:95%}
        </style>
        """,
        unsafe_allow_html=True,
    )

    project_info = get_project_info()
    if project_info:
        current_version, package_name = project_info
        latest_version = check_package_version(current_version, package_name)
        if latest_version:
            st.sidebar.warning(
                f"A new version ({latest_version}) of {package_name} is available. "
                f"You are currently using version ({current_version}). Please update the package."
            )


def get_project_info():
    try:
        pyproject_path = os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")
        with open(pyproject_path, "r") as f:
            pyproject_data = toml.load(f)
        version = pyproject_data["project"].get("version")
        name = pyproject_data["project"].get("name")
        if version and name:
            return version, name
        return None
    except (FileNotFoundError, KeyError):
        return None


def check_package_version(current_version, package_name):
    try:
        response = requests.get(f"https://pypi.org/pypi/{package_name}/json", timeout=5)
        if response.status_code == 200:
            latest_version = response.json()["info"]["version"]
            if pkg_resources.parse_version(
                    current_version
            ) < pkg_resources.parse_version(latest_version):
                return latest_version
    except requests.RequestException:
        return None
    return None


def set_sidebar_state(value):
    if st.session_state.sidebar_state == value:
        st.session_state.flag = value
        st.session_state.sidebar_state = (
            "expanded" if value == "collapsed" else "collapsed"
        )
    else:
        st.session_state.sidebar_state = value
    st.rerun()


def login_to_inception(api_url, username, password):
    """
    Logs in to the Inception API using the provided API URL, username, and password.
    (Derived from INCEpTION dashboard.)

    Args:
        api_url (str): The URL of the Inception API.
        username (str): The username for authentication.
        password (str): The password for authentication.

    Returns:
        tuple: A tuple containing a boolean value indicating whether the login was successful and an instance of the Inception client.

    """
    if "http" not in api_url:
        api_url = f"http://{api_url}"
    button = st.sidebar.button("Login")
    if button:
        inception_client = Pycaprio(api_url, (username, password))
        try:
            inception_client.api.projects()
            st.sidebar.success("Login successful ✅")
            return True, inception_client
        except Exception:
            st.sidebar.error("Login unsuccessful ❌")
            return False, None
    return False, None


def select_method_to_handle_the_data():
    """
    Allows the user to select a method to import data for generating reports.
    derived from select_method_to_import_data()
    (Derived from INCEpTION dashboard.)
    """

    method = st.sidebar.radio(
        "Choose your method to import data:",
        ("Manually", "API"),
        index=0
    )

    modus = st.sidebar.radio(
        "Choose the surrogation modus:",
        ("x", "entity", "gemtex", "fictive")
    )

    date_shift = st.sidebar.number_input("Date Shift:", step=1)

    if method == "Manually":
        st.sidebar.write("Please input the path to the folder containing the INCEpTION projects.")
        projects_folder = st.sidebar.text_input("Projects Folder:", value="")
        uploaded_files  = st.sidebar.file_uploader("Or upload project files:", accept_multiple_files=True, type="zip")
        button_qc_m     = st.sidebar.button("Run Quality Control")
        button_sur_m    = st.sidebar.button("Run Creation Surrogates")

        upload_folder = _get_upload_folder()
        if button_qc_m:
            if uploaded_files:
                for uploaded_file in uploaded_files:
                    file_path = upload_folder / uploaded_file.name
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.read())
                selected_projects = [f.name.split(".")[0] for f in uploaded_files]
                st.session_state["projects"] = read_dir(str(upload_folder), selected_projects)
                st.session_state["projects_folder"] = upload_folder

            elif projects_folder:
                st.session_state["projects"] = read_dir(projects_folder)
                st.session_state["projects_folder"] = projects_folder

            st.session_state["task"] = "quality_control"
            st.session_state["method"] = "Manually"
            set_sidebar_state("collapsed")

        if button_sur_m:
            if uploaded_files:
                for uploaded_file in uploaded_files:
                    file_path = upload_folder / uploaded_file.name
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.read())
                annotation_project_path = upload_folder
            else:
                annotation_project_path = projects_folder
            config = {
                'input': {
                    'annotation_project_path': annotation_project_path,
                    'task': 'surrogate'
                },
                'surrogate_process': {
                    'surrogate_modes': [modus],
                    'date_surrogation': date_shift
                },
                'output': ''
            }

            st.session_state["task"] = "surrogate"
            st.session_state["projects"] = projects_folder
            config['surrogate_process']['rename_files'] = True

            st.session_state["config"] = config
            st.session_state["method"] = "Manually"
            set_sidebar_state("collapsed")

    elif method == "API":

        projects_folder = f"{os.path.expanduser('~')}/.gemtex_surrogator/projects"

        #if os.path.exists(projects_folder):
        #    shutil.rmtree(projects_folder)
        #os.makedirs(projects_folder)

        os.makedirs(os.path.dirname(projects_folder), exist_ok=True)
        st.session_state["projects_folder"] = projects_folder

        api_url = st.sidebar.text_input("Enter API URL:", "")
        username = st.sidebar.text_input("Username:", "")
        password = st.sidebar.text_input("Password:", type="password", value="")

        inception_status = st.session_state.get("inception_status", False)
        inception_client = st.session_state.get("inception_client", None)

        if not inception_status:
            inception_status, inception_client = login_to_inception(
                api_url=api_url, username=username, password=password
            )
            st.session_state["inception_status"] = inception_status
            st.session_state["inception_client"] = inception_client

        if inception_status and "available_projects" not in st.session_state:
            inception_projects = inception_client.api.projects()
            st.session_state["available_projects"] = inception_projects

        if inception_status and "available_projects" in st.session_state:
            st.sidebar.write("Select the projects to import:")
            selected_projects = st.session_state.get("selected_projects", {})

            for inception_project in st.session_state["available_projects"]:
                project_name = inception_project.project_name
                project_id = inception_project.project_id
                selected_projects[project_id] = st.sidebar.checkbox(project_name, value=False)
                st.session_state["selected_projects"] = selected_projects

            selected_projects_names = []

            button_qc_a = st.sidebar.button("Run Quality Control")
            button_sur_a = st.sidebar.button("Run Creation Surrogates")

            if button_qc_a or button_sur_a:

                for project_id, is_selected in selected_projects.items():

                    if is_selected:

                        project = inception_client.api.project(project_id)
                        selected_projects_names.append(project.project_name)
                        file_path = f"{projects_folder}/{project.project_name}.zip"

                        proc_folder = f"{projects_folder}/"
                        for file in os.scandir(proc_folder):
                            if file.name.endswith(".zip"):
                                os.unlink(file.path)
                        if not os.path.isdir(proc_folder):
                            os.makedirs(proc_folder)

                        st.sidebar.write(f"Importing project: {project.project_name}")
                        log.info(f"Importing project {project.project_name} into {file_path} ")
                        project_export = inception_client.api.export_project(project, "jsoncas")

                        with open(file_path, "wb") as f:
                            f.write(project_export)
                        log.debug("Import Success")

                st.session_state["method"] = "API"
                st.session_state["projects"] = read_dir(
                    dir_path=projects_folder,
                    selected_projects=selected_projects_names
                )

            if button_qc_a:
                st.session_state["task"] = "quality_control"
                set_sidebar_state("collapsed")

            if button_sur_a:
                config = {
                    'input': {
                        'annotation_project_path': projects_folder,
                        'task': 'surrogate'
                    },
                    'surrogate_process': {
                        # 'corpus_documents': corpus_documents,
                        'surrogate_modes': []
                    },
                    'output': ''
                }

                st.session_state["task"] = "surrogate"

                config['surrogate_process']['surrogate_modes'].append(modus)  # .append("gemtex") ## todo
                config['surrogate_process']['rename_files'] = True
                st.session_state["config"] = config
                set_sidebar_state("collapsed")

        #if os.path.exists(projects_folder):
        #    shutil.rmtree(projects_folder)


def _get_upload_folder() -> Path:
    folder = Path('~').expanduser() / '.gemtex_surrogator' / 'projects'
    if os.path.exists(folder):
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def create_zip_download_quality_control(project_name, timestamp_key, paths_reports):
    """
    Create a zip file containing all generated reports including csv files and the summarizing md file,
    Download button provided.
    """

    shutil.make_archive(
        base_name=os.getcwd() + os.sep + paths_reports['dir_project_quality_control'],
        format='zip',
        root_dir=os.getcwd() + os.sep + paths_reports['dir_project_quality_control']
    )

    with open(os.getcwd() + os.sep + paths_reports['dir_project_quality_control'] + '.zip', "rb") as zip_qc_file:
        zip_qc_byte = zip_qc_file.read()
    ste.download_button(
        label="Download Quality Control Reports (ZIP) - " + project_name,
        data=zip_qc_byte,
        file_name='quality_control' + '_' + project_name + '_' + timestamp_key + '.zip',
        mime='application/zip'
    )


def webservice_output_quality_control(quality_control, timestamp_key, project_name):
    """
    Create the displayed output of the quality control as part of the webservice.
    """

    st.write("<hr>", unsafe_allow_html=True)

    st.write(pd.DataFrame(quality_control['stats_detailed_cnt']).transpose().rename_axis('document'))
    st.write(pd.DataFrame(quality_control['stats_detailed']).transpose().rename_axis('document'))

    st.write("<hr>", unsafe_allow_html=True)
    corpus_files = pd.DataFrame(quality_control['corpus_files'], index=['part_of_corpus']).transpose()

    st.write('<h3>Processed Documents</h3>', unsafe_allow_html=True)
    st.write(
        pd.DataFrame(
            corpus_files[corpus_files['part_of_corpus'] == 1].index,
            columns=['document'])
        .rename_axis('#', axis=0)
    )

    st.write('<h3> Excluded Documents from Corpus (containing OTHER or NONE annotation)</h3>', unsafe_allow_html=True)
    df_part_of_corpus = pd.DataFrame(corpus_files[corpus_files['part_of_corpus'] == 0].index).rename_axis('document',                                                                                                          axis=0)
    if not df_part_of_corpus.empty:
        st.write(df_part_of_corpus)
    else:
        st.write('No wrong annotations with tag NONE.' + '\n\n')

    st.write('<h4> &#10132; Wrong Annotations (NONE)</h4>', unsafe_allow_html=True)
    df_wrong_annotations_none = pd.DataFrame(
        quality_control['wrong_annotations_none']).transpose().rename_axis('document & token.id')
    if not df_wrong_annotations_none.empty:
        st.write(df_wrong_annotations_none.to_markdown() + '\n\n')
    else:
        st.write('No wrong annotations with tag NONE.' + '\n\n')

    st.write('<h4> &#10132; Wrong Annotations (OTHER)</h4>', unsafe_allow_html=True)
    df_wrong_annotations_other = pd.DataFrame(
        quality_control['wrong_annotations_other']).transpose().rename_axis('document & token.id')
    if not df_wrong_annotations_other.empty:
        st.write(df_wrong_annotations_other.to_markdown() + '\n\n')
    else:
        st.write('No wrong annotations with tag OTHER.' + '\n\n')

    df_wrong_annotations_date_birth = pd.DataFrame(quality_control['wrong_annotations_date_birth'])
    if not df_wrong_annotations_date_birth.empty:
        st.write('## Wrong DATE_BIRTH\n\n' + df_wrong_annotations_date_birth.transpose().to_markdown() + '\n\n')
    else:
        st.write('No wrong annotations with tag BIRTH_DATE.' + '\n\n')

    df_wrong_annotations_date_death = pd.DataFrame(quality_control['wrong_annotations_date_death'])
    if not df_wrong_annotations_date_death.empty:
        st.write('## Wrong BIRTH_DATE\n\n' + df_wrong_annotations_date_death.transpose().to_markdown() + '\n\n')
    else:
        st.write('No wrong annotations with tag BIRTH_DEATH.' + '\n\n')

    st.write('<h3>Counts DATE_BIRTH</h3>', unsafe_allow_html=True)
    st.write(
        pd.DataFrame(
            quality_control['birthday_cnt'],
            index=['DATE_BIRTH (#)']
        ).rename_axis('document', axis=0).transpose()
    )

    out_directory_private = 'private'
    if not os.path.exists(path=out_directory_private):
        os.makedirs(name=out_directory_private)

    out_directory_private = 'private' + os.sep + 'private-' + timestamp_key
    if not os.path.exists(path=out_directory_private):
        os.makedirs(name=out_directory_private)
        log.info(msg=out_directory_private + ' created.')

    dir_project_quality_control = ('private' + os.sep + 'private-' + timestamp_key + os.sep +
                                   'quality_control' + '_' + project_name + '_' + timestamp_key)
    if not os.path.exists(path=dir_project_quality_control):
        os.makedirs(name=dir_project_quality_control)
        log.info(msg=dir_project_quality_control + ' created.')

    paths_reports = write_quality_control_report(
        quality_control=quality_control,
        dir_project_quality_control=dir_project_quality_control,
        project_name=project_name,
        timestamp_key=timestamp_key
    )

    return paths_reports


def main():
    startup()

    st.write(
        "<style> h1 {text-align: center; margin-bottom: 50px, } </style>",
        unsafe_allow_html=True,
    )
    st.title("GeMTeX Surrogator for INCEpTION projects")
    st.write("<hr>", unsafe_allow_html=True)
    select_method_to_handle_the_data()

    if (
            "projects" not in st.session_state.keys() or
            (len(st.session_state["projects"]) == 0) or
            st.session_state["projects"] != []
    ):
        st.write(
            '<b>Input a valid project path.</b>',
            unsafe_allow_html=True
        )

    if (
            "method" in st.session_state.keys() and
            "projects" in st.session_state.keys() and
            len(st.session_state["projects"]) > 0 and
            "config" not in st.session_state.keys()
    ):
        projects = [copy.deepcopy(project) for project in st.session_state["projects"]]

        projects = sorted(projects, key=lambda x: x["name"])

        st.write('<h2>Run Quality Control</h2>', unsafe_allow_html=True)
        st.write('Starting...', unsafe_allow_html=True)

        timestamp_key = datetime.now().strftime('%Y%m%d-%H%M%S')

        for project in projects:
            quality_control = run_quality_control_of_project(project)
            st.write("<hr>", unsafe_allow_html=True)
            project_name = '-'.join(project['name'].replace('.zip', '').split('-')[0:-1])

            st.write('<b>Project: <b>' + project_name, unsafe_allow_html=True)

            paths_reports = webservice_output_quality_control(
                quality_control=quality_control,
                timestamp_key=timestamp_key,
                project_name=project_name
            )
            create_zip_download_quality_control(
                project_name=project_name,
                timestamp_key=timestamp_key,
                paths_reports=paths_reports
            )

        st.write("<hr>", unsafe_allow_html=True)

    if "config" in st.session_state and "projects" in st.session_state:
        st.write('<h2>Run Creation Surrogates</h2>', unsafe_allow_html=True)

        surrogate_return = set_surrogates_in_inception_projects(config=st.session_state["config"])

        if surrogate_return == 0:
            st.write(
                '<b>WARNING: The given input project path is not existing or an empty string. Nothing processed.</b><br>'+
                '<b>Please reload your Browser.</b><br>',
                unsafe_allow_html=True
            )
            st.write(
                'Repeat the input.',
                unsafe_allow_html=True
            )
        else:
            st.write('Starting...', unsafe_allow_html=True)

            dir_out_private = surrogate_return['dir_out_private']
            dir_out_public = surrogate_return['dir_out_public']
            projects = surrogate_return['projects']
            timestamp_key = surrogate_return['timestamp_key']

            st.write('<h3>Run Information</h3>', unsafe_allow_html=True)
            st.write('<b>timestamp_key:</b> ' + str(timestamp_key), unsafe_allow_html=True)

            st.write('<h3>Processed Projects</h3>', unsafe_allow_html=True)
            for proj in projects:
                st.write("<hr>", unsafe_allow_html=True)
                st.write('<h3> Project ' + proj + '</h3>', unsafe_allow_html=True)
                webservice_output_quality_control(
                    quality_control=surrogate_return['quality_control_of_projects'][proj], ## hier gibts Fehler.
                    timestamp_key=timestamp_key,
                    project_name=proj,
                )

            st.write('<h4>Results</h4>', unsafe_allow_html=True)
            st.write('<b>Private exports:</b> ' + str(dir_out_private), unsafe_allow_html=True)
            st.write('<b>Public exports:</b> ' + str(dir_out_public), unsafe_allow_html=True)

            shutil.make_archive(
                base_name=dir_out_private,
                format='zip',
                root_dir=str('private' + os.sep + 'private-' + timestamp_key),
            )

            with open(dir_out_private + '.zip', "rb") as zip_file:
                zip_byte = zip_file.read()
            ste.download_button(
                label="Download PRIVATE files: cas annotation files and statistics (" + timestamp_key + ")",
                data=zip_byte,
                file_name='private-' + timestamp_key + '.zip',
                mime='application/zip'
            )

            shutil.make_archive(
                base_name=dir_out_public,
                format='zip',
                root_dir=str('public' + os.sep + 'public-' + timestamp_key),
            )

            with open(dir_out_public + '.zip', "rb") as zip_file_public:
                zip_byte_public = zip_file_public.read()
            ste.download_button(
                label="Download PUBLIC files: text files with surrogates (" + timestamp_key + ")",
                data=zip_byte_public,
                file_name='public-' + timestamp_key + '.zip',
                mime='application/zip'
            )

            st.write('Processing done.')
            st.write("<hr>", unsafe_allow_html=True)

        if "config" in session_state.keys():
            del session_state["config"]
        if "projects_folder" in session_state.keys():
            del session_state["projects_folder"]


if __name__ == "__main__":
    main()
