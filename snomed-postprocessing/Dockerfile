FROM python:3.13-slim-bookworm

RUN pip install uv

WORKDIR /snomed_postprocessing

COPY . .

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN uv tool install . && uv tool update-shell && uv cache clean

ENTRYPOINT ["programm-entry"]