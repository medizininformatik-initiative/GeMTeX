import json
import logging
import pathlib
from abc import ABC, abstractmethod
from collections import namedtuple
from dataclasses import dataclass

import cassis

from ariadne.contrib.uima_cas_mapper.mapping_reader import MappingConfig

response_consumer_return_value = namedtuple(
    "response_consumer_return_value", ["offsets", "labels", "count", "score"]
)


@dataclass
class Annotation:
    begin: int
    end: int
    layer: str
    score: float
    src: object

    def get(self, attr: str):
        if attr not in ["begin", "end", "layer", "score"]:
            if isinstance(self.src, dict):
                return self.src.get(attr)
            elif isinstance(self.src, object):
                return getattr(self.src, attr)
        return getattr(self, attr)


class Processor(ABC):
    def __init__(self, proc_type):
        self.type = proc_type

    @abstractmethod
    def init(self, response, consumer):
        consumer.count = 0
        consumer.labels = []
        consumer.offsets = []
        consumer.scores = []

    @abstractmethod
    def get_next(self) -> Annotation: raise NotImplementedError


class JsonProcessor(Processor):
    def __init__(self):
        super().__init__(self.__class__.__name__)
        self.json_data = None

    def init(self, json_response: dict, consumer):
        if "payload" not in json_response:
            logging.warning(f"No payload:\n{json_response}")
        super().init(json_response, consumer)
        self.json_data = json_response.get("payload", [])
        return self

    def get_next(self) -> Annotation:
        for anno in self.json_data:
            _begin = anno.get("begin", None)
            _end = anno.get("end", None)
            _layer = anno.get("type", None)
            _score = 0.0   # ToDo: get real score if available

            if _begin is None or _end is None or _layer is None:
                continue
            yield Annotation(begin=_begin, end=_end, layer=_layer, score=_score, src=anno)


class CasProcessor(Processor):
    def __init__(self):
        super().__init__(self.__class__.__name__)
        self.cas_data = None

    def init(self, cas: cassis.Cas, consumer):
        super().init(cas, consumer)
        self.cas_data = cas
        return self

    def get_next(self) -> Annotation:
        for anno in self.cas_data.select()


class ResponseConsumer(ABC):
    def __init__(self, name: str, processor: Processor):
        self.name = name
        self.processor = processor
        self.count = 0
        self.labels = []
        self.offsets = []
        self.scores = []

    def process(self, response) -> "response_consumer_return_value":
        raise NotImplementedError


class MappingConsumer(ResponseConsumer):

    def __init__(self, config: str, processor: Processor):
        super().__init__(self.__class__.__name__, processor)
        self.mapper = MappingConfig.build(pathlib.Path(config))

    def process(self, response) -> "response_consumer_return_value":
        _processor = self.processor.init(response, self)

        for anno in _processor.get_next():
            for source_layer, check_dict in self.mapper.annotation_mapping.items():
                if anno.layer == source_layer:
                    for _label, _check_call in check_dict.items():
                        if _check_call(anno):
                            self.labels.append(_label)
                            self.offsets.append(
                                (
                                    anno.begin,
                                    anno.end,
                                )
                            )
                            self.scores.append(anno.score)
                            self.count += 1
                            continue
                    continue
        return response_consumer_return_value(self.offsets, self.labels, self.count, self.scores)


class SimpleDeidConsumer(ResponseConsumer):
    def __init__(self, processor: Processor = None):
        super().__init__(self.__class__.__name__, JsonProcessor() if processor is None else processor)
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

    def process(self, response):
        _processor = self.processor.init(response, self)

        for anno in _processor.get_next():
            if anno.layer.startswith(self.namespace):
                _anno_label = anno.layer[len(self.namespace):]
                if _anno_label not in self.deid_types:
                    continue
                self.count += 1
                self.offsets.append(
                    (
                        anno.begin,
                        anno.end,
                    )
                )
                self.labels.append(_anno_label)
        return response_consumer_return_value(self.offsets, self.labels, self.count, self.scores)


if __name__ == "__main__":
    response_path = pathlib.Path(pathlib.Path(__file__).parent.parent.parent / pathlib.Path("tests/resources/albers_response.json"))
    config_path = pathlib.Path(pathlib.Path(__file__).parent.parent.parent / pathlib.Path("prefab-mapping-files/deid_mapping_singlelayer.json"))

    deid_consumer = MappingConsumer(str(config_path.resolve()), JsonProcessor())
    processed = deid_consumer.process(json.load(response_path.open('rb')))
    print(processed)
