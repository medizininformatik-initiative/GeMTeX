import json
import os
import string

import gender_guesser.detector as gen
import pandas as pd

# Lists of articles and prepositions that may appear in names
ARTICLES = [
    'der', 'die', 'das', 'den', 'dem', 'des',
    'ein', 'eine', 'einen', 'einem', 'einer', 'eines',
    'el', 'la', 'los', 'las', 'le', 'les', 'l',
]

PREPOSITIONS = ['ab', 'an', 'auf', 'aus', 'bei', 'bis', 'durch', 'für', 'gegen', 'ohne', 'um', 'unter', 'über', 'vor',
                'hinter', 'neben', 'zwischen', 'nach', 'mit', 'von', 'zu', 'gegenüber', 'während', 'trotz', 'wegen',
                'statt', 'gemäß', 'entlang', 'seit', 'laut', 'vom', 'zur', 'zum', 'beim', 'van', 'des', 'de', 'del',
                'dos']

TITLES = {"dr", "phil", "univ", "medic", "dres", "med", "dipl", "psych", "dent", "vet", "habil", "mult", "rer", "päd",
          "nat"}


def is_title(token):
    return any(title in token.lower() for title in TITLES)


def has_female_suffix(token):
    return any(female_suffix in token for female_suffix in {"in", "innen"})


def is_salutation(token):
    return token in {"Herr", "Frau", "Hr.", "Fr."}


def is_punctuation(token):
    # includes characters like . , ; ! ? - ( )
    return token in string.punctuation


def detect_gender(name, preceding_words, gender_guesser):
    """
    Detects the gender of a name based on preceding titles, salutations, suffixes, and a fallback gender guessing model.

    Parameters
    ----------
    name : tuple
        A tuple where:
        - The first element (str) is the primary name being analyzed.
        - The second element (list of str) is a list of preceding words providing context (e.g., titles or salutations).
    preceding_words : Any
    gender_guesser : object
        An instance of a gender guessing model or utility that provides a `get_gender` method.

    Returns
    -------
    str
        The detected gender, which can be:
        - "male": Assigned if a male salutation, suffix, or the fallback model identifies the name as male.
        - "female": Assigned if a female salutation, suffix, or the fallback model identifies the name as female.
    """
    for preceding_word in reversed(preceding_words):
        # Skip punctuation
        if is_punctuation(preceding_word):
            continue

        # Check for titles
        if is_title(preceding_word):
            continue

        # Check for salutations
        if is_salutation(preceding_word):
            if preceding_word.lower() in {"herr", "hr."}:  # "patient"
                return "male"
            elif preceding_word.lower() in {"frau", "fr."}:  # "patientin"
                return "female"

        # Check for female suffixes
        if has_female_suffix(preceding_word):
            return "female"

        # If a non-title, non-salutation, non-suffix word is encountered, stop processing
        break
    # use gender guessing model as fallback method for classification
    gender = gender_guesser.get_gender(name)

    return gender


with open('resources' + os.sep + 'de_subLists' + os.sep + 'male.json', 'r', encoding='utf-8') as male_file:
    male_data = json.load(male_file)

with open('resources' + os.sep + 'de_subLists' + os.sep + 'female.json', 'r', encoding='utf-8') as female_file:
    female_data = json.load(female_file)

with open('resources' + os.sep + 'de_subLists' + os.sep + 'family.json', 'r', encoding='utf-8') as family_file:
    family_data = json.load(family_file)


# Check if a word is a preposition or article
def is_prep_or_article(word):
    return word.lower() in ARTICLES or word.lower() in PREPOSITIONS


