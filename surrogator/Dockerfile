FROM python:3.11-slim-buster

ARG WEBSERVICE_WORKDIR=/webservice

WORKDIR $WEBSERVICE_WORKDIR

COPY surrogator.py pyproject.toml ./
COPY Surrogator ./Surrogator/
COPY resources ./resources
RUN pip install .
RUN download_models

ENTRYPOINT [ "python", "surrogator.py" ]
