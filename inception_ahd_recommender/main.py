import logging
import os

from ariadne.contrib.external_uima_classifier import ExternalUIMAClassifier
from ariadne.server import Server

_config = {
  "address": os.getenv("EXTERNAL_SERVER_ADDRESS", "http://localhost:8080"),
  "security_token": os.getenv("EXTERNAL_SERVER_TOKEN", ""),
  "endpoint": os.getenv("PIPELINE_ENDPOINT",
                        "/health-discovery/rest/v1/textanalysis/projects/GeMTeX/pipelines/deid/analyseText"),
  "response_consumer": os.getenv("CONSUMER", "inception_ahd_recommender.ariadne.contrib.external_uima_classifier.DeidConsumer")
}

_server_handle = os.getenv("SERVER_HANDLE", "deid_recommender")

logging.info(f"\nUsing the following address: {_config['address']}{_config['endpoint']}\n"
             f"with ResponseConsumer: '{_config['response_consumer']}'")

server = Server()
server.add_classifier(_server_handle, ExternalUIMAClassifier(server_config=_config))

app = server._app

if __name__ == "__main__":
    server.start()
elif __name__ != "__main__":
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
