import random
import string


def get_n_random_keys(n: int, used_keys: list[str]):
    """
    Get n random keys for PHI replacements

    Parameters
    ----------
    n: integer
    used_keys: dict[Any, Any]

    Returns
    -------
    gen: list of strings, used keys: list of strings
    """

    random.seed(random.randint(0, 10000))
    letters = string.ascii_uppercase

    gen_keys = []

    for i in range(n):

        key = ''.join(random.choices(letters, k=2)) + str(random.randint(0, 9)) + ''.join(
            random.choices(letters, k=2)) + str(random.randint(0, 9))

        if key not in used_keys:
            if key not in gen_keys:
                gen_keys.append(key)
                used_keys.append(key)
            else:
                key = get_n_random_keys(n=1, used_keys=used_keys)
                gen_keys.append(key[0][0])
                used_keys.append(key[0][0])
        else:
            key = get_n_random_keys(n=1, used_keys=used_keys)
            gen_keys.append(key[0][0])
            used_keys.append(key[0][0])

    return gen_keys, used_keys


def get_n_random_filenames(n, used_keys):
    """
    Get n random keys for filenames

    Parameters
    ----------
    n: integer
    used_keys: list of strings

    Returns
    -------
    gen: list of strings, used keys: list of strings
    """

    random.seed(random.randint(0, 1000))
    letters = string.ascii_uppercase

    gen_keys = []

    for i in range(n):

        key = ''.join(random.choices(letters, k=3)) + str(random.randint(0, 9)) + ''.join(
            random.choices(letters, k=3)) + str(random.randint(0, 9))

        if key not in used_keys:
            if key not in gen_keys:
                gen_keys.append(key)
                used_keys.append(key)
            else:
                key = get_n_random_filenames(n=1, used_keys=used_keys)
                gen_keys.append(key[0][0])
                used_keys.append(key[0][0])
        else:
            key = get_n_random_filenames(n=1, used_keys=used_keys)
            gen_keys.append(key[0][0])
            used_keys.append(key[0][0])

    return gen_keys, used_keys
