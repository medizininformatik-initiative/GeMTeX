from Surrogator.Substitution.CasManagement import CasManagement


class CasManagementSimple(CasManagement):

    """
    Class to handle all x and entity mode replacements, depending on CasManagement

    Parameters
    ----------
    mode : str

    """

    def __init__(self, mode):
        self.mode = mode

    def manipulate_cas(self, cas):
        """
        Manipulate sofa string into cas object.

        Parameters
        ----------
        cas: cas object
        mode: string

        Returns
        -------
        cas : cas object
        """
        #sofa = cas.get_sofa()
        shift = []

        new_text = ''
        last_token_end = 0

        relevant_types = [t for t in cas.typesystem.get_types() if 'PHI' in t.name]
        cas_name = relevant_types[0].name

        for sentence in cas.select(cas_name):
            for token in cas.select_covered(cas_name, sentence):
                if self.mode == 'x':
                    replace_element = ''.join(['X' for _ in token.get_covered_text()])
                    new_text, new_end, shift, last_token_end, token.begin, token.end = self.set_shift_and_new_text(
                        token=token,
                        replace_element=replace_element,
                        last_token_end=last_token_end,
                        shift=shift,
                        new_text=new_text,
                        sofa=cas.get_sofa(),
                    )

                elif self.mode == 'entity':
                    replace_element = str(token.kind)
                    new_text, new_end, shift, last_token_end, token.begin, token.end = self.set_shift_and_new_text(
                        token=token,
                        replace_element=replace_element,
                        last_token_end=last_token_end,
                        shift=shift,
                        new_text=new_text,
                        sofa=cas.get_sofa(),
                    )
                else:
                    exit(-1)

        new_text = new_text + cas.get_sofa().sofaString[last_token_end:]

        return {
            'cas':
                self.manipulate_sofa_string_in_cas(
                    cas=cas,
                    new_text=new_text,
                    shift=shift
                )
        }
