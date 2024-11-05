import json
import logging
import pathlib
import sys
from abc import ABC, abstractmethod
from collections import namedtuple, defaultdict
from dataclasses import dataclass
from enum import Enum

import cassis
from cassis.typesystem import TypeNotFoundError, FeatureStructure

from ariadne.contrib.uima_cas_mapper.mapping_reader import (
    MappingConfig,
    MappingTypeEnum,
)

response_consumer_return_value = namedtuple(
    "response_consumer_return_value",
    ["offsets", "labels", "count", "score", "features"],
)


class ProcessorType(Enum):
    CAS = "cas"
    JSON = "json"


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
    def get_next(self, layer) -> Annotation:
        raise NotImplementedError


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
        logging.debug(f"Getting next for layer {layer}")
        for anno in self.json_data:
            _begin = anno.get("begin", None)
            _end = anno.get("end", None)
            _layer = anno.get("type", None)
            _score = anno.get("score", 0.0)

            if _begin is None or _end is None or _layer is None or layer != _layer:
                continue
            logging.debug(f"Yielding result for {anno.get('id')}")
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
        logging.debug(f"Getting next for layer {layer}")
        try:
            for anno in self.cas_data.select(layer):
                result_anno = Annotation(
                    begin=anno.get("begin"),
                    end=anno.get("end"),
                    score=anno.get("score") if anno.get("score") is not None else 0.0,
                    src=anno,
                )
                if result_anno.begin is None or result_anno.end is None:
                    continue
                logging.debug(f"Yielding result for {anno.xmiID}")
                yield result_anno
        except TypeNotFoundError:
            yield


class ResponseConsumer(ABC):
    def __init__(self, name: str, processor: ProcessorType):
        self.processor_types = {
            ProcessorType.CAS: CasProcessor,
            ProcessorType.JSON: JsonProcessor,
        }
        self.name = name
        self.processor = self.processor_types.get(processor, CasProcessor)()
        self.count = 0
        self.labels = []
        self.offsets = []
        self.scores = []
        self.features = []

    @abstractmethod
    def process(self, response) -> "response_consumer_return_value":
        raise NotImplementedError


