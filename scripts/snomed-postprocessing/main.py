import json
import re

from scttsrapy.api import EndpointBuilder
import scttsrapy.concepts as concepts


def pprint_json(json_data):
    print(json.dumps(json_data, indent=2))


def filter_by_semantic_tag(json_data: dict, tag: str = None) -> dict:
    if tag is None:
        return json_data
    if not json_data.get("success", False):
        return {
            "success": False,
            "content": []
        }

    regex = re.compile(r'\({}\)'.format(tag), flags=re.IGNORECASE)
    return {
        "success": True,
        "content": [
            d for d in json_data.get("content", []) if regex.match(d.get("fsn", {}).get("term", ""))
        ]
    }

if __name__ == "__main__":
    # Set up the endpoint for local snowstorm
    endpoint_builder = EndpointBuilder()
    endpoint_builder.set_api_endpoint("http://nlp-prod:9021")

    # Query all children for concept '47295007' --> "Psychomotor agitation (finding)"
    concept_children = concepts.get_concept_children("47295007", endpoint_builder=endpoint_builder)
    pprint_json(filter_by_semantic_tag(concept_children, tag="disorder"))