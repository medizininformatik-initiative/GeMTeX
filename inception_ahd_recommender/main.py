import logging
import os
import pathlib
import sys
from pydoc import locate
from typing import Union

from ariadne.contrib.external_server_consumer import ProcessorType
from ariadne.contrib.external_uima_classifier import AHDClassifier
from ariadne.server import Server


def eval_bool(bool_str: Union[str, bool]) -> bool:
    if isinstance(bool_str, bool):
        return bool_str
    elif isinstance(bool_str, str):
        return {"true": True, "false": False, "yes": True, "no": False,
                "y": True, "n": False, "j": True, "ja": True, "nein": False}.get(bool_str.lower())
    else:
        return True

_config = {
    "address": os.getenv("EXTERNAL_SERVER_ADDRESS", "http://localhost:8080"),
    "security_token": os.getenv("EXTERNAL_SERVER_TOKEN", ""),
    "pipeline_project": os.getenv("PIPELINE_PROJECT", "GeMTeX"),
    "pipeline_name": os.getenv("PIPELINE_NAME", "deid"),
    "response_consumer": os.getenv(
        "CONSUMER", "ariadne.contrib.external_server_consumer.SimpleDeidConsumer"
    ),
    "classifier": os.getenv("CLASSIFIER", False),
    "processor": os.getenv("PROCESSOR", ProcessorType.CAS),
    "docker_mode": eval_bool(os.getenv("DOCKER_MODE", True)),
}

_server_handle = os.getenv("SERVER_HANDLE", "deid_recommender")
_model_folder = os.getenv("MODEL_DIR", None)
try:
    _model_folder = pathlib.Path(_model_folder)
    _model_folder.mkdir(parents=True, exist_ok=True)
except:
    _model_folder = None

if __name__ != "__main__":
    logging.info(
        f"\nUsing the following address: {_config['address']}\n"
        f"with project: {_config['pipeline_project']} and\n"
        f"pipeline: {_config['pipeline_name']} and\n"
        f"with ResponseConsumer: '{_config['response_consumer']}'"
    )

try:
    _classifier = (
        AHDClassifier if not _config["classifier"] else locate(_config["classifier"])
    )
except Exception as e:
    logging.error(e)
    sys.exit(-1)

server = Server()

if __name__ == "__main__":
    _config = {
        "address": "http://0.0.0.0:9010",
        "security_token": "8ffafddb8986d5dde5e62f9bab804631485cae42bcde5498c52b06a9f769586c",
        "pipeline_project": "RemoteRecommender",
        # "pipeline_name": "gemtex_preannotation-0.12.0",
        "pipeline_name": "deid-custom",
        "response_consumer": "ariadne.contrib.external_server_consumer.MappingConsumer::"
        # "./prefab-mapping-files/snomed_mapping_singlelayer.json",
        "./prefab-mapping-files/deid_mapping_singlelayer.json",
        "classifier": os.getenv("CLASSIFIER", False),
        "processor": os.getenv("PROCESSOR", ProcessorType.CAS),
        "docker_mode": False
    }
    _classifier = (
        AHDClassifier if not _config["classifier"] else locate(_config["classifier"])
    )
    server.add_classifier(
        # _server_handle, _classifier(config=_config, model_directory=_model_folder)
        "ahd_recommender", _classifier(config=_config, model_directory=_model_folder)
    )
    server.start(port=5002)
elif __name__ != "__main__":
    server.add_classifier(
        _server_handle, _classifier(config=_config, model_directory=_model_folder)
    )
    app = server._app

    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
