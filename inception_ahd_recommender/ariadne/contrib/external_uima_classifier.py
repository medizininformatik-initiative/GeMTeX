import json
import logging
import pathlib
import sys
from abc import abstractmethod, ABC
from collections import namedtuple
from pathlib import Path
from pydoc import locate
from typing import Any, Optional, List, Union

import cassis
import requests
from cassis import Cas
from averbis import Client as AHDClient
from requests import RequestException

from ariadne.classifier import Classifier as AriadneClassifier
from ariadne.contrib.external_server_consumer import (
    ResponseConsumer,
    response_consumer_return_value,
    ProcessorType,
    CasProcessor,
)
from ariadne.contrib.inception_util import create_span_prediction
from ariadne.protocol import TrainingDocument

logging.basicConfig(level=logging.INFO)
config_object = namedtuple(
    "server_config",
    [
        "address",
        "security_token",
        "pipeline_project",
        "pipeline_name",
        "response_consumer",
        "classifier",
        "processor",
        "docker_mode"
    ],
)


def _as_named_tuple(dct: dict):
    lower_dict = {k.lower(): v for k, v in dct.items()}
    if len(set(config_object._fields).intersection(lower_dict.keys())) != len(
        config_object._fields
    ):
        logging.warning(
            f"There are missing keys in the server config:"
            f" {set(config_object._fields).difference(lower_dict.keys())}."
            f' They will be treated as "None"'
        )

    _response_consumer = lower_dict.get("response_consumer", "").split("::")
    _response_consumer_name = None
    _response_consumer_config = None
    if len(_response_consumer) == 2:
        _response_consumer_name = _response_consumer[0]
        _response_consumer_config = _response_consumer[1]
    elif len(_response_consumer) == 1 and _response_consumer[0] != "":
        _response_consumer_name = _response_consumer[0]

    _security = lower_dict.get("security_token", "").split(",")
    if len(_security) == 1:
        if _security[0] != "":
            _security = _security[0].strip()
            logging.info(f"Authentication with Token: {_security[:6]}...")
        else:
            _security = None
    elif len(_security) == 2:
        _security = (
            _security[0].strip(),
            _security[1].strip(),
        )
        logging.info(
            f"Authentication with Username '{_security[0]}' &"
            f" Password: '{_security[1][:2]}{'*'*(len(_security[1])-2)}'"
        )

    return config_object(
        address=lower_dict.get("address", None),
        pipeline_name=lower_dict.get("pipeline_name", None),
        pipeline_project=lower_dict.get("pipeline_project", None),
        security_token=_security,
        response_consumer={
            "name": _response_consumer_name,
            "config": _response_consumer_config,
        },
        classifier=lower_dict.get("classifier"),
        processor=lower_dict.get("processor"),
        docker_mode=lower_dict.get("docker_mode"),
    )


