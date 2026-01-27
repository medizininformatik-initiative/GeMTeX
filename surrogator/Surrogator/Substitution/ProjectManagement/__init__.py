import json
import logging
import os
from copy import deepcopy

import cassis
import pandas as pd
from cassis import load_cas_from_json

from Surrogator.FileUtils import export_cas_to_file, read_dir, handle_config
from Surrogator.QualityControl import run_quality_control_of_project, write_quality_control_report
from Surrogator.Substitution.CasManagement.Fictive import CasManagementFictive
from Surrogator.Substitution.CasManagement.Gemtex import CasManagementGemtex
from Surrogator.Substitution.CasManagement.Simple import CasManagementSimple


def set_surrogates_in_inception_projects(config):
    """
    This function starts the process to transform text with different configurations of the placeholders.

    Parameters
    ----------
    config : dict

    Returns
    -------
    dict
    """

    logging.info(msg='Set surrogates in inception projects.')
    logging.info(msg='surrogate modes: ' + str(config['surrogate_process']['surrogate_modes']))

    dir_out_private, dir_out_public, surrogate_modes, timestamp_key = handle_config(config)

    if config['input']['annotation_project_path'] != "":
        if os.path.exists(config['input']['annotation_project_path']):
            projects = read_dir(dir_path=config['input']['annotation_project_path'])
        else:
            return 0
    else:
        return 0

    if not projects:
        return 0

    logging.info(msg='setting private directory ' + dir_out_private)
    logging.info(msg='setting public directory ' + dir_out_public)

    quality_control_of_projects = {}

    for mode in surrogate_modes:
        if mode in ['x', 'entity']:
            cm = CasManagementSimple(mode=mode)
        elif mode == 'gemtex':
            cm = CasManagementGemtex()
        elif mode == 'fictive':
            cm = CasManagementFictive(config=config)
        else:
            logging.warning("No valid modus, only x, entity, gemtex and fictive allowed.")
            exit()

        for project in projects:
            logging.info(msg='Project (file): ' + str(project['name']))
            project_name = project['name']

            logging.info(msg='Project (name): ' + project_name)

            quality_control = run_quality_control_of_project(project)
            corpus_documents = pd.DataFrame(quality_control['corpus_files'], index=['part_of_corpus']).transpose()

            project_surrogate = dir_out_public + os.sep + 'surrogate' + '_' + project_name + '_' + timestamp_key
            if not os.path.exists(path=project_surrogate):
                os.makedirs(name=project_surrogate)

            dir_project_private = dir_out_private + os.sep + project_name
            if not os.path.exists(path=dir_project_private):
                os.makedirs(name=dir_project_private)

            dir_project_cas = dir_project_private + os.sep + 'cas' + '_' + project_name + '_' + timestamp_key
            if not os.path.exists(path=dir_project_cas):
                os.makedirs(name=dir_project_cas)

            doc_random_keys = {}

            logging.info('mode: ' + str(mode))

            for i, ann_doc in enumerate(corpus_documents[corpus_documents['part_of_corpus'] == 1].index):

                logging.info(msg='processing file: ' + str(ann_doc))
                m_cas = deepcopy(project['annotations'][ann_doc])

                pipeline_results = cm.manipulate_cas(cas=m_cas)

                if mode in ['fictive', 'gemtex']:
                    doc_random_keys[ann_doc] = {
                        'filename_orig': str(ann_doc),
                        'annotations': pipeline_results['key_ass'],
                    }

                export_cas_to_file(
                    # cas=m_cas,
                    cas=pipeline_results['cas'],
                    dir_out_text=project_surrogate,
                    dir_out_cas=dir_project_cas,
                    file_name=ann_doc + '_deid_' + timestamp_key,
                )

            # project relevant output
            if mode in ['gemtex', 'fictive']:
                with open(
                        file=dir_project_private + os.sep + project_name + '_' + timestamp_key + '_key_assignment_' + mode + '.json',
                        mode='w',
                        encoding='utf8'
                ) as outfile:
                    json.dump(doc_random_keys, outfile, indent=2, sort_keys=False, ensure_ascii=False)

                flat_random_keys = {}

                # for filename in random_filenames:
                for filename in corpus_documents[corpus_documents['part_of_corpus'] == 1].index:
                    for annotations in doc_random_keys[filename]['annotations']:
                        for key in doc_random_keys[filename]['annotations'][annotations]:
                            flat_random_keys[
                                project_name + '-**-' + filename + '-**-' + str(annotations) + '-**-' + key] = \
                                doc_random_keys[filename]['annotations'][annotations][key]

                with open(
                        file=dir_project_private + os.sep + project_name + '_' + timestamp_key + '_key_assignment_' + mode + '_flat.json',
                        mode='w',
                        encoding='utf8'
                ) as outfile_flat:
                    json.dump(flat_random_keys, outfile_flat, indent=2, sort_keys=False, ensure_ascii=False)

            dir_project_quality_control = dir_project_private + os.sep + 'quality_control' + '_' + project_name + '_' + timestamp_key
            if not os.path.exists(path=dir_project_quality_control):
                os.makedirs(name=dir_project_quality_control)

            quality_control_of_projects[project_name] = quality_control
            write_quality_control_report(
                quality_control=run_quality_control_of_project(project),
                dir_project_quality_control=dir_project_quality_control,
                project_name=project_name,
                timestamp_key=timestamp_key
            )

            logging.info(msg='Processing of project ' + project_name + ' done!')
    logging.info(msg='Processing of given projects done! Timestamp key from this run: ' + timestamp_key)
    logging.info(msg='Private exports: ' + dir_out_private)
    logging.info(msg='Public exports: ' + dir_out_public)

    return {
        "dir_out_private": dir_out_private,
        "dir_out_public": dir_out_public,
        "projects": [project['name'] for project in projects],
        "timestamp_key": timestamp_key,
        "quality_control_of_projects": quality_control_of_projects
    }


