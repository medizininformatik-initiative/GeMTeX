import json
import logging
import pathlib
from abc import ABC, abstractmethod
from collections import namedtuple
from dataclasses import dataclass

import cassis
from cassis.typesystem import TypeNotFoundError

from ariadne.contrib.uima_cas_mapper.mapping_reader import MappingConfig

response_consumer_return_value = namedtuple(
    "response_consumer_return_value", ["offsets", "labels", "count", "score"]
)


@dataclass
class Annotation:
    begin: int
    end: int
    score: float
    src: object

    def get(self, attr: str):
        if attr not in ["begin", "end", "score"]:
            if isinstance(self.src, dict):
                return self.src.get(attr, None)
            elif isinstance(self.src, object):
                return getattr(self.src, attr, None)
        return getattr(self, attr, None)


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
    def get_next(self, layer) -> Annotation: raise NotImplementedError


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

    def get_next(self, layer) -> Annotation:
        for anno in self.json_data:
            _begin = anno.get("begin", None)
            _end = anno.get("end", None)
            _layer = anno.get("type", None)
            _score = anno.get("score", 0.0)

            if _begin is None or _end is None or _layer is None or layer != _layer:
                continue
            yield Annotation(begin=_begin, end=_end, score=_score, src=anno)


class CasProcessor(Processor):
    def __init__(self):
        super().__init__(self.__class__.__name__)
        self.cas_data = None

    def init(self, cas: cassis.Cas, consumer):
        super().init(cas, consumer)
        self.cas_data = cas
        return self

    def get_next(self, layer) -> Annotation:
        try:
            for anno in self.cas_data.select(layer):
                result_anno = Annotation(
                    begin=anno.get("begin"),
                    end=anno.get("end"),
                    score=anno.get("score") if anno.get("score") is not None else 0.0,
                    src=anno
                )
                if result_anno.begin is None or result_anno.end is None:
                    continue
                yield result_anno
        except TypeNotFoundError:
            yield


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

        for source_layer, check_dict in self.mapper.annotation_mapping.items():
            for anno in _processor.get_next(source_layer):
                if anno is None:
                    continue
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
    response_path_json = pathlib.Path(pathlib.Path(__file__).parent.parent.parent / pathlib.Path("tests/resources/albers_response.json"))
    response_path_xmi = pathlib.Path(pathlib.Path(__file__).parent.parent.parent / pathlib.Path("tests/resources/Albers.txt.xmi"))
    typesystem_path = pathlib.Path(pathlib.Path(__file__).parent.parent.parent / pathlib.Path("tests/resources/albers_TypeSystem.xml"))
    config_path = pathlib.Path(pathlib.Path(__file__).parent.parent.parent / pathlib.Path("prefab-mapping-files/deid_mapping_singlelayer.json"))

    deid_consumer_json = MappingConsumer(str(config_path.resolve()), JsonProcessor())
    processed_json = deid_consumer_json.process(json.load(response_path_json.open('rb')))

    deid_consumer_xmi = MappingConsumer(str(config_path.resolve()), CasProcessor())
    ts = cassis.load_typesystem(typesystem_path)
    processed_xmi = deid_consumer_xmi.process(cassis.load_cas_from_xmi(response_path_xmi, ts, lenient=True))
    print(processed_xmi)
