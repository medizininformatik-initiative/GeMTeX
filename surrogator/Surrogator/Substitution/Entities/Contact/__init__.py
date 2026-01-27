import re


MOBILE_PREFIXES = [
    '151',  # Telekom (D1)
    '152',  # Vodafone (D2)
    '155',  # E-Plus (now O2)
    '156',  # Drillisch / 1&1 (MVNOs)
    '157',  # E-Plus
    '159',  # Telefónica (O2)

    '160',  # Vodafone (D2)
    '162',  # Vodafone (D2)
    '163',  # E-Plus

    '170',  # Telekom (D1)
    '171',  # Telekom (D1)
    '172',  # Vodafone (D2)
    '173',  # Telekom (D1)
    '174',  # Telekom (D1)
    '175',  # Telekom (D1)

    '176',  # E-Plus
    '177',  # O2
    '178',  # O2
    '179',  # O2
]

_PHONE_RE = re.compile(r"""
    ^\s*
    (?:
        (?P<prefix>(?:\+|00)\d{1,3}|0)   # +49, 0043, or 0
        [\s./-]*                         # optional separator
    )?
    \(? (?P<area>\d{1,5}) \)?            # area code (1–5 digits), optional parentheses
    [\s./-]*                             # optional separator
    (?P<number>\d[\d\s./-]*)             # subscriber digits, may include separators
    \s*$
""", re.VERBOSE)


def split_phone(number: str) -> tuple[str | None, str, str]:
    """
    Splits a European phone number into:
    - prefix: '+<country_code>', '0', or None
    - area: 1–5 digit area or mobile network code
    - subscriber: remaining digits, punctuation removed

    Assumes:
    - Area code is either clearly separated (by space, slash, dash, etc.)
      OR simply the first 1–5 digits after the prefix.
    - Tolerates various common notations: +49, 0049, (030), 030/1234567, etc.
    """
    m = _PHONE_RE.match(number)
    if not m:
        raise ValueError(f"Unrecognised phone format: {number!r}")

    prefix = m.group('prefix')
    area = m.group('area')
    number = re.sub(r'\D', '', m.group('number'))  # remove separators from subscriber

    return prefix, area, number