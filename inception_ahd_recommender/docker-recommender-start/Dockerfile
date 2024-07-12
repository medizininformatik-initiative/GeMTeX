ARG ROOT_CONTAINER=python:3.7-slim
FROM $ROOT_CONTAINER

ARG RECOMMENDER_WORKDIR=/inception_ahd_recommender

ARG RECOMMENDER_WORKERS
ARG RECOMMENDER_ADDRESS

WORKDIR $RECOMMENDER_WORKDIR


COPY .. .

RUN python -m pip install --upgrade pip
RUN python -m pip install gunicorn
RUN python -m pip install -e .
RUN python -m pip install -e ".[contrib]"


CMD gunicorn -w $RECOMMENDER_WORKERS -b $RECOMMENDER_ADDRESS --log-level INFO main:app