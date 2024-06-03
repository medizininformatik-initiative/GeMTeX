import logging
import os
import pathlib

from ariadne.contrib.external_uima_classifier import ExternalUIMAClassifier
from ariadne.server import Server

_config = {
    "address": os.getenv("EXTERNAL_SERVER_ADDRESS", "http://localhost:8080"),
    "security_token": os.getenv("EXTERNAL_SERVER_TOKEN", ""),
    "pipeline_project": os.getenv("PIPELINE_PROJECT", "GeMTeX"),
    "pipeline_name": os.getenv("PIPELINE_NAME", "deid"),
    "response_consumer": os.getenv(
        "CONSUMER", "ariadne.contrib.external_uima_classifier.SimpleDeidConsumer"
    ),
}

_server_handle = os.getenv("SERVER_HANDLE", "deid_recommender")
_model_folder = os.getenv("MODEL_DIR", None)
try:
    _model_folder = pathlib.Path(_model_folder)
    _model_folder.mkdir(parents=True, exist_ok=True)
except:
    _model_folder = None

logging.info(
    f"\nUsing the following address: {_config['address']}{_config['endpoint']}\n"
    f"with ResponseConsumer: '{_config['response_consumer']}'"
)

server = Server()
server.add_classifier(_server_handle, ExternalUIMAClassifier(server_config=_config, model_directory=_model_folder))

app = server._app

if __name__ == "__main__":
    server.start()
elif __name__ != "__main__":
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