def set_surrogates_in_inception_files(config):
    """
    This function starts the process to transform text with different configurations of the placeholders.
    All output files are created here.

    Parameters
    ----------
    config : dict

    Returns
    -------
    """

    logging.info(msg='Set surrogates in inception projects.')
    logging.info(msg='surrogate modes: ' + str(config['surrogate_process']['surrogate_modes']))

    dir_out_private, dir_out_public, surrogate_modes, timestamp_key = handle_config(config)

    path_files_to_process = config['input']['annotation_project_path']
    #modes = config['surrogate_process']['surrogate_modes']

    logging.info(msg='Files in path: ' + path_files_to_process)
    project_name = path_files_to_process.split(os.sep)[-1]
    #project_name = project['name']
    logging.info(msg='Project (name): ' + project_name)

    #quality_control = run_quality_control_of_project(project)
    #corpus_documents = pd.DataFrame(quality_control['corpus_files'], index=['part_of_corpus']).transpose()

    project_surrogate = dir_out_public + os.sep + 'surrogate' + '_' + project_name + '_' + timestamp_key
    if not os.path.exists(path=project_surrogate):
        os.makedirs(name=project_surrogate)

    dir_project_private = dir_out_private + os.sep + project_name
    if not os.path.exists(path=dir_project_private):
        os.makedirs(name=dir_project_private)

    dir_project_cas = dir_project_private + os.sep + 'cas' + '_' + project_name + '_' + timestamp_key
    if not os.path.exists(path=dir_project_cas):
        os.makedirs(name=dir_project_cas)

    for mode in surrogate_modes: ## eigentlich nur 1 Modus!!

        if mode in ['x', 'entity']:
            cm = CasManagementSimple(mode=mode)
        elif mode == 'gemtex':
            cm = CasManagementGemtex()
        elif mode == 'fictive':
            cm = CasManagementFictive(config)
        else:
            logging.warning("No valid modus, only x, entity, gemtex and fictive allowed.")
            exit()

        doc_random_keys = {}

        for ann_doc in os.listdir(path_files_to_process):
            if ann_doc.endswith('json'):# or cas_file.endswith('xmi'):

                with open(path_files_to_process + os.sep + ann_doc, 'rb') as cas_file_stream:
                    cas = cassis.load_cas_from_json(cas_file_stream)

                logging.info(msg='processing file: ' + path_files_to_process + os.sep + ann_doc)
                m_cas = deepcopy(cas)

                pipeline_results = cm.manipulate_cas(cas=m_cas)

                logging.info('mode: ' + str(mode))

                if mode in ['fictive', 'gemtex']:
                    doc_random_keys[ann_doc] = {
                        'filename_orig': str(ann_doc),
                        'annotations': pipeline_results['key_ass'],
                    }

                export_cas_to_file(
                    # cas=m_cas,
                    cas=pipeline_results['cas'],
                    dir_out_text=project_surrogate,
                    dir_out_cas=dir_project_cas,
                    file_name=ann_doc + '_deid_' + timestamp_key,
                )

        # project relevant output
        if mode in ['gemtex', 'fictive']:
            with open(
                    file=dir_project_private + os.sep + project_name + '_' + timestamp_key + '_key_assignment_' + mode + '.json',
                    mode='w',
                    encoding='utf8'
            ) as outfile:
                json.dump(doc_random_keys, outfile, indent=2, sort_keys=False, ensure_ascii=False)


            flat_random_keys = {}

            # for filename in random_filenames:
            #for filename in corpus_documents[corpus_documents['part_of_corpus'] == 1].index:
            for filename in os.listdir(path_files_to_process):
                if filename.endswith('json'):
                    for annotations in doc_random_keys[filename]['annotations']:
                        for key in doc_random_keys[filename]['annotations'][annotations]:
                            flat_random_keys[
                                project_name + '-**-' + filename + '-**-' + str(annotations) + '-**-' + key] = \
                                doc_random_keys[filename]['annotations'][annotations][key]

            with open(
                    file=dir_project_private + os.sep + project_name + '_' + timestamp_key + '_key_assignment_' + mode + '_flat.json',
                    mode='w',
                    encoding='utf8'
            ) as outfile_flat:
                json.dump(flat_random_keys, outfile_flat, indent=2, sort_keys=False, ensure_ascii=False)