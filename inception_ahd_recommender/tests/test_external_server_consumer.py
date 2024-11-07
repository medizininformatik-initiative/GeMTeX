import pathlib

import cassis
import pytest

from ariadne.contrib.external_server_consumer import MappingConsumer, ProcessorType

_config = "../prefab-mapping-files/general_mapping_singlelayer.json"

@pytest.fixture
def cas_mapping_consumer():
    return MappingConsumer(config=_config, processor=ProcessorType.CAS)

@pytest.fixture
def typesystem():
    return cassis.load_typesystem(pathlib.Path("resources/albers_TypeSystem.xml"))

@pytest.fixture
def cas_server_response(typesystem):
    return cassis.load_cas_from_xmi(pathlib.Path("resources/Albers.txt.xmi"), typesystem=typesystem)

def test_mapping_consumer(cas_mapping_consumer, cas_server_response):
    cas_mapping_consumer.process(cas_server_response)