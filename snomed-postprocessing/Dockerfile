FROM python:3.13-slim-bookworm

RUN pip install uv

WORKDIR /snomed_postprocessing

RUN apt-get update --yes && \
    apt-get install --yes git

COPY . .

RUN uv sync && uv cache clean

ENV COMMAND="program-entry"

ENTRYPOINT "uv run ${COMMAND}"