# Classify each part of a name as First Name (FN) or Last Name (LN)
def classify_name(name, preceding_words):
    """
    Classifies each part of a name as either a first name (FN) or a last name (LN),
    grouping all parts of the last name into a single key while keeping individual
    parts of the first name separate.

    Rules
    - Names with commas (e.g., "LAST, First"):
        - Parts before and including the comma are classified as "LN".
        - Parts after the comma are classified as "FN".
    - Single-word names:
        - If preceded by specific salutations (e.g., "Herr", "Frau"),
          they are classified as "LN".
        - Otherwise, they are classified as "FN".
    - Two-word names without prepositions or articles:
        - The first part is classified as "FN".
        - The second part is classified as "LN".
    - Names with more than two words:
        - Prepositions or articles indicate the start of the last name.
        - The last name is grouped as a single key, and preceding words are classified as "FN".

    Parameters
    ----------
    name : str
        The full name to classify. Can include multiple parts separated by spaces or
        special punctuation such as commas or apostrophes.

    preceding_words : Any

    Returns
    -------
    dict
        A dictionary where:
        - Keys are individual first name parts or the full last name (if it has multiple parts).
        - Values are the classification:
            - "FN": Assigned to each part of the first name.
            - "LN": Assigned to the full last name (grouped as a single key if applicable).
    """
    parts = name.split()
    classification = {}

    # Rule 1: Names with commas (e.g., "LAST, First")
    if ',' in name:
        # Split the name into parts and remove commas
        parts_clean = [part.strip(',') for part in parts]
        try:
            comma_index = next(i for i, part in enumerate(parts_clean) if ',' in name)
        except StopIteration:
            comma_index = None

        if comma_index is not None:
            # All parts before and including the comma are 'LN'
            last_name_parts = []
            first_name_parts = []
            for i, part in enumerate(parts):
                clean_part = part.strip(',')  # Remove comma for clean keys
                if i <= comma_index:
                    last_name_parts.append(clean_part)
                else:
                    first_name_parts.append(clean_part)
            # Join last name parts into one key
            classification[' '.join(last_name_parts)] = 'LN'
            # Assign 'FN' to each first name part
            for fn_part in first_name_parts:
                classification[fn_part] = 'FN'
            return classification

    # Rule 2: Single word names classification based on preceding salutations
    if len(parts) == 1:
        # Iterate through preceding_words in reverse to find relevant indicators
        for preceding_word in reversed(preceding_words):
            # Skip punctuation
            if is_punctuation(preceding_word):
                continue

            # Check for titles
            if is_title(preceding_word):
                continue

            # Check for salutations
            if is_salutation(preceding_word):
                if preceding_word.lower() == "herr":
                    classification[parts[0]] = 'LN'
                    return classification
                elif preceding_word.lower() == "frau":
                    classification[parts[0]] = 'LN'
                    return classification
        # If no relevant preceding words found, assume 'FN'
        classification[parts[0]] = 'FN'
        return classification

    # Rule 3: Two-word names are assumed to be "First Last" if there is no preposition or article
    if len(parts) == 2 and not any(is_prep_or_article(part) for part in parts):
        classification[parts[0]] = 'FN'
        classification[parts[1]] = 'LN'
        return classification

    # Rule 4: Names with more than two words
    last_name_start = None
    for i, part in enumerate(parts):
        if is_prep_or_article(part):
            last_name_start = i
            break

    if last_name_start is not None:
        # Assign 'FN' to parts before last_name_start
        for fn_part in parts[:last_name_start]:
            classification[fn_part] = 'FN'
        # Assign 'LN' to the remaining parts, joined as one key
        last_name = ' '.join(parts[last_name_start:])
        classification[last_name] = 'LN'
    else:
        # No preposition or article found; last word is 'LN', others 'FN'
        for fn_part in parts[:-1]:
            classification[fn_part] = 'FN'
        classification[parts[-1]] = 'LN'

    return classification


def surrogate_names_by_fictive_names(list_of_names):
    """
    Convert JSON data to DataFrames

    Parameters
    ----------
    list_of_names : list

    Returns
    -------
    dict

    """


    male_df = pd.DataFrame([name for _, names in male_data.items() for name in names], columns=['Name'])
    female_df = pd.DataFrame([name for _, names in female_data.items() for name in names], columns=['Name'])

    # Combine male and female DataFrames into one
    # names_df = pd.concat([male_df, female_df], ignore_index=True)

    # Create DataFrame for family names
    family_df = pd.DataFrame([name for _, names in family_data.items() for name in names], columns=['Name'])

    surrogate_first_names = {}
    surrogate_fam_names = {}
    surrogate_all = {}
    gender_guesser = gen.Detector()

    for name in list_of_names.items():
        gender = ''
        preceding_words = name[1]
        classification = classify_name(name[0], preceding_words)

        for classification_key, classification_value in classification.items():
            key_norm = classification_key.lower()
            if classification_value == 'FN':
                if key_norm not in surrogate_all:
                    gender = detect_gender(classification_key, preceding_words, gender_guesser)
                    pool = female_df if gender == 'female' else male_df
                    surrogate_all[key_norm] = pool['Name'].sample(1).iat[0]
                surrogate_first_names[classification_key] = surrogate_all[key_norm]

            elif classification_value == 'LN':
                if key_norm not in surrogate_all:
                    surrogate_all[key_norm] = family_df['Name'].sample(1).iat[0]
                surrogate_fam_names[classification_key] = surrogate_all[key_norm]

    surrogate_names = {}

    for name in list_of_names.items():
        preceding_words = name[1]

        surrogate_name = []

        classification = classify_name(name[0], preceding_words)
        for classification_key, classification_value in classification.items():

            if classification_value == 'FN':
                surrogate_name.append(surrogate_first_names[classification_key])

            elif classification_value == 'LN':
                surrogate_name.append(surrogate_fam_names[classification_key])

        surrogate_names[name[0]] = ' '.join(surrogate_name)

    return surrogate_names
