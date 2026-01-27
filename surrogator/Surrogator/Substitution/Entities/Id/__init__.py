import random
import string
import re
import schwifty


def check_iban(id_iban):
    """
    Proof if given string is a valid IBAN

    Parameters
    ----------
    id_iban : str

    Returns
    -------
    string or 0
    """

    try:
        schwifty.IBAN(id_iban)
    except ValueError:
        return 0


def check_bic(id_bic):
    """
    Proof if given string is a valid IBAN

    Parameters
    ----------
    id_bic : str

    Returns
    -------
    string or 0
    """

    try:
        schwifty.BIC(id_bic)
    except ValueError:
        return 0


def surrogate_identifiers(identifier_strings):
    """
    create surrogates of identifiers tagged PII items

    Parameters
    ----------
    identifier_strings : dict

    Returns
    -------
    dict
    """

    random.seed(random.randint(0, 100))

    id_strs = {}
    for id_str in identifier_strings:

        if check_iban(id_str) != 0 and check_iban(id_str) is not None:
            id_strs[id_str] = schwifty.IBAN.random(country_code="DE")
        if check_bic(id_str) != 0 and check_bic(id_str) is not None:
            id_strs[id_str] = schwifty.BIC.from_bank_code('DE', schwifty.IBAN.random(country_code="DE").bank_code)
        else:
            random_id = ''
            for c in id_str:
                if c.isupper():
                    random_id = random_id + random.choice(string.ascii_uppercase)
                elif c.islower():
                    random_id = random_id + random.choice(string.ascii_lowercase)
                elif c.isdigit():
                    random_id = random_id + str(random.randint(0, 9))
                else:
                    random_id = random_id + c
            id_strs[id_str] = random_id

    return id_strs


def surrogate_email(mail_strings, names, locations, location_organizations):
    """
    create surrogates of PII items tagged as email

    Parameters
    ----------
    mail_strings : dict
    names : dict
    locations : dict
    location_organizations : dict

    Returns
    -------
    dict
    """

    replaced_strings = {}

    l_names = {}
    l_cities = {}
    l_location_organizations = {}

    for nam_str in names:
        l_names[nam_str.lower()] = (names[nam_str]).lower()

    for city_string in locations:
        l_cities[city_string.lower()] = (locations[city_string]).lower()

    for loc_str in location_organizations:
        l_location_organizations[loc_str.lower()] = (location_organizations[loc_str]).lower()

    names.update(l_names)
    locations.update(l_cities)
    location_organizations.update(l_location_organizations)

    spl_dict = {}
    for mail_string in mail_strings:
        spl = re.split(r'\W', mail_string)

        for i, s in enumerate(spl):
            if i != len(spl) - 1:
                if s in names.keys():
                    spl_dict[s] = names[s]
                elif s in locations.keys():
                    spl_dict[s] = locations[s]
                elif s in location_organizations.keys():
                    spl_dict[s] = location_organizations[s]
                elif s in ['klinik', 'klinikum', 'krankenhaus']:
                    spl_dict[s] = s
                else:
                    if s is not spl_dict.keys():
                        spl_dict[s] = ''.join(list(surrogate_identifiers([s]).values()))

    for mail_string in mail_strings:
        mail_string_old = mail_string
        for entry in spl_dict:
            mail_string = mail_string.replace(entry, spl_dict[entry])

        replaced_strings[mail_string_old] = mail_string.replace(' ', '')

    return replaced_strings


def surrogate_url(url_strings, names, locations, location_organizations):
    """
    create surrogates of PII items tagged as url

    Parameters
    ----------
    mail_strings : dict
    names : dict
    location : dict
    location_organizations : dict

    Returns
    -------
    dict
    """

    replaced_strings = {}

    l_names = {}
    l_cities = {}
    l_location_organizations = {}

    for nam_str in names:
        l_names[nam_str.lower()] = (names[nam_str]).lower()

    for city_string in locations:
        l_cities[city_string.lower()] = (locations[city_string]).lower()

    for loc_str in location_organizations:
        l_location_organizations[loc_str.lower()] = (location_organizations[loc_str]).lower()

    names.update(l_names)
    locations.update(l_cities)
    location_organizations.update(l_location_organizations)

    spl_dict = {}
    for url_string in url_strings:
        spl = re.split(r'\W', url_string)

        for i, s in enumerate(spl):
            if (i != len(spl) - 1):
                if (s != 'www') and (s != 'http') and (s != 'https'):
                    if s in names.keys():
                        spl_dict[s] = names[s]
                    elif s in locations.keys():
                        spl_dict[s] = locations[s]
                    elif s in location_organizations.keys():
                        spl_dict[s] = location_organizations[s]
                    elif s in ['klinik', 'klinikum', 'krankenhaus']:
                        spl_dict[s] = s
                    else:
                        if s is not spl_dict.keys():
                            spl_dict[s] = ''.join(list(surrogate_identifiers([s]).values()))

    for url_string in url_strings:
        url_string_old = url_string
        for entry in spl_dict:
            url_string = url_string.replace(entry, spl_dict[entry])

        replaced_strings[url_string_old] = url_string.replace(' ', '')

    return replaced_strings
