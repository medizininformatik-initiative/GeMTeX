import json
import os
import random

with open('resources' + os.sep + 'titles' + os.sep + 'name_titles.json', encoding='utf-8') as json_file:
    name_titles = json.load(json_file)
    json_file.close()

dict_title_group = {}
for name_title_gr in name_titles:
    for name_title in name_titles[name_title_gr]:
        dict_title_group[name_title] = name_title_gr


def get_name_title(n_title):
    """
    create name title surrogate for further replacement

    Parameters
    ----------
    n_title : dict

    Returns
    -------
    dict
    """


    if n_title in dict_title_group.keys():
        temp = name_titles[dict_title_group[name_title]].copy()
        # bug!
        if n_title in temp:
            temp.remove(n_title)
        return random.sample(temp, 1)[0]
    else:
        return random.sample(name_titles['1'], 1)[0]


def surrogate_name_titles(list_of_names):
    """
    surrogate name titles from list of names

    Parameters
    ----------
    list_of_names : list

    Returns
    -------
    dict
    """

    return {name_to_replace: get_name_title(name_to_replace) for name_to_replace in list_of_names}
