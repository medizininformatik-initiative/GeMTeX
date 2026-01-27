import logging
import re
from datetime import datetime
from datetime import timedelta
import dateutil
import pandas as pd

from Surrogator.Substitution.Entities.Date.dateFormats import dateFormatsAlpha
from Surrogator.Substitution.Entities.Date.dateFormats import dateFormatsNr
from Surrogator.Substitution.Entities.Date.dateFormats import dateReplMonths
from Surrogator.Substitution.Entities.Date.dateFormats import DateParserInfo


def get_quarter(str_date):
    """
    Get quarter of a date string a date formatted string.

    Parameters
    ----------
    str_date: str

    Returns
    -------
    quarter: str
    """

    try:
        quart = pd.Timestamp(str_date).quarter
        year = pd.Timestamp(str_date).year

        if quart == 1:
            return '01.01.' + str(year)
        elif quart == 2:
            return '01.04.' + str(year)
        elif quart == 3:
            return '01.07.' + str(year)
        elif quart == 4:
            return '01.10.' + str(year)
        return 'none'

    except ValueError:
        logging.warning('Not able to convert date to quarter! ' + str_date + 'is returned as NONE value.')
        return 'none'


def surrogate_dates(dates, int_delta):
    """
    surrogate a list of dates

    Parameters
    ----------
    dates: dict
    int_delta: int

    Returns
    -------
    dates: dict
    """


    for date in dates:
        dates[date] = sub_date(date, int_delta)
    return dates


def sub_date(str_token, int_delta):
    """
    str_token : date annotation a string
    int_delta : delta for shift of the dates as string
    """

    try:
        token_pars = dateutil.parser.parse(
            re.sub(r'\.(?=\w)', '. ', str_token),
            parserinfo=DateParserInfo(dayfirst=True, yearfirst=True)
        )
        new_token_pars = token_pars + timedelta(days=int_delta)
        new_token = re.findall(r'\W+|\w+', str_token)
        parts = re.findall(r'\w+', str_token)

    except Exception as e:
        logging.warning(f"Failed to parse ({e}): {str_token}")
        return 'DATE'

    if re.search('[a-zA-Z]+', str_token):

        month = datetime.strftime(token_pars, '%B')

        for form in dateFormatsAlpha:

            try:
                parts_pars = datetime.strftime(token_pars, form)

            except Exception as e:
                logging.warning(f"Failed tpo parse ({e}): {str_token}")
                return 'DATE'

            idx_month = [i for i, form in enumerate(dateReplMonths[month]) if
                         parts == re.findall(r'\w+', re.sub(month, form, parts_pars))]
            if idx_month:
                new_month = datetime.strftime(new_token_pars, '%B')
                if len(dateReplMonths[new_month]) > idx_month[0]:
                    new_parts_pars = re.findall(
                        r'\w+',
                        re.sub(
                            new_month,
                            dateReplMonths[new_month][idx_month[0]],
                            datetime.strftime(new_token_pars, form)
                        )
                    )
                else:
                    new_parts_pars = re.findall(
                        r'\w+',
                        re.sub(
                            new_month,
                            dateReplMonths[new_month][0],
                            datetime.strftime(new_token_pars, form))
                    )
                c = 0
                for i, part in enumerate(new_token):
                    if part.isalnum():  # and len(part) == 1: # todd
                        try:
                            new_token[i] = new_parts_pars[c]
                            c += 1
                        except Exception:
                            new_token = new_parts_pars
                            break
                new_token = ''.join(new_token)
    else:
        for form in dateFormatsNr:
            try:
                parts_pars = re.findall(r'\w+', datetime.strftime(token_pars, form))
                if parts_pars == parts:
                    new_parts_pars = re.findall(r'\w+', datetime.strftime(new_token_pars, form))
                    new_token = '.'.join(new_parts_pars)
            except Exception as e:
                new_token = 'DATE'
                logging.warning(f"Something wrong with parsing ({e})!")

    if not type(new_token) is str:
        new_token = ''.join(new_token)

    if not new_token.endswith('.') and str_token.endswith('.'):
        new_token += '.'

    return new_token


def check_and_clean_date_proof(str_date):
    try:
        dateutil.parser.parse(
            re.sub(r'\.(?=\w)', '. ', str_date),
            parserinfo=DateParserInfo(dayfirst=True, yearfirst=True)
        )
        return str_date
    except Exception:
        logging.warning(msg='Warnung - fehlerhaftes Datum: ' + str_date)
        return -1


def check_and_clean_date(str_date):
    try:
        dateutil.parser.parse(
            re.sub(r'\.(?=\w)', '. ', str_date),
            parserinfo=DateParserInfo(dayfirst=True, yearfirst=True)
        )

        return str_date
    except Exception as e:

        logging.warning(f"Bad date ({e}): {str_date}")

        # if re.fullmatch(pattern="\d{2}(\.|\s)\d{2}(\.|\s)\d{4}", string=str_date):
        #    match = re.match(pattern="\d{2}(\.|\s)\d{2}(\.|\s)\d{4}", string=str_date)
        #    return str_date[match.start():match.end()].replace(' ', '.')

        # elif re.fullmatch(pattern="\d\d?\.\s?[A-Za-zöäü]+\s?\d\d\d\d", string=str_date):
        #    return str_date[0:-4] + ' ' + str_date[-4] + str_date[-3] + str_date[-2] + str_date[-1]

        # elif re.fullmatch(pattern="3/20009", string=str_date):
        #    return '3/2009'

        # else:
        #    logging.warning(msg='Warnung - fehlerhaftes Datum: ' + str_date)
        #    return 0
