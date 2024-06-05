import logging
import os
import pathlib
import sys
from pydoc import locate

from ariadne.contrib.external_server_consumer import ProcessorType
from ariadne.contrib.external_uima_classifier import AHDClassifier
from ariadne.server import Server

_config = {
    "address": os.getenv("EXTERNAL_SERVER_ADDRESS", "http://localhost:8080"),
    "security_token": os.getenv("EXTERNAL_SERVER_TOKEN", ""),
    "pipeline_project": os.getenv("PIPELINE_PROJECT", "GeMTeX"),
    "pipeline_name": os.getenv("PIPELINE_NAME", "deid"),
    "response_consumer": os.getenv(
        "CONSUMER", "ariadne.contrib.external_server_consumer.SimpleDeidConsumer"
    ),
    "classifier": os.getenv("CLASSIFIER", False),
    "processor": os.getenv("PROCESSOR", ProcessorType.CAS)
}

_server_handle = os.getenv("SERVER_HANDLE", "deid_recommender")
_model_folder = os.getenv("MODEL_DIR", None)
try:
    _model_folder = pathlib.Path(_model_folder)
    _model_folder.mkdir(parents=True, exist_ok=True)
except:
    _model_folder = None

logging.info(
    f"\nUsing the following address: {_config['address']}\n"
    f"with project: {_config['pipeline_project']} and\n"
    f"pipeline: {_config['pipeline_name']} and\n"
    f"with ResponseConsumer: '{_config['response_consumer']}'"
)

try:
    _classifier = AHDClassifier if not _config["classifier"] else locate(_config["classifier"])
except Exception as e:
    logging.error(e)
    sys.exit(-1)

server = Server()
server.add_classifier(_server_handle, _classifier(config=_config, model_directory=_model_folder))

app = server._app

if __name__ == "__main__":
    server.start()
elif __name__ != "__main__":
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
