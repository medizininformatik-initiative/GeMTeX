import collections
import json
import logging
import os

import pandas as pd
from mdutils.mdutils import MdUtils

from Surrogator.FileUtils import read_dir, handle_config
from Surrogator.Substitution.Entities.Date import get_quarter


def examine_cas(cas, cas_name):
    """
    Examine a given cas from a document, compute statistics and decide if document is part of the corpus.

    Parameters
    ----------
    cas : cas object
    cas_name : string

    Returns
    -------
    dict, dict, bool
    """
    stats_det = collections.defaultdict(collections.Counter)
    is_part_of_corpus = 1

    for sentence in cas.select(cas_name):
        for token in cas.select_covered(cas_name, sentence):
            if token.kind is not None:
                stats_det[token.kind].update([token.get_covered_text()])

                if token.kind == 'OTHER':
                    is_part_of_corpus = 0
            else:
                is_part_of_corpus = 0

    return ({kind: list(set(dict(stats_det[kind]).keys())) for kind in stats_det},
            {kind: sum(stats_det[kind].values()) for kind in stats_det},
            is_part_of_corpus)


def run_quality_control_only(config):
    """
    This function is for a check of the annotated elements.

    Parameters
    ----------
    config : dict

    Returns
    -------
    """

    logging.info(msg='quality control')

    dir_out_private, dir_out_public, surrogate_modes, timestamp_key = handle_config(config)

    projects = read_dir(dir_path=config['input']['annotation_project_path'])

    proof_projects(
        projects=projects,
        dir_out_private=dir_out_private,
        timestamp_key=timestamp_key
    )


