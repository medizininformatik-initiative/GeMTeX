import logging
import pathlib

import cassis
import pytest

from ariadne.contrib.external_server_consumer import MappingConsumer, ProcessorType
from ariadne.contrib.external_uima_classifier import add_prediction_to_cas

logging.getLogger().setLevel(logging.INFO)
scenario_dict = {
    "general": {
        "xmi": "resources/Baastrup.general.xmi",
        "ts": "resources/general_TypeSystem.xml",
        "mapping": "../prefab-mapping-files/general_mapping_singlelayer.json",
        "layer": "Core",
        "feature": "kind"
    },
    "deid": {
        "xmi": "resources/Albers.deid.xmi",
        "ts": "resources/deid_TypeSystem.xml",
        "mapping": "../prefab-mapping-files/deid_mapping_singlelayer.json",
        "layer": "PHI",
        "feature": "kind"
    }
}
scenario_switch = "general"

@pytest.fixture
def cas_mapping_consumer():
    return MappingConsumer(config=scenario_dict.get(scenario_switch).get("mapping"), processor=ProcessorType.CAS)

@pytest.fixture
def typesystem():
    return cassis.load_typesystem(pathlib.Path(scenario_dict.get(scenario_switch).get("ts")))

@pytest.fixture
def cas_server_response(typesystem):
    return cassis.load_cas_from_xmi(pathlib.Path(scenario_dict.get(scenario_switch).get("xmi")), typesystem=typesystem)

def test_mapping_consumer(cas_mapping_consumer, cas_server_response):
    logging.info(cas_mapping_consumer.process(cas_server_response).features)

def test_add_prediction_to_cas(cas_mapping_consumer, cas_server_response, typesystem):
    add_prediction_to_cas(
        cas=cassis.Cas(
            typesystem=typesystem,
            sofa_string=cas_server_response.sofa_string
        ),
        layer=scenario_dict.get(scenario_switch).get("layer"),
        feature=scenario_dict.get(scenario_switch).get("feature"),
        project_id="0",
        document_id="0",
        user_id="0",
        response=cas_mapping_consumer.process(cas_server_response)
    )