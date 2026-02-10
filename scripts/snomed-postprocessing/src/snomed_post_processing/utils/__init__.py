import enum
import json
import re


class DumpMode(enum.Enum):
    SEMANTIC = enum.auto()
    VERSION = enum.auto()


def _flexible_whitespace_pattern(s: str) -> str:
    """
    Build a regex pattern from `s` where any whitespace sequence matches \\s+.
    Non-whitespace characters are escaped for regex.
    """
    escaped_parts = []
    i = 0
    while i < len(s):
        if s[i].isspace():
            while i < len(s) and s[i].isspace():
                i += 1
            escaped_parts.append(r"\s+")
        else:
            char = s[i]
            if char in r".^$*+?{}[]\|()":
                escaped_parts.append(re.escape(char))
            else:
                escaped_parts.append(char)
            i += 1
    return "".join(escaped_parts)


def pprint_json(json_data):
    print(json.dumps(json_data, indent=2))


def filter_by_semantic_tag(
    json_data: dict, tags: list[str] = None, positive: bool = True
) -> dict:
    """
    Filters the results of e.g. "scttsrapy"´s `get_concept_children` by the respective "semantic tag".

    :param json_data: the result dict, containing at least a "content" field that features a list of concepts.
    :param tags: a list of the semantic tags to filter by (e.g. "disorder", "finding", etc.).
    :param positive: whether to include concepts with said semantic tags (`True`) or to exclude them (`False`).
    """
    if tags is None:
        return json_data
    if not json_data.get("success", False):
        return {"success": False, "content": []}

    re_tags = re.compile(fr"\({"|".join([_flexible_whitespace_pattern(t) for t in tags])}\)", re.IGNORECASE)

    if positive:
        bool_check = lambda d: (
            len(re_tags.findall(d.get("fsn", {}).get("term", "").lower())) > 0
        )
    else:
        bool_check = lambda d: (
            len(re_tags.findall(d.get("fsn", {}).get("term", "").lower())) == 0
        )
    return {
        "success": True,
        "content": [d for t in tags for d in json_data.get("content", []) if bool_check(d)],
    }
