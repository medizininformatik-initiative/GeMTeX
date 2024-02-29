import json
import logging
import pathlib
from collections import namedtuple
from pathlib import Path
from pydoc import locate
from typing import Any, Optional, List, Union

import requests
from cassis import Cas

<<<<<<< HEAD
from ariadne.classifier import Classifier
from ariadne.contrib.external_server_consumer import ResponseConsumer
from ariadne.contrib.inception_util import create_span_prediction
from ariadne.protocol import TrainingDocument
=======
from inception_ahd_recommender.ariadne.classifier import Classifier
from inception_ahd_recommender.ariadne.contrib.external_server_consumer import ResponseConsumer
from inception_ahd_recommender.ariadne.contrib.inception_util import create_span_prediction
from inception_ahd_recommender.ariadne.protocol import TrainingDocument
>>>>>>> 008b9d2... init external ahd recommender for inception

logging.basicConfig(level=logging.INFO)
config_object = namedtuple('server_config',
                           ['address', 'security_token', 'endpoint', 'response_consumer'])


def _as_named_tuple(dct: dict):
    lower_dict = {k.lower(): v for k, v in dct.items()}
    if len(set(config_object._fields).intersection(lower_dict.keys())) != len(config_object._fields):
        logging.warning(f'There are missing keys in the server config:'
                        f' {set(config_object._fields).difference(lower_dict.keys())}.'
                        f' They will be treated the as "None"')

    _response_consumer = lower_dict.get('response_consumer', "").split("::")
    _response_consumer_name = None
    _response_consumer_config = None
    if len(_response_consumer) == 2:
        _response_consumer_name = _response_consumer[0]
        _response_consumer_config = _response_consumer[1]
    elif len(_response_consumer) == 1 and _response_consumer[0] != '':
        _response_consumer_name = _response_consumer[0]

    return config_object(
        address=lower_dict.get("address", None),
        endpoint=lower_dict.get("endpoint", None),
        security_token=lower_dict.get("security_token", None),
        response_consumer={
            "name": _response_consumer_name,
            "config": _response_consumer_config
        },
    )


class ExternalUIMAClassifier(Classifier):
    def __init__(self, server_config: Union[Path, dict], model_directory: Path = None):
        super().__init__(model_directory)

        self._config = config_object(address=None, security_token=None, endpoint=None, response_consumer=None)
        if isinstance(server_config, Path):
            try:
                self._config = json.load(server_config.open('br'), object_hook=_as_named_tuple)
            except OSError:
                logging.error(f"Couldn't find/read server config file at the specified path: {server_config.resolve()}")
        elif isinstance(server_config, dict):
            self._config = _as_named_tuple(server_config)
        else:
            logging.error(f"Server configuration is neither a path to a json file nor a dict: {server_config.__class__}.")

        if self._config.address is None or self._config.endpoint is None:
            logging.error(f"Neither address nor endpoint couldn't be defined for the provided config file:"
                          f" {json.load(server_config.open('rb'))}")

        self._connect_to_server()
        self._create_response_consumer()

    def _connect_to_server(self):
        self._server = None
        try:
            response = requests.get(self._config.address)
            logging.info(f"Server accessible: '{response.text}'")
            self._server = f"{self._config.address}/{self._config.endpoint if not self._config.endpoint.startswith('/') else self._config.endpoint[1:]}"
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError):
            logging.error(f"No server reachable under '{self._config.address}'")

    def _create_response_consumer(self):
        self.response_consumer: Optional[ResponseConsumer] = None
        _response_consumer = self._config.response_consumer
        if _response_consumer is not None:
            self.response_consumer = locate(f"{_response_consumer.get('name')}")(config=_response_consumer.get("config"))
        else:
            logging.error(f"Couldn't find response consumer '{_response_consumer.get('name')}'"
                          f"{' with config: ' if _response_consumer.get('config', False) else '.'}"
                          f"{_response_consumer.get('config') if _response_consumer.get('config', False) else ''}")

    def _post_text(self, text: str):
        if self._server is not None and self.response_consumer is not None:
            response = requests.post(
                self._server,
                data=text.encode('utf-8'),
                headers={
                    "Content-Type": "text/plain; charset=utf-8",
                    "api-token": self._config.security_token
                })
            _parsed_response = self.response_consumer.parse_json(response.json())
            return _parsed_response
        else:
            return None

    def _load_model(self, user_id: str) -> Optional[Any]:
        return super()._load_model(user_id)

    def _save_model(self, user_id: str, model: Any):
        super()._save_model(user_id, model)

    def _get_model_path(self, user_id: str) -> Path:
        return super()._get_model_path(user_id)

    def predict(self, cas: Cas, layer: str, feature: str, project_id: str, document_id: str, user_id: str):
        _server_response = self._post_text(cas.sofa_string)
        for i in range(_server_response.count):
            _begin, _end = _server_response.offsets[i]
            prediction = create_span_prediction(cas, layer, feature, _begin, _end, _server_response.labels[i], _server_response.score[i])
            cas.add(prediction)

    def fit(self, documents: List[TrainingDocument], layer: str, feature: str, project_id, user_id: str):
        for doc in documents:
            logging.info(doc.document_id)


if __name__ == "__main__":
    from inception_ahd_recommender.ariadne.server import Server

    server = Server()
    server.add_classifier("ahd_deid", ExternalUIMAClassifier(pathlib.Path("../../tests/resources/test_config.json")))

    server.start()