def write_quality_control_report(quality_control, dir_project_quality_control, project_name, timestamp_key):
    """
    create the markdown report for quality control

    Parameters
    ----------
    quality_control : dict
    dir_project_quality_control : str
    project_name : string
    timestamp_key : string

    Returns
    -------
    dict
    """

    md_report = MdUtils(
        file_name=dir_project_quality_control + os.sep + 'Report_Quality_Control_' + project_name + '_' + timestamp_key + '.md',
        title='Report Quality Control of Run ' + project_name + '_' + timestamp_key
    )
    md_report.write('# Project: ' + project_name + '\n\n')

    with open(file=dir_project_quality_control + os.sep + 'quality_control.json', mode='w', encoding='utf8') as outfile:
        json.dump(quality_control, outfile, indent=2, sort_keys=True, ensure_ascii=False)

    pd_corpus = pd.DataFrame(
        quality_control['corpus_files'],
        index=['part_of_corpus']
    ).rename_axis('document', axis=1).transpose()
    path_file_corpus_documents = dir_project_quality_control + os.sep + project_name + '_corpus_documents.csv'
    pd_corpus.to_csv(path_file_corpus_documents)

    path_file_corpus_details = dir_project_quality_control + os.sep + project_name + '_corpus_details.csv'
    pd.DataFrame(quality_control['stats_detailed']).transpose().to_csv(path_file_corpus_details)
    corpus_details = pd.DataFrame(quality_control['stats_detailed']).transpose().rename_axis('document', axis=1)

    path_file_statistics = dir_project_quality_control + os.sep + project_name + '_statistics.csv'
    pd.DataFrame(quality_control['stats_detailed_cnt']).transpose().to_csv(path_file_statistics)

    md_report.write('\n\n' + pd.DataFrame(
        quality_control['stats_detailed_cnt']).transpose().rename_axis('document').to_markdown() + '\n\n')

    md_report.write('\n\n' + pd.DataFrame(
        quality_control['stats_detailed']).transpose().rename_axis('document').to_markdown() + '\n\n')

    for item in ['OTHER', 'PROFESSION', 'LOCATION_OTHER', 'AGE']:
        if item in corpus_details.keys():
            md_report.write('\n\n' + pd.DataFrame(
                corpus_details).dropna(subset=[item])[item].transpose().rename_axis('document').to_markdown() + '\n\n')

    md_report.write('## Documents of Corpus\n\n')

    corpus_files = pd.DataFrame(quality_control['corpus_files'], index=['part_of_corpus']).transpose()
    md_report.write('### Processed Documents\n\n')
    md_report.write(pd.DataFrame(
        corpus_files[corpus_files['part_of_corpus'] == 1].index).rename_axis('document', axis=0).to_markdown() + '\n\n')

    md_report.write('### Excluded Documents from Corpus (containing OTHER or NONE annotation)\n\n')

    df_part_of_corpus = pd.DataFrame(corpus_files[corpus_files['part_of_corpus'] == 0].index).rename_axis('document', axis=0)
    if not df_part_of_corpus.empty:
        md_report.write(df_part_of_corpus.to_markdown() + '\n\n')
    else:
        md_report.write('No excluded documents.' + '\n\n')

    df_wrong_annotations_none = pd.DataFrame(quality_control['wrong_annotations_none']).transpose().rename_axis('document & token.id')
    if not df_wrong_annotations_none.empty:
        md_report.write('## Wrong annotations (NONE)\n\n' + df_wrong_annotations_none.to_markdown() + '\n\n')
    else:
        md_report.write('No wrong annotations with tag NONE.' + '\n\n')

    df_wrong_annotations_other = pd.DataFrame(quality_control['wrong_annotations_other']).transpose().rename_axis('document & token.id')
    if not df_wrong_annotations_other.empty:
        md_report.write('## Wrong annotations (OTHER)\n\n' + df_wrong_annotations_other.to_markdown() + '\n\n')
    else:
        md_report.write('No wrong annotations with tag OTHER.' + '\n\n')

    df_wrong_annotations_date_birth = pd.DataFrame(quality_control['wrong_annotations_date_birth'])
    if not df_wrong_annotations_date_birth.empty:
        md_report.write('## Wrong DATE_BIRTH\n\n' + df_wrong_annotations_date_birth.transpose().to_markdown() + '\n\n')
    else:
        md_report.write('No wrong annotations with tag BIRTH_DATE.' + '\n\n')

    df_wrong_annotations_date_death = pd.DataFrame(quality_control['wrong_annotations_date_death'])
    if not df_wrong_annotations_date_death.empty:
        md_report.write('## Wrong BIRTH_DATE\n\n' + df_wrong_annotations_date_death.transpose().to_markdown() + '\n\n')
    else:
        md_report.write('No wrong annotations with tag BIRTH_DEATH.' + '\n\n')

    md_report.write(
        '## Counts DATE_BIRTH\n\n'
        + pd.DataFrame(
            quality_control['birthday_cnt'],
            index=['DATE_BIRTH (#)']
        ).rename_axis('document', axis=0).transpose().to_markdown() + '\n\n'
    )

    md_report.create_md_file()
    logging.info(msg='Report quality control of project "' + project_name + '" in ' + md_report.file_name)

    return {
        "path_file_corpus_details":    path_file_corpus_details,
        "path_file_corpus_documents":  path_file_corpus_documents,
        "path_file_statistics":        path_file_statistics,
        "path_file_report_md":         md_report.file_name,
        "dir_project_quality_control": dir_project_quality_control
    }


def proof_projects(projects, dir_out_private, timestamp_key):
    """
    proof and examine projects (bunch of single projects),
    examination started by run_quality_control_of_project(...)

    Parameters
    ----------
    projects : list[dict]
    dir_out_private : str
    timestamp_key : str

    Returns
    -------
    dict
    """

    for project in projects:
        project_name = project['name']

        logging.info(msg='name: ' + project_name)

        dir_project_private = dir_out_private + os.sep + project_name
        if not os.path.exists(path=dir_project_private):
            os.makedirs(name=dir_project_private)

        dir_project_quality_control = dir_project_private + os.sep + 'quality_control' + '_' + project_name + '_' + timestamp_key
        if not os.path.exists(path=dir_project_quality_control):
            os.makedirs(name=dir_project_quality_control)

        write_quality_control_report(
            quality_control=run_quality_control_of_project(project),
            dir_project_quality_control=dir_project_quality_control,
            project_name=project_name,
            timestamp_key=timestamp_key
        )


