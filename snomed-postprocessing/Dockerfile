FROM python:3.13-slim-bookworm

RUN pip install uv

WORKDIR /snomed_postprocessing

RUN apt-get update --yes && \
    apt-get install --yes git

COPY . .

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN uv sync && uv cache clean

ENV cmd_command="program-entry"

ENTRYPOINT ["uv", "run", "$cmd_command"]