class ExternalClassifier(ABC):
    def __init__(self, config, classifier_type):
        self._classifier_type = classifier_type
        self._config: Optional["config_object"] = None
        self._server = None
        self._response_consumer: Optional[ResponseConsumer] = None

        self._initialize_configuration(config)
        self._initialize_server()
        self._initialize_response_consumer()

    def _initialize_configuration(self, config):
        self._config = config_object(
            address=None,
            security_token=None,
            pipeline_name=None,
            pipeline_project=None,
            response_consumer=None,
            classifier=None,
            processor=None,
            docker_mode=None
        )
        if isinstance(config, Path):
            try:
                self._config = json.load(config.open("br"), object_hook=_as_named_tuple)
            except OSError:
                logging.error(
                    f"Couldn't find/read server config file at the specified path: {config.resolve()}"
                )
        elif isinstance(config, dict):
            self._config = _as_named_tuple(config)
        else:
            logging.error(
                f"Server configuration is neither a path to a json file nor a dict: {config.__class__}."
            )

        if (
            self.get_configuration().address is None
            or self.get_configuration().pipeline_name is None
            or self.get_configuration().pipeline_name is None
        ):
            logging.error(
                f"Either address or project/pipeline name couldn't be defined for the provided config file:"
                f" {json.load(config.open('rb'))}"
            )

    def get_configuration(self) -> "config_object":
        return (
            self._config
            if self._config is not None
            else config_object(None, None, None, None, None, None, None, None)
        )

    @abstractmethod
    def _initialize_server(self):
        raise NotImplementedError

    def get_server(self):
        return self._server

    def _initialize_response_consumer(self):
        try:
            _processor_type = ProcessorType(self.get_configuration().processor)
        except ValueError:
            logging.warning(
                f"Processor type {self.get_configuration().processor} not found, using default 'cas'."
            )
            _processor_type = ProcessorType.CAS
        if self.get_configuration().response_consumer is not None:
            self._response_consumer = locate(
                f"{self.get_configuration().response_consumer.get('name')}"
            )(
                config=self.get_configuration().response_consumer.get("config"),
                processor=_processor_type,
            )
        else:
            logging.error(
                f"Couldn't find response consumer '{self.get_configuration().response_consumer.get('name')}'"
                f"{' with config: ' if self.get_configuration().response_consumer.get('config', False) else '.'}"
                f"{self.get_configuration().response_consumer.get('config') if self.get_configuration().response_consumer.get('config', False) else ''}"
            )

    def get_response_consumer(self) -> ResponseConsumer:
        return self._response_consumer

    @abstractmethod
    def process_text(self, text: str, language: str = None):
        raise NotImplementedError


class ExternalUIMAClassifier(AriadneClassifier, ExternalClassifier):
    def __init__(self, config: Union[Path, dict], model_directory: Path = None):
        super().__init__(model_directory)
        super(AriadneClassifier, self).__init__(config, self.__class__.__name__)

    def _initialize_server(self):
        try:
            if self.get_configuration().address is None:
                raise RuntimeError("Configuration has seemingly failed")
            response = requests.get(self.get_configuration().address)
            logging.info(f"Server accessible: '{response.status_code}'")
            _endpoint = (
                f"health-discovery/rest/v1/textanalysis/projects/{self.get_configuration().pipeline_project}"
                f"/pipelines/{self.get_configuration().pipeline_name}/analyseText"
            )
            self._server = f"{self.get_configuration().address}/{_endpoint}"
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError):
            logging.error(
                f"No server reachable under '{self.get_configuration().address}'"
            )

    def _load_model(self, user_id: str) -> Optional[Any]:
        return super()._load_model(user_id)

    def _save_model(self, user_id: str, model: Any):
        super()._save_model(user_id, model)

    def _get_model_path(self, user_id: str) -> Path:
        return super()._get_model_path(user_id)

    def process_text(self, text: str, language: str = None):
        if self.get_server() is not None and self.get_response_consumer() is not None:
            response = requests.post(
                self.get_server(),
                data=text.encode("utf-8"),
                headers={
                    "Content-Type": "text/plain; charset=utf-8",
                    "api-token": self.get_configuration().security_token,
                },
            )
            _parsed_response = self.get_response_consumer().process(response.json())
            return _parsed_response
        else:
            _faulty_config = (
                "server" if self.get_server() is None else "response consumer"
            )
            logging.warning(
                f"Configuration for at least the '{_faulty_config}' went wrong."
            )
            return None

    def predict(
        self,
        cas: Cas,
        layer: str,
        feature: str,
        project_id: str,
        document_id: str,
        user_id: str,
    ):
        _server_response = self.process_text(cas.sofa_string)
        add_prediction_to_cas(
            cas,
            layer,
            feature,
            project_id,
            document_id,
            user_id,
            _server_response,
            self.__class__.__name__,
        )

    def fit(
        self,
        documents: List[TrainingDocument],
        layer: str,
        feature: str,
        project_id,
        user_id: str,
    ):
        for doc in documents:
            logging.info(doc.document_id)


