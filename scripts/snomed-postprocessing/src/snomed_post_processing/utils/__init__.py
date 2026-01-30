import json


def pprint_json(json_data):
    print(json.dumps(json_data, indent=2))


def filter_by_semantic_tag(
    json_data: dict, tag: str = None, positive: bool = True
) -> dict:
    """
    Filters the results of e.g. "scttsrapy"´s `get_concept_children` by the respective "semantic tag".

    :param json_data: the result dict, containing at least a "content" field that features a list of concepts.
    :param tag: the semantic tag to filter by (e.g. "disorder", "finding", etc.).
    :param positive: whether to include concepts with said semantic tag (`True`) or to exclude them (`False`).
    """
    if tag is None:
        return json_data
    if not json_data.get("success", False):
        return {"success": False, "content": []}

    if positive:
        bool_check = (
            lambda x: x.get("fsn", {}).get("term", "").lower().find(f"({tag.lower()})")
            != -1
        )
    else:
        bool_check = (
            lambda x: x.get("fsn", {}).get("term", "").lower().find(f"({tag.lower()})")
            == -1
        )
    return {
        "success": True,
        "content": [d for d in json_data.get("content", []) if bool_check(d)],
    }
