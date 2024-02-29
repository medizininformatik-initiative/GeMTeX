import logging
import pathlib
from collections import namedtuple

from ariadne.contrib.uima_cas_mapper.mapping_reader import MappingConfig

response_consumer_return_value = namedtuple(
    "response_consumer_return_value", ["offsets", "labels", "count", "score"]
)


class ResponseConsumer:
    def __init__(self, name: str):
        self.name = name

    def parse_json(self, json) -> "response_consumer_return_value":
        pass


class MappingConsumer(ResponseConsumer):

    def __init__(self, config: str):
        super().__init__(self.__class__.__name__)
        self.mapper = MappingConfig.build(pathlib.Path(config))

    def parse_json(self, json_response):
        _count = 0
        _labels = []
        _offsets = []
        _score = []
        if "payload" not in json_response:
            logging.warning(f"No payload:\n{json_response}")
        for anno in json_response.get("payload", []):
            for source_layer, check_dict in self.mapper.annotation_mapping.items():
                if anno.get("type", False) and anno.get("type") == source_layer:
                    for _label, _check_call in check_dict.items():
                        if _check_call(anno):
                            _labels.append(_label)
                            _offsets.append(
                                (
                                    anno.get("begin"),
                                    anno.get("end"),
                                )
                            )
                            _score.append(0.0)  # ToDo: get real score if available
                            _count += 1
        return response_consumer_return_value(_offsets, _labels, _count, _score)


class SimpleDeidConsumer(ResponseConsumer):
    def __init__(self):
        super().__init__(self.__class__.__name__)
        self.namespace = "de.averbis.types.health."
        self.deid_types = [
            "Date",
            "Name",
            "Age",
            "Contact",
            "ID",
            "Location",
            "Profession",
            "PHIOther",
        ]

    def parse_json(self, json_response):
        _count = 0
        _labels = []
        _offsets = []
        if "payload" not in json_response:
            logging.warning(f"No payload:\n{json_response}")
        for anno in json_response.get("payload", []):
            if anno.get("type", False) and anno.get("type").startswith(self.namespace):
                _anno_label = anno.get("type")[len(self.namespace) :]
                if _anno_label not in self.deid_types:
                    continue
                _count += 1
                _offsets.append(
                    (
                        anno.get("begin"),
                        anno.get("end"),
                    )
                )
                _labels.append(_anno_label)
        return response_consumer_return_value(_offsets, _labels, _count, 0.0)
