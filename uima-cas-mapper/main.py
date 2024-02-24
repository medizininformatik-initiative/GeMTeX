import argparse
import enum
import logging
import pathlib
from collections import defaultdict

import cassis.typesystem
from tqdm import tqdm
from typing import Optional, Tuple, Union

from cassis import *
from cassis.typesystem import TYPE_NAME_STRING, FeatureStructure
from tqdm.contrib.logging import logging_redirect_tqdm
from mapping_reader import MappingConfig, MappingTypeEnum

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class ExportEnum(enum.IntEnum):
    JSON = 1
    XMI = 2

class TransformerParser(argparse.ArgumentParser):
    def __init__(self):
        super().__init__()
        # Positional Arguments
        self.add_argument('xmi_path',
                          help="Path where the 'source' XMIs reside.")
        self.add_argument('typesystem',
                          help="Path to the 'source' Typesystem.")
        self.add_argument('mapping_file',
                          help="A file that specifies how the 'source' layers are mapped to 'target' layers.")

        # Optional Arguments
        self.add_argument('-o',
                          '--output_path',
                          default=None,
                          help="The path where the transformed XMIs/JSON file will be stored."
                               " (default: 'INPUT_PATH/out')")
        self.add_argument('-e',
                          '--file_ending',
                          default='xmi',
                          help="File ending for the serialized cas'. (default: 'xmi')")
        self.add_argument('-t',
                          '--ts_file_ending',
                          default='xml',
                          help="File ending for the type system. (default: 'xml')")

        self.add_argument('-x',
                          '--export_format',
                          default='json',
                          help="Which format the 'target' cas should have (json/xmi). (default: 'json')")

    def parse_args(self, **kwargs):
        ns = super().parse_args(**kwargs)
        ns.xmi_path = pathlib.Path(ns.xmi_path)
        ns.typesystem = pathlib.Path(ns.typesystem)
        ns.mapping_file = pathlib.Path(ns.mapping_file)
        ns.output_path = pathlib.Path(
            ns.xmi_path if ns.output_path is None else '',
            ns.output_path if ns.output_path is not None else 'out')

        if not ns.output_path.exists():
            ns.output_path.mkdir(parents=True)

        _exp_dict = {'json': ExportEnum.JSON, 'jason': ExportEnum.JSON, 'jsn': ExportEnum.JSON,
                     'xmi': ExportEnum.XMI, 'xml': ExportEnum.XMI}
        if ns.export_format not in _exp_dict:
            logging.warning(f"Unknown export format: {ns.export_format}. Using default format 'json'.")
            ns.export_format = ExportEnum.JSON
        else:
            ns.export_format = _exp_dict[ns.export_format]

        return ns


def check_for_more_specific(duplicate_dict: dict, layer_instance: FeatureStructure, feat):
    _kind = layer_instance.get('kind') if layer_instance.get('kind') is not None else layer_instance.type.name
    _id = f"{layer_instance.get('begin')}_{layer_instance.get('end')}_{_kind}"
    if _id not in duplicate_dict:
        duplicate_dict[_id]["layer"] = layer_instance
        duplicate_dict[_id]["features"] = feat
    else:
        _old_none = [
            duplicate_dict[_id]["layer"].get(i) for i in duplicate_dict[_id]["layer"].__dir__() if
            (not i.startswith('__'))
        ].count(None)

        _now_none = [
            layer_instance.get(i) for i in layer_instance.__dir__() if (not i.startswith('__'))
        ].count(None)

        if _old_none > _now_none:
            duplicate_dict[_id]["layer"] = layer_instance
            duplicate_dict[_id]["features"] = feat