class MappingConsumer(ResponseConsumer):

    def __init__(
        self, config: str, processor: ProcessorType = ProcessorType.CAS, **kwargs
    ):
        super().__init__(name=self.__class__.__name__, processor=processor)
        self.mapper = MappingConfig.build(pathlib.Path(config))
        self._check_target_layers()

    def _check_target_layers(self):
        _target_layers = defaultdict(list)
        _problematic_layers = defaultdict(set)
        for k, v in self.mapper.annotation_mapping.items():
            _target_layers[v.target_layer].append(k)
            if v.mapping_type == MappingTypeEnum.SINGLELAYER:
                _problematic_layers[v.target_layer].add(v.entry_name)
        if len(_target_layers) > 1:
            _pre = (
                f"The mapping file seems to be configured for more than one target layer:"
                f" {list(_target_layers.keys())}."
            )
            if len(_problematic_layers) > 1:
                logging.error(
                    f"{_pre}\n"
                    f"\tAdditionally, {len(_problematic_layers)} of them compete for the recommender"
                    f" assignment, but only one layer is allowed for each recommender.\n"
                    f"\tPlease rewrite the mapping file or delete/check one or more of the entries:"
                    f" {set([v for v in _problematic_layers.values()])}."
                )
                sys.exit(-1)
            logging.warning(
                f"{_pre}\n\tBut right now, nothing needs to be done about it."
            )
        elif len(_target_layers) < 1:
            logging.error(
                f"The mapping file seems to be configured badly since there is no target layer."
            )
            sys.exit(-1)

    def process(self, response) -> "response_consumer_return_value":
        _processor = self.processor.init(response, self)

        for source_layer, check_dict in self.mapper.annotation_mapping.items():
            # Multilayer is not allowed for Recommender since a single Recommender is configured for an INCEpTION layer
            if check_dict.mapping_type == MappingTypeEnum.MULTILAYER:
                logging.warning(
                    f"An INCEpTION Recommender is only configured for a single layer."
                    f" It appears your configuration file has an entry for Multilayer processing."
                    f" Skipping the entry in question:\n{check_dict}"
                )
                continue

            anno: Annotation
            for anno in _processor.get_next(source_layer):
                _final_label = None
                _final_features = None

                if anno is None:
                    continue
                # if check_dict.mapping_type == MappingTypeEnum.SINGLELAYER:
                for _label, _check_call in check_dict.items():
                    if _check_call(anno):
                        _final_label = _label
                        _final_features = {check_dict.target_feature: _label}
                        _dupl = check_dict.additional_feats.pop(check_dict.target_feature, None)
                        if _dupl is not None:
                            logging.warning(
                                f"Removed {_dupl} from 'add_feature' for entry '{check_dict.entry_name}_{_label}'.")
                        for k, v in check_dict.additional_feats.items():  # Provide the "add_feature" values
                            _feat_val = anno.get(k)
                            if _feat_val is not None:
                                _final_features[k] = _feat_val
                        self.count += 1
                        break  # Stacking layers is not allowed
                # else:
                #     logging.warning(f"An INCEpTION Recommender is only configured for a single layer."
                #                     f" It appears your configuration file has an entry for Multilayer processing."
                #                     f" Skipping the entry in question:\n{check_dict}")
                #     continue  # Multilayer is not allowed for Recommender since a single Recommender is configured for an INCEpTION layer
                # _final_label = check_dict.target_layer
                # _final_features = {tf: sf[0](anno.src, sf[1]) for tf, sf in check_dict.items()}
                # self.count += 1

                self.labels.append(_final_label)
                self.offsets.append(
                    (
                        anno.begin,
                        anno.end,
                    )
                )
                self.scores.append(anno.score)
                self.features.append(_final_features)
        return response_consumer_return_value(
            self.offsets, self.labels, self.count, self.scores, self.features
        )


class SimpleDeidConsumer(ResponseConsumer):
    def __init__(self, processor: ProcessorType = ProcessorType.JSON, **kwargs):
        super().__init__(name=self.__class__.__name__, processor=processor)
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

    def process(self, response) -> "response_consumer_return_value":
        _processor = self.processor.init(response, self)

        for anno in _processor.get_next():
            if anno.layer.startswith(self.namespace):
                _anno_label = anno.layer[len(self.namespace) :]
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
        return response_consumer_return_value(
            self.offsets, self.labels, self.count, self.scores, None
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    response_path_json = pathlib.Path(
        pathlib.Path(__file__).parent.parent.parent
        / pathlib.Path("tests/resources/albers_response.json")
    )
    response_path_xmi = pathlib.Path(
        pathlib.Path(__file__).parent.parent.parent
        / pathlib.Path("tests/resources/Albers.txt.xmi")
    )
    typesystem_path = pathlib.Path(
        pathlib.Path(__file__).parent.parent.parent
        / pathlib.Path("tests/resources/albers_TypeSystem.xml")
    )
    config_path = pathlib.Path(
        pathlib.Path(__file__).parent.parent.parent
        / pathlib.Path("prefab-mapping-files/deid_mapping_singlelayer.json")
    )

    deid_consumer_json = MappingConsumer(str(config_path.resolve()), ProcessorType.JSON)
    processed_json = deid_consumer_json.process(
        json.load(response_path_json.open("rb"))
    )
    print(processed_json)

    deid_consumer_xmi = MappingConsumer(str(config_path.resolve()), ProcessorType.CAS)
    ts = cassis.load_typesystem(typesystem_path)
    processed_xmi = deid_consumer_xmi.process(
        cassis.load_cas_from_xmi(response_path_xmi, ts, lenient=True)
    )
    print(processed_xmi)
