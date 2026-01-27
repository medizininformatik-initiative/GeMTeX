import collections
import logging
from Surrogator.Substitution.CasManagement import CasManagement
from Surrogator.Substitution.Entities.Date import get_quarter
from Surrogator.Substitution.KeyCreator import get_n_random_keys


class CasManagementGemtex(CasManagement):

    """
    Class to handle all gemtex mode replacements, depending on CasManagement

    Parameters
    ----------
    config : dict

    """

    def __init__(self):
        self.used_keys = []

    def manipulate_cas(self, cas):
        """
        Manipulate sofa string into a cas object.

        Returns
        -------
        cas : cas object
        """

        sofa = cas.get_sofa()
        annotations = collections.defaultdict(set)
        dates = []

        relevant_types = [t for t in cas.typesystem.get_types() if 'PHI' in t.name]
        cas_name = relevant_types[0].name

        for sentence in cas.select(cas_name):
            for token in cas.select_covered(cas_name, sentence):

                if token.kind is not None:

                    if token.kind not in ['PROFESSION', 'AGE']:
                        if token.kind != 'DATE':
                            annotations[token.kind].add(token.get_covered_text())

                        if token.kind == 'DATE':
                            if token.get_covered_text() not in dates:
                                dates.append(token.get_covered_text())

                        if token.kind == 'DATE_BIRTH':
                            if token.get_covered_text() not in dates:
                                dates.append(token.get_covered_text())

                        if token.kind == 'DATE_DEATH':
                            if token.get_covered_text() not in dates:
                                dates.append(token.get_covered_text())

                else:
                    logging.warning('token.kind: NONE - ' + token.get_covered_text())
                    annotations[token.kind].add(token.get_covered_text())

        random_keys, self.used_keys = get_n_random_keys(
            n=sum([len(annotations[label_type]) for label_type in annotations]),
            used_keys=self.used_keys
        )

        key_ass = {}
        key_ass_ret = {}
        i = 0

        for label_type in annotations:
            key_ass[label_type] = {}

            if label_type not in ['DATE']:
                key_ass_ret[label_type] = {}

            for annotation in annotations[label_type]:
                if label_type not in ['DATE', 'DATE_BIRTH', 'DATE_DEATH']:
                    key_ass[label_type][annotation] = random_keys[i]
                    key_ass_ret[label_type][random_keys[i]] = annotation
                    i = i+1

        new_text = ''
        last_token_end = 0

        shift = []

        relevant_types = [t for t in cas.typesystem.get_types() if 'PHI' in t.name]
        cas_name = relevant_types[0].name

        for sentence in cas.select(cas_name):

            for token in cas.select_covered(cas_name, sentence):

                if token.kind is not None:

                    if token.kind not in ['PROFESSION', 'AGE']:

                        if not token.kind.startswith('DATE'):
                            replace_element = '[** ' + token.kind + ' ' + key_ass[token.kind][token.get_covered_text()] + ' **]'
                        else:  # DATE
                            if token.kind in ['DATE_BIRTH', 'DATE_DEATH']:
                                quarter_date = get_quarter(token.get_covered_text())
                                replace_element = '[** ' + token.kind + ' ' + quarter_date + ' **]'
                                key_ass_ret[token.kind][quarter_date] = token.get_covered_text()

                            else:
                                replace_element = '[** ' + token.kind + ' ' + token.get_covered_text() + ' **]'

                    else:
                        replace_element = '[** ' + token.kind + ' ' + token.get_covered_text() + ' **]'

                else:
                    logging.warning('token.kind: NONE - ' + token.get_covered_text())
                    replace_element = '[** ' + str(token.kind) + ' ' + key_ass[token.kind][token.get_covered_text()] + ' **]'

                new_text, new_end, shift, last_token_end, token.begin, token.end = self.set_shift_and_new_text(
                    token=token,
                    replace_element=replace_element,
                    last_token_end=last_token_end,
                    shift=shift,
                    new_text=new_text,
                    sofa=sofa,
                )

        new_text = new_text + cas.get_sofa().sofaString[last_token_end:]

        return {
            'cas': self.manipulate_sofa_string_in_cas(cas=cas, new_text=new_text, shift=shift),
            'key_ass': key_ass_ret,
            'used_keys': self.used_keys
        }