def mark_new(
        new_cas: Cas,
        old_cas: Cas,
        ts: TypeSystem,
        mapping: MappingConfig,
        missing_type_warn: list = None
) -> Tuple[Cas, list]:
    # ToDo: deal with overlapping/stacking layers of the same type?
    #  (e.g.: DATE spans for '07-10.10.2022' -> DATE is applied to 07, 10.10.2022 and 07-10.10.2022)
    if missing_type_warn is None:
        missing_type_warn = []

    for source_layer, mapping_dict in mapping.annotation_mapping.items():
        duplicate_check = defaultdict(dict)
        try:
            for layer_instance in old_cas.select(source_layer):
                feat = mapping_dict
                if mapping_dict.mapping_type == MappingTypeEnum.SINGLELAYER:
                    for k, v in mapping_dict.items():
                        if v(layer_instance):
                            feat = {mapping_dict.target_feature: k}
                else:
                    feat = {tf: sf[0](layer_instance, sf[1]) for tf, sf in mapping_dict.items()}
                check_for_more_specific(duplicate_check, layer_instance, feat)

        except cassis.typesystem.TypeNotFoundError as e:
            if source_layer not in missing_type_warn:
                logging.warning(f" {e}")
            missing_type_warn.append(source_layer)
            continue

        for fs_dict in duplicate_check.values():
            _layers, _feats = fs_dict["layer"], fs_dict["features"]
            ts_init = ts.get_type(mapping_dict.target_layer)
            ts_instance = ts_init(begin=_layers.get("begin"), end=_layers.get("end"), **_feats)
            new_cas.add(ts_instance)

    new_cas.sofa_string = old_cas.sofa_string
    new_cas.sofa_mime = old_cas.sofa_mime
    new_cas.sofa_uri = old_cas.sofa_uri
    new_cas.sofa_array = old_cas.sofa_array
    return new_cas, missing_type_warn


def init_source_cas(
        cas_path: pathlib.Path,
        typesystem: Union[pathlib.Path, TypeSystem],
        suffix: str = "xmi"
) -> Tuple[Optional[Cas], Optional[TypeSystem], Optional[str]]:
    cas: Optional[Cas] = None

    if isinstance(typesystem, pathlib.Path):
        logging.info(f" Loading TypeSystem from: '{typesystem.resolve()}'")
        try:
            with typesystem.open('rb') as ts_file:
                typesystem = load_typesystem(ts_file)
        except Exception as e:
            logging.error(e)
            typesystem = None
    elif isinstance(typesystem, TypeSystem):
        pass
    else:
        typesystem = None

    try:
        if cas_path.is_file():
            with cas_path.open('rb') as cas_file:
                if suffix in ['xmi']:
                    cas = load_cas_from_xmi(cas_file, typesystem)
                elif suffix in ['json']:
                    cas = load_cas_from_json(cas_file)
            yield cas, typesystem, cas_path.stem
        elif cas_path.is_dir():
            _count = sum([1 for i in cas_path.glob(f"*.{suffix}") if i.is_file()])
            logging.info(f" Processing {suffix}-data from:"
                         f" '{cas_path.resolve()}' ({_count} file{'' if _count == 1 else 's'}).")
            for cas_file in tqdm(cas_path.glob(f"*.{suffix}"), ascii=True, total=_count):
                yield from init_source_cas(pathlib.Path(cas_file), typesystem, suffix)
        else:
            raise FileNotFoundError

    except Exception as e:
        logging.error(e)


def init_target_ts(mapping: MappingConfig) -> TypeSystem:
    typesystem = TypeSystem()
    for _, target_layer, layer_dict in mapping._layer_iterator():
        ts_type = typesystem.create_type(target_layer)
        ts_type_features = list(layer_dict.get("features", {}).keys())
        if len(ts_type_features) == 0:
            continue
        for feature in ts_type_features:
            typesystem.create_feature(
                domainType=ts_type,
                name=feature,
                rangeType=TYPE_NAME_STRING  # ToDo: change this to be configured in mapping file
            )
    return typesystem


if __name__ == '__main__':
    t_parser = TransformerParser()
    args = t_parser.parse_args()

    mapping_config = MappingConfig.build(args.mapping_file)
    target_ts = init_target_ts(mapping_config)
    missing_types = None
    with logging_redirect_tqdm():
        for _cas, _ts, fi_name in init_source_cas(args.xmi_path, args.typesystem, args.file_ending):
            target_cas = Cas(target_ts)
            export_cas, missing_types = mark_new(target_cas, _cas, target_ts, mapping_config, missing_types)
            if args.export_format == ExportEnum.JSON:
                export_cas.to_json(pathlib.Path(args.output_path, f"{fi_name}.json"), pretty_print=True)
            elif args.export_format == ExportEnum.XMI:
                export_cas.to_xmi(pathlib.Path(args.output_path, f"{fi_name}.xmi"), pretty_print=True)
