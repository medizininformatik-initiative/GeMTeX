ARG ROOT_CONTAINER=python:3.9-slim
FROM $ROOT_CONTAINER

RUN pip install uv

ARG RECOMMENDER_WORKDIR=/inception_ahd_recommender

WORKDIR $RECOMMENDER_WORKDIR

COPY . .

RUN uv sync

ENTRYPOINT ["uv", "run", "gunicorn"]