def run_quality_control_of_project(project):
    """
    proof and examine one single project

    Parameters
    ----------
    project : dict

    Returns
    -------
    dict
    """

    logging.info(msg='project: ' + str(project['name']))

    wrong_annotations_none       = {}
    wrong_annotations_other      = {}
    wrong_annotations_date_birth = {}
    wrong_annotations_date_death = {}

    stats_detailed          = {}
    stats_detailed_cnt      = {}
    corpus_files            = {}
    birthday_cnt            = {}

    for i, document in enumerate(project['annotations']):

        logging.info(msg='processing document [' + str(i + 1) + ']: ' + str(document))
        cas = project['annotations'][document]
        relevant_types = [t for t in cas.typesystem.get_types() if 'PHI' in t.name]

        if relevant_types:

            cas_name = relevant_types[0].name

            stats_det, stats_det_count, is_part_of_corpus = examine_cas(cas=cas, cas_name=cas_name)

            corpus_files[document]       = is_part_of_corpus
            stats_detailed[document]     = dict(stats_det)
            stats_detailed_cnt[document] = dict(stats_det_count)

            if 'DATE_BIRTH' not in stats_det_count:
                logging.warning(msg='No BIRTH_DATE annotated.')
                birthday_cnt[document] = 0
            else:
                if 'DATE_BIRTH' in stats_detailed[document].keys():
                    for date_ann in stats_detailed[document]['DATE_BIRTH']:
                        if get_quarter(date_ann) == 'none':
                            wrong_annotations_date_death[document] = {'wrong data annotation': date_ann}
                else:
                    logging.warning('no DATE_BIRTH annotation')

                if int(stats_detailed_cnt[document]['DATE_BIRTH']) > 1:
                    logging.warning(msg='More than one DATE_BIRTH inside!')
                    birthday_cnt[document] = stats_detailed_cnt[document]['DATE_BIRTH']

            if 'DATE_DEATH' in stats_detailed[document].keys():
                for date_ann in stats_detailed[document]['DATE_DEATH']:
                    if get_quarter(date_ann) == 'none':
                        wrong_annotations_date_death[document] = {'wrong data annotation': date_ann}
                else:
                    logging.warning(msg='no DATE_DEATH annotation')

            for sentence in cas.select(cas_name):

                for token in cas.select_covered(cas_name, sentence):

                    if token.kind is None or 'OTHER' == token.kind:
                        if token.kind is None:
                            wrong_annotations_none[document + ' & ' + str(token.xmiID)] = {
                                'text':        token.get_covered_text(),
                                'token.begin': str(token.begin),
                                'token.end':   str(token.end),
                            }
                        elif token.kind == 'OTHER':
                            wrong_annotations_other[document + ' & ' + str(token.xmiID)] = {
                                'text':        token.get_covered_text(),
                                'token.begin': str(token.begin),
                                'token.end':   str(token.end),
                            }

                        logging.warning(msg='---- Wrong Annotation : [kind]' + str(token.kind) + ' ----')
                        logging.warning(msg='token.xmiID: ' + str(token.xmiID))
                        logging.warning(msg='token.text: '  + str(token.get_covered_text()))
                        logging.warning(msg='token.begin: ' + str(token.begin) + ' / token.end: ' + str(token.end))
                        logging.warning(msg='------------------------')

        else:
            logging.warning(msg='--- NO PII or PHI layer annotations ---')

    quality_control = {
        'wrong_annotations_none':       wrong_annotations_none,
        'wrong_annotations_other':      wrong_annotations_other,
        'wrong_annotations_date_birth': wrong_annotations_date_birth,
        'wrong_annotations_date_death': wrong_annotations_date_death,
        'stats_detailed':               stats_detailed,
        'stats_detailed_cnt':           stats_detailed_cnt,
        'corpus_files':                 corpus_files,
        'birthday_cnt':                 birthday_cnt
    }

    return quality_control