class AHDClassifier(AriadneClassifier, ExternalClassifier):

    def __init__(self, config: Union[Path, dict], model_directory: Path = None):
        self._pipeline = None
        super().__init__(model_directory)
        super(AriadneClassifier, self).__init__(config, self.__class__.__name__)

    def get_pipeline(self):
        return self._pipeline

    def _initialize_server(self):
        self._server = None
        try:
            _msg = f"{self.__class__.__name__} server initialization with "
            if isinstance(self.get_configuration().security_token, str):
                _msg += "API Token."
                _api_token = self.get_configuration().security_token
            # elif ((isinstance(self.get_configuration().security_token, tuple)
            #        or isinstance(self.get_configuration().security_token, list)
            #       ) and len(self.get_configuration().security_token) == 2):
            #     _msg += "Username & Password."
            #     _user = self.get_configuration().security_token[0]
            #     _pwd = self.get_configuration().security_token[1]
            #     self._server = AHDClient(
            #         f"{self.get_configuration().address}/health-discovery",
            #         username=_user,
            #         password=_pwd,
            #     )
            #     _api_token = self._server.regenerate_api_token(_user, _pwd)
            #     logging.warning(f"Regenerated new API token '{_api_token[:4]}...'. Storing and using this one.")
            else:
                # raise Exception("No means of authentication provided (either token or username + password).")
                raise Exception(
                    "No means of authentication provided (need an API token)."
                )

            logging.info(_msg)
            self._server = AHDClient(
                f"{self.get_configuration().address}/health-discovery",
                api_token=_api_token,
            )
            project = self.get_server().get_project(
                name=self.get_configuration().pipeline_project
            )
            pipeline = project.get_pipeline(self.get_configuration().pipeline_name)
            pipeline.ensure_started()
            self._pipeline = pipeline
            logging.info(
                f"Pipeline '{self.get_configuration().pipeline_name}' in project '{self.get_configuration().pipeline_project}' successfully assigned."
            )
        except Exception as e:
            logging.error(e)
            sys.exit(-1)

    def _load_model(self, user_id: str) -> Optional[Any]:
        return super()._load_model(user_id)

    def _save_model(self, user_id: str, model: Any):
        super()._save_model(user_id, model)

    def _get_model_path(self, user_id: str) -> Path:
        return super()._get_model_path(user_id)

    def process_text(self, text: str, language: str = None):
        try:
            return self.get_response_consumer().process(
                self.get_pipeline().analyse_text_to_cas(source=text, language=language)
            )
        except RequestException as e:
            log_str = f"AHD not accessible: '{e}'"
            logging.error(log_str)

    def fit(
        self,
        documents: List[TrainingDocument],
        layer: str,
        feature: str,
        project_id,
        user_id: str,
    ):
        super().fit(documents, layer, feature, project_id, user_id)

    def predict(
        self,
        cas: Cas,
        layer: str,
        feature: str,
        project_id: str,
        document_id: str,
        user_id: str,
    ):
        _server_response = self.process_text(cas.sofa_string, cas.document_language)
        add_prediction_to_cas(
            cas,
            layer,
            feature,
            project_id,
            document_id,
            user_id,
            _server_response,
            self.__class__.__name__,
        )


def add_prediction_to_cas(
    cas: Cas,
    layer: str,
    feature: str,
    project_id: str,
    document_id: str,
    user_id: str,
    response: response_consumer_return_value,
    class_name: Optional[str] = None,
):
    if isinstance(response, response_consumer_return_value) and isinstance(
        response.count, int
    ):
        for i in range(response.count):
            _begin, _end = response.offsets[i]
            prediction = create_span_prediction(
                cas,
                layer,
                feature,
                _begin,
                _end,
                response.labels[i],
                response.score[i],
            )
            cas.add(prediction)
    else:
        logging.error(
            f"Failed to predict document with id: {document_id} (response from 'process_text' seems to be faulty)."
            f"--> In classifier: '{class_name}'."
        )


if __name__ == "__main__":
    from ariadne.server import Server

    server = Server()
    server.add_classifier(
        "ahd_deid",
        ExternalUIMAClassifier(pathlib.Path("../../tests/resources/test_config.json")),
    )

    server.start()
