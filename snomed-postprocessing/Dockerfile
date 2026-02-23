FROM python:3.13-slim-bookworm

RUN pip install uv

WORKDIR /snomed_postprocessing

COPY . .

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN uvx install . && uv cache clean

ENTRYPOINT ["programm-entry"]