# Licensed to the Technische Universität Darmstadt under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The Technische Universität Darmstadt
# licenses this file to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import logging
import os
from pathlib import Path
from typing import List, Optional, Any

import joblib
from cassis import Cas

import ariadne
from ariadne.protocol import TrainingDocument

logger = logging.getLogger(__file__)


class Classifier:
    def __init__(self, model_directory: Path = None):
        self.model_directory = (
            ariadne.model_directory if model_directory is None else model_directory
        )

    def fit(
        self,
        documents: List[TrainingDocument],
        layer: str,
        feature: str,
        project_id,
        user_id: str,
    ):
        pass

    def predict(
        self,
        cas: Cas,
        layer: str,
        feature: str,
        project_id: str,
        document_id: str,
        user_id: str,
    ):
        raise NotImplementedError()

    def _load_model(self, user_id: str) -> Optional[Any]:
        model_path = self._get_model_path(user_id)
        if model_path.is_file():
            logger.debug("Model found for [%s]", model_path)
            return joblib.load(model_path)
        else:
            logger.debug("No model found for [%s]", model_path)
            return None

    def _save_model(self, user_id: str, model: Any):
        model_path = self._get_model_path(user_id)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_model_path = model_path.with_suffix(".joblib.tmp")
        joblib.dump(model, tmp_model_path)
        os.replace(tmp_model_path, model_path)

    def _get_model_path(self, user_id: str) -> Path:
        return self.model_directory / self.name / f"model_{user_id}.joblib"

    @property
    def name(self) -> str:
        return type(self).__name__
