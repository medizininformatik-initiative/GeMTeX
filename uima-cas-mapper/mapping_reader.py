"""
File: main.py
Author: Franz Matthies
Email: franz.matthies@imise.uni-leipzig.de
Date: February 24, 2024

Description: Contains a class that interprets a mapping file and provides the mapping methods.
"""

import enum
import json
import pathlib
from types import SimpleNamespace
from typing import Union, Iterator, Dict


class ArchitectureEnum(enum.Enum):
    TARGET = "target"
    SOURCE = "source"


class MappingTypeEnum(enum.Enum):
    SINGLELAYER = "singlelayer"
    MULTILAYER = "multilayer"


class AnnotationMapping(dict):
    def __init__(
            self,
            target_layer: str,
            target_feature: str,
            mapping_type: MappingTypeEnum = MappingTypeEnum.SINGLELAYER,
            *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.mapping_type = mapping_type
        self.target_layer = target_layer
        self.target_feature = target_feature

    @property
    def mapping_type(self):
        return self._mapping_type

    @mapping_type.setter
    def mapping_type(self, val: MappingTypeEnum):
        self._mapping_type = val

    @property
    def target_layer(self):
        return self._target_layer

    @target_layer.setter
    def target_layer(self, val: str):
        self._target_layer = val

    @property
    def target_feature(self):
        return self._target_feature

    @target_feature.setter
    def target_feature(self, val: str):
        self._target_feature = val


class MappingConfig:
    macros: dict
    identifier: SimpleNamespace
    entries: SimpleNamespace
    annotation_mapping: Dict[str, AnnotationMapping]

    def _layer_iterator(self) -> Iterator[tuple]:
        for layer_suffix, layer_dict in self.entries.__dict__.items():
            if layer_dict.get("layer", None) is None:
                source_layer = None
                target_layer = f"{self.identifier.target_default}.{layer_suffix}"
            elif not layer_dict.get("layer"):
                source_layer = f"{self.identifier.source_default}.{layer_suffix}"
                target_layer = f"{self.identifier.target_default}.{layer_suffix}"
            else:
                source_layer = list(layer_dict.get("layer").values())[0]
                target_layer = list(layer_dict.get("layer").keys())[0]
            yield source_layer, target_layer, layer_dict

    def _build_annotation_mapping(self):
        self.annotation_mapping = {}
        for source_layer, target_layer, layer_dict in self._layer_iterator():
            if source_layer is not None:
                self.annotation_mapping[source_layer] = AnnotationMapping(
                    target_layer,
                    None,
                    MappingTypeEnum.MULTILAYER,
                    {tf: ((lambda x, y: sf[1:]), sf[1:]) if sf.startswith("$") else ((lambda x, y: x.get(y)), sf) for tf, sf in layer_dict.get("features", {}).items()}
                )
            else:
                for feat, feat_val in layer_dict.get("features", {}).items():
                    if isinstance(feat_val, dict):
                        for key, val in feat_val.items():
                            if isinstance(val, dict):
                                source_layer = self.get_macro_value(val.get("layer", None), ArchitectureEnum.SOURCE)
                                check_fs = MappingConfig.resolve_simple_bool(val.get("feature", lambda x: True))
                                if source_layer not in self.annotation_mapping:
                                    self.annotation_mapping[source_layer] = AnnotationMapping(
                                        target_layer=target_layer,
                                        target_feature=feat,
                                        mapping_type=MappingTypeEnum.SINGLELAYER
                                    )
                                self.annotation_mapping[source_layer][key] = check_fs

    def get_macro_value(self, macro: Union[str, dict], architecture: ArchitectureEnum = ArchitectureEnum.TARGET):
        value = macro
        if isinstance(macro, str):
            if macro.startswith("#"):
                _list = value.split(".")
                value = (f"{self.macros.get(_list[0][1:])}"
                         f"{'.' if len(_list) > 1 else ''}"
                         f"{'.'.join(_list[1:])}")
            elif macro.startswith("."):
                return f"{self.identifier.source_default if architecture == ArchitectureEnum.SOURCE else self.identifier.target_default}{macro}"
        return value

    @staticmethod
    def resolve_simple_bool(check: str):
        if isinstance(check, str) and check.startswith("@"):
            _expr = check[1:].split("==")
            if len(_expr) == 2:
                _target = _expr[0]
                _check = _expr[1]
            else:
                return lambda x: x.get(_expr[0]) is not None
            return lambda x: (x.get(_target) if x.get(_target) is not None else "none").lower() in _check.split("|")
        else:
            return check

    @staticmethod
    def build(config_file: pathlib.Path):
        mapping_config = MappingConfig()
        config = None
        if isinstance(config_file, pathlib.Path):
            with config_file.open('rb') as fi:
                config = json.load(fi)

        if config is None or config_file is None:
            return

        mapping_config.macros = config.get("IDENTIFIER_MACROS", {})

        _identifier_dict = {}
        for key, value in config.get("MAPPING", {}).get("IDENTIFIER", {}).items():
            _identifier_dict[key] = mapping_config.get_macro_value(value)
        mapping_config.identifier = SimpleNamespace(**_identifier_dict)

        _entries_dict = {}
        for entry, entry_values in config.get("MAPPING", {}).get("ENTRIES", {}).items():
            _entries_dict[entry] = {}
            for layer_feature, _dict in entry_values.items():
                _entries_dict[entry][layer_feature] = {}
                for key, value in _dict.items():
                    _entries_dict[entry][layer_feature][mapping_config.get_macro_value(key)] = mapping_config.get_macro_value(value)
        mapping_config.entries = SimpleNamespace(**_entries_dict)

        mapping_config._build_annotation_mapping()

        return mapping